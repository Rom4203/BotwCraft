#!/usr/bin/env python3
"""BotwCraft: read-only, zero-dependency BOTW Switch Havok terrain collision exporter.

Inputs: your own Nintendo Switch Breath of the Wild RomFS Physics/TeraMeshRigidBody/
MainField/*.shktmrb or a ZIP containing the same files.
Outputs: local, versioned BTRI1 triangle cache (no Nintendo data distributed).
The cache is a bridge asset; by itself it does not install or activate a Minecraft mod.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import time
import zipfile

HKX_MAGIC = b'\x57\xe0\xe0\x57\x10\xc0\xc0\x10'
GRID_RE = re.compile(r'^(\d+)-(\d+)\.shktmrb$',re.I)


def yaz0(raw:bytes,max_size:int=128*1024*1024)->bytes:
    if raw[:4]!=b'Yaz0': raise ValueError('not Yaz0')
    size=int.from_bytes(raw[4:8],'big')
    if not 1<=size<=max_size: raise ValueError('bad Yaz0 output size')
    output=bytearray(size);p=16;w=0;flags=0;left=0
    while w<size:
        if left==0:
            if p>=len(raw):raise ValueError('truncated Yaz0 control')
            flags=raw[p];p+=1;left=8
        if flags & 0x80:
            if p>=len(raw):raise ValueError('truncated Yaz0 literal')
            output[w]=raw[p];w+=1;p+=1
        else:
            if p+2>len(raw):raise ValueError('truncated Yaz0 backreference')
            a,b=raw[p:p+2];p+=2
            dist=((a&0xf)<<8)+b+1;size_run=a>>4
            if size_run==0:
                if p>=len(raw):raise ValueError('truncated Yaz0 run')
                size_run=raw[p]+18;p+=1
            else:size_run+=2
            if dist>w or w+size_run>size:raise ValueError('invalid Yaz0 reference')
            for _ in range(size_run):output[w]=output[w-dist];w+=1
        flags=(flags<<1)&255;left-=1
    return bytes(output)


def u16(b,at):return struct.unpack_from('<H',b,at)[0]
def u32(b,at):return struct.unpack_from('<I',b,at)[0]
def u64(b,at):return struct.unpack_from('<Q',b,at)[0]
def vec3(b,at):return struct.unpack_from('<3f',b,at)

def extract_terrain(raw:bytes)->tuple[list[tuple[float,...]],dict]:
    data=yaz0(raw) if raw.startswith(b'Yaz0') else raw
    if not data.startswith(HKX_MAGIC):raise ValueError('not a Switch Havok packfile')
    if data[40:54]!=b'hk_2014.2.0-r1':raise ValueError('unsupported Havok SDK version')
    data_section_header=data.find(b'__data__',0,0x200)
    class_section_header=data.find(b'__classnames__',0,0x200)
    if data_section_header not in (0xc0,0xd0) or class_section_header<0:raise ValueError('unexpected Havok section layout')
    data_start=u32(data,data_section_header+20)
    local_fixup=u32(data,data_section_header+24)
    global_fixup=u32(data,data_section_header+28)
    virtual_fixup=u32(data,data_section_header+32)
    end_virtual=u32(data,data_section_header+36)
    class_start=u32(data,class_section_header+20)
    if data_start+end_virtual>len(data):raise ValueError('bad section offsets')
    fixes={u32(data,data_start+i):u32(data,data_start+i+4) for i in range(local_fixup,global_fixup,8) if u32(data,data_start+i)!=0xffffffff}
    shapes=[]
    for i in range(virtual_fixup,end_virtual,12):
        obj,section,classname=struct.unpack_from('<3I',data,data_start+i)
        if obj==0xffffffff:break
        name=data[class_start+classname:class_start+classname+80].split(b'\0',1)[0]
        if name==b'hkpBvCompressedMeshShape':shapes.append(obj)
    if len(shapes)!=1:raise ValueError(f'expected one terrain mesh, found {len(shapes)}')
    sh=shapes[0]
    def arr(rel,size,read):
        ptr=sh+rel
        n=u32(data,data_start+ptr+8)&0x3fffffff
        if n>1_000_000:raise ValueError('unreasonable mesh array count')
        if n==0:return []
        start=fixes.get(ptr)
        if start is None or start+n*size>local_fixup:raise ValueError('missing/invalid Havok local fixup')
        return [read(data,data_start+start+i*size) for i in range(n)]
    sections=arr(0xa0,96,lambda b,o:b[o:o+96])
    primitives=arr(0xb0,4,lambda b,o:b[o:o+4])
    shared_ids=arr(0xc0,2,u16)
    packed_vertices=arr(0xd0,4,u32)
    shared_vertices=arr(0xe0,8,u64)
    primitive_keys=u32(data,data_start+sh+0x90)
    domain_min=vec3(data,data_start+sh+0x70)
    domain_max=vec3(data,data_start+sh+0x80)
    bounds={'min':list(domain_min),'max':list(domain_max)}
    all_triangles=[]
    degenerate_keys=0
    for sec in sections:
        offset=vec3(sec,0x30)
        scale=vec3(sec,0x3c)
        first_packed=u32(sec,0x48)
        shared_ref=u32(sec,0x4c)
        primitive_ref=u32(sec,0x50)
        packed_n=sec[0x58]
        shared_n=sec[0x59]
        start_of_shared=shared_ref>>8
        if shared_ref&255!=packed_n:raise ValueError('inconsistent section packed/shared vertex counts')
        if first_packed+packed_n>len(packed_vertices) or start_of_shared+shared_n>len(shared_ids):raise ValueError('invalid section vertex indices')
        verts=[]
        for i in range(packed_n):
            v=packed_vertices[first_packed+i]
            code=(v&0x7ff,(v>>11)&0x7ff,(v>>22)&0x3ff)
            verts.append(tuple(offset[j]+code[j]*scale[j] for j in range(3)))
        for i in range(shared_n):
            index=shared_ids[start_of_shared+i]
            if index>=len(shared_vertices):raise ValueError('shared vertex index out of range')
            v=shared_vertices[index]
            code=(v&0x1fffff,(v>>21)&0x1fffff,(v>>42)&0x3fffff)
            verts.append(tuple(domain_min[j]+code[j]*(domain_max[j]-domain_min[j])/(0x3fffff if j==2 else 0x1fffff) for j in range(3)))
        first_primitive=primitive_ref>>8
        n_primitives=primitive_ref&255
        if first_primitive+n_primitives>len(primitives):raise ValueError('invalid section primitive count')
        for p in primitives[first_primitive:first_primitive+n_primitives]:
            a,b,c,d=p
            if max(a,b,c,d)>=len(verts):
                # Two vanilla BOTW files contain one dangling degenerate/sentinel
                # (222,173,222,173), which is not an actual collision face.
                if a==c and b==d:
                    degenerate_keys+=1
                    continue
                raise ValueError(f'primitive references vertex outside section: {list(p)} / {len(verts)}')
            all_triangles.append((*verts[a],*verts[b],*verts[c]))
            if d!=c:all_triangles.append((*verts[a],*verts[c],*verts[d]))
    if len(all_triangles)+degenerate_keys!=primitive_keys:
        raise ValueError(f'Havok triangle count mismatch: {len(all_triangles)}+{degenerate_keys} != {primitive_keys}')
    for t in all_triangles:
        if not all(math.isfinite(c) for c in t):raise ValueError('nonfinite triangle')
        for i,v in enumerate(t):
            k=i%3
            if not domain_min[k]-0.1<=v<=domain_max[k]+0.1:
                raise ValueError(f'collision coordinate outside bounding box {k}: {v}')
    return all_triangles,{'primitives':len(primitives),'triangle_keys':primitive_keys,'triangles':len(all_triangles),'degenerate_keys':degenerate_keys,'sections':len(sections),'bounds_local':bounds,'sdk':'hk_2014.2.0-r1'}


def inputs(source:Path):
    if source.is_dir():
        # Accept extracted RomFS root or Physics/TeraMeshRigidBody/MainField.
        for p in sorted(source.rglob('*.shktmrb')):
            yield p.name,p.read_bytes()
    elif source.suffix.lower()=='.zip':
        with zipfile.ZipFile(source) as z:
            for info in sorted(z.infolist(),key=lambda x:x.filename):
                if not info.is_dir() and info.filename.lower().endswith('.shktmrb'):
                    yield Path(info.filename).name,z.read(info)
    else:
        if source.name.lower().endswith('.shktmrb'):
            yield source.name,source.read_bytes()
        else:raise ValueError('need RomFS directory, shktmrb ZIP or shktmrb file')


def convert(source:Path,out:Path,verify:bool=False):
    out.mkdir(parents=True,exist_ok=True)
    tile_dir=out/'terrain'
    if not verify:tile_dir.mkdir(parents=True,exist_ok=True)
    tiles=[];started=time.monotonic()
    previous={}
    old_manifest=out/'terrain_manifest.json'
    if old_manifest.is_file() and not verify:
        try:
            previous={row['filename']:row for row in json.loads(old_manifest.read_text(encoding='utf-8')).get('tiles',[])}
        except (OSError,ValueError,KeyError):
            previous={}
    reused=0
    for name,raw in inputs(source):
        match=GRID_RE.fullmatch(name)
        if not match:raise ValueError(f'unknown tile name {name}')
        gx,gz=map(int,match.groups())
        if not (0<=gx<40 and 0<=gz<32):raise ValueError(f'unsupported tile indices {name}')
        digest=hashlib.sha256(raw).hexdigest()
        target=tile_dir/f'{gx:02}-{gz:02}.btri'
        old=previous.get(name,{})
        if (not verify and old.get('sha256')==digest and target.is_file()
                and target.stat().st_size==52+old.get('triangles',-1)*36):
            tiles.append(old);reused+=1
            if reused<=3:print(f'{name:<20} already converted, cache reused')
            continue
        faces,info=extract_terrain(raw)
        x_start=-5000+gx*250
        z_start=-4000+gz*250
        row={'filename':name,'gx':gx,'gz':gz,'world_x':x_start,'world_z':z_start,'sha256':digest,**info}
        if not verify:
            # BTRI v1: 4s magic, u32 version, i32 gx, i32 gz, u32 count,
            # i32 world_x, i32 world_z, 6 f32 local AABB, N*9 f32 triangles.
            # Local coordinates are kept intact; the host adds world_x/z.
            with target.open('wb') as fp:
                fp.write(struct.pack('<4sIiiIii6f',b'BTRI',1,gx,gz,len(faces),x_start,z_start,*info['bounds_local']['min'],*info['bounds_local']['max']))
                for t in faces:fp.write(struct.pack('<9f',*t))
            row['cache_file']=str(target.relative_to(out)).replace('\\','/')
        tiles.append(row)
        print(f'{name:<20} {len(faces):>7} triangles / {info["sections"]:>4} sections' + (' [verified]' if verify else ' [cached]'))
    summary={'tiles':len(tiles),'reused_cached_tiles':reused,'triangles':sum(x['triangles'] for x in tiles),'degenerate_keys':sum(x['degenerate_keys'] for x in tiles),'elapsed_seconds':round(time.monotonic()-started,2),'format':'BotwCraft BTRI v1','coordinate_grid':'40 x 32 tiles, 250 m; origin x=-5000, z=-4000','note':'geometry exported from game-owned physics files; mod integration required to use it'}
    manifest={'summary':summary,'tiles':tiles}
    path=out/'terrain_manifest.json'
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    print('\nDone:',summary,'\nManifest:',path)
    return manifest


def main(argv=None):
    ap=argparse.ArgumentParser(description='Convert BOTW Switch .shktmrb to exact collision mesh BTRI cache (no game assets included)')
    ap.add_argument('source',type=Path,help='RomFS directory OR ZIP with .shktmrb files')
    ap.add_argument('--output','-o',type=Path,default=Path('BotwCraft_TerrainCache'))
    ap.add_argument('--verify',action='store_true',help='verify only, do not write triangle cache')
    a=ap.parse_args(argv)
    if not a.source.exists():ap.error(f'input not found: {a.source}')
    convert(a.source,a.output,a.verify)

if __name__=='__main__':main()