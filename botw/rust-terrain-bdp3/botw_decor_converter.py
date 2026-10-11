#!/usr/bin/env python3
"""Decode local BOTW .shksc static compound instances into tiled BTRI collision meshes.
Uses only standard Python, handles mesh, box, capsule and cylinder collision shapes.
ConvexVerticesShape support is intentionally deferred; never fabricates those collisions.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, os, re, struct, tempfile, time, zipfile
from pathlib import Path
from botw_collision_converter import yaz0, HKX_MAGIC, u16, u32, u64, vec3

GRID=250; X0=-5000; Z0=-4000

def u8(b,i):return b[i]
def float4(b,i):return struct.unpack_from('<4f',b,i)

def pack(data):
 h=data.find(b'__data__',0,512);ch=data.find(b'__classnames__',0,512)
 if h<0 or ch<0:raise ValueError('no Havok section header')
 ds=u32(data,h+20);local=u32(data,h+24);glob=u32(data,h+28);virt=u32(data,h+32);end=u32(data,h+36);cs=u32(data,ch+20)
 if ds+end>len(data)+8:raise ValueError('truncated Havok data')
 lf={u32(data,ds+i):u32(data,ds+i+4) for i in range(local,glob,8) if u32(data,ds+i)!=0xffffffff}
 gf={u32(data,ds+i):u32(data,ds+i+8) for i in range(glob,virt,12) if u32(data,ds+i)!=0xffffffff}
 objs={}
 for off in range(virt,min(end,len(data)-ds-12)+1,12):
  o,sec,n=struct.unpack_from('<3I',data,ds+off)
  if o==0xffffffff:break
  objs[o]=data[cs+n:cs+n+120].split(b'\0',1)[0].decode('ascii','replace')
 def arr(o,rel,size,reader):
  at=o+rel;n=u32(data,ds+at+8)&0x3fffffff
  if n>1_000_000:raise ValueError(('array count',hex(o),hex(rel),n))
  start=lf.get(at)
  if n and (start is None or start+n*size>local):raise ValueError(('array fixup',hex(o),hex(rel),n,start))
  return [] if not n else [reader(data,ds+start+i*size) for i in range(n)]
 return data,ds,objs,lf,gf,arr

def mesh(ctx,sh):
 data,ds,objs,lf,gf,arr=ctx
 secs=arr(sh,0xa0,96,lambda b,o:b[o:o+96]);prim=arr(sh,0xb0,4,lambda b,o:b[o:o+4])
 ids=arr(sh,0xc0,2,u16);packed=arr(sh,0xd0,4,u32);shared=arr(sh,0xe0,8,u64)
 bounds=[vec3(data,ds+sh+o) for o in (0x70,0x80)]
 faces=[]
 for sec in secs:
  off=vec3(sec,0x30);scale=vec3(sec,0x3c);first=u32(sec,0x48);sv=u32(sec,0x4c);pr=u32(sec,0x50)
  if sv&255!=sec[0x58] or first+sec[0x58]>len(packed) or (sv>>8)+sec[0x59]>len(ids):raise ValueError('bad Havok section vertex list')
  verts=[]
  for j in range(sec[0x58]):
   v=packed[first+j];code=(v&0x7ff,(v>>11)&0x7ff,(v>>22)&0x3ff)
   verts.append(tuple(off[k]+code[k]*scale[k] for k in range(3)))
  for j in range(sec[0x59]):
   v=shared[ids[(sv>>8)+j]];code=(v&0x1fffff,(v>>21)&0x1fffff,(v>>42)&0x3fffff)
   verts.append(tuple(bounds[0][k]+code[k]*(bounds[1][k]-bounds[0][k])/(0x3fffff if k==2 else 0x1fffff) for k in range(3)))
  start=pr>>8;n=pr&255
  if start+n>len(prim):raise ValueError('bad Havok section triangles')
  for p in prim[start:start+n]:
   a,b,c,d=p
   if max(p)>=len(verts):
    if a==c and b==d:continue
    raise ValueError('invalid Havok mesh vertex')
   faces.append((verts[a],verts[b],verts[c]))
   if c!=d:faces.append((verts[a],verts[c],verts[d]))
 return faces

def box(half):
 x,y,z=map(abs,half[:3]);v=[(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]
 faces=[]
 for a,b,c,d in [(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]:
  faces.extend([(v[a],v[b],v[c]),(v[a],v[c],v[d])])
 return faces

def tube(a,b,r,rings=12,hemisphere=False):
 # Cylinders and capsule trunks preserve their actual local axis and radius.
 if not 0.002<=r<=50:return []
 diff=tuple(b[i]-a[i] for i in range(3));length=math.sqrt(sum(q*q for q in diff))
 if length<1e-7:return []
 axis=tuple(q/length for q in diff);base=(0.,1.,0.) if abs(axis[1])<0.9 else (1.,0.,0.)
 u=(axis[1]*base[2]-axis[2]*base[1],axis[2]*base[0]-axis[0]*base[2],axis[0]*base[1]-axis[1]*base[0]);norm=math.sqrt(sum(q*q for q in u));u=tuple(q/norm for q in u)
 v=(axis[1]*u[2]-axis[2]*u[1],axis[2]*u[0]-axis[0]*u[2],axis[0]*u[1]-axis[1]*u[0])
 def ring(center,radius):return [tuple(center[k]+radius*(math.cos(i*2*math.pi/rings)*u[k]+math.sin(i*2*math.pi/rings)*v[k]) for k in range(3)) for i in range(rings)]
 out=[];one=ring(a,r);two=ring(b,r)
 for i in range(rings):
  j=(i+1)%rings;out.extend([(one[i],two[i],two[j]),(one[i],two[j],one[j])])
  if not hemisphere:out.extend([(a,one[j],one[i]),(b,two[i],two[j])])
 if hemisphere:
  # two true hemisphere caps (3 latitude rings) with end points
  for center,sign,first in [(a,-1,one),(b,1,two)]:
   last=first
   for t in (math.pi/6,math.pi/3):
    nxt=ring(tuple(center[k]+sign*r*math.sin(t)*axis[k] for k in range(3)),r*math.cos(t))
    for i in range(rings):
     j=(i+1)%rings;out.extend([(last[i],nxt[i],nxt[j]),(last[i],nxt[j],last[j])])
    last=nxt
   tip=tuple(center[k]+sign*r*axis[k] for k in range(3))
   for i in range(rings):out.append((last[i],tip,last[(i+1)%rings]))
 return out

def convex_hull(vertices):
 """Small exact 3D convex hull, no SciPy, handles shape vertices stored in Havok."""
 # Deduplicate packed SIMD coordinates before triangulation.
 points=[];seen=set()
 for p in vertices:
  if not all(math.isfinite(v) and abs(v)<100000 for v in p):continue
  key=tuple(round(v,5) for v in p)
  if key not in seen:seen.add(key);points.append(p)
 if len(points)<4:return []
 def sub(a,b):return tuple(a[i]-b[i] for i in range(3))
 def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
 def dot(a,b):return sum(a[i]*b[i] for i in range(3))
 a=0;b=max(range(1,len(points)),key=lambda i:dot(sub(points[i],points[a]),sub(points[i],points[a])))
 if b==a:return []
 c=max((i for i in range(len(points)) if i not in (a,b)),key=lambda i:dot(cross(sub(points[b],points[a]),sub(points[i],points[a])),cross(sub(points[b],points[a]),sub(points[i],points[a]))))
 normal=cross(sub(points[b],points[a]),sub(points[c],points[a]))
 d=max((i for i in range(len(points)) if i not in (a,b,c)),key=lambda i:abs(dot(normal,sub(points[i],points[a]))))
 if abs(dot(normal,sub(points[d],points[a])))<1e-8:return []
 interior=tuple((points[a][i]+points[b][i]+points[c][i]+points[d][i])/4 for i in range(3))
 def oriented(u,v,w):
  n=cross(sub(points[v],points[u]),sub(points[w],points[u]))
  return (u,w,v) if dot(n,sub(interior,points[u]))>0 else (u,v,w)
 hull=[oriented(a,b,c),oriented(a,c,d),oriented(a,d,b),oriented(b,d,c)]
 for idx in range(len(points)):
  if idx in (a,b,c,d):continue
  visible=[]
  for f in hull:
   u,v,w=f;n=cross(sub(points[v],points[u]),sub(points[w],points[u]))
   if dot(n,sub(points[idx],points[u]))>1e-6:visible.append(f)
  if not visible:continue
  border={}
  for u,v,w in visible:
   for edge in ((u,v),(v,w),(w,u)):
    reverse=(edge[1],edge[0]);
    if reverse in border:del border[reverse]
    else:border[edge]=None
  visible_ids=set(visible);hull=[f for f in hull if f not in visible_ids]
  for u,v in border:
   face=oriented(v,u,idx)
   edges=(sub(points[face[1]],points[face[0]]),sub(points[face[2]],points[face[0]]))
   n=cross(*edges)
   if dot(n,n)>1e-10:hull.append(face)
 return [(points[a],points[b],points[c]) for a,b,c in hull]

def convex(ctx,sh):
 data,ds,objs,lf,gf,arr=ctx
 num=u32(data,ds+sh+0x50)
 if not 4<=num<=256:return []
 matrices=arr(sh,0x40,48,lambda b,o:struct.unpack_from('<12f',b,o))
 verts=[]
 for m in matrices:
  for i in range(4):verts.append((m[i],m[4+i],m[8+i]))
 if len(verts)<num:raise ValueError('Havok convex vertex count mismatch')
 return convex_hull(verts[:num])

def shapes(ctx,ob,kind):
 data,ds,*_=ctx
 at=ds+ob
 if kind=='hkpBvCompressedMeshShape':return mesh(ctx,ob)
 if kind=='hkpBoxShape':return box(float4(data,at+32))
 if kind=='hkpCapsuleShape':return tube(vec3(data,at+32),vec3(data,at+48),struct.unpack_from('<f',data,at+24)[0],hemisphere=True)
 if kind=='hkpCylinderShape':return tube(vec3(data,at+48),vec3(data,at+64),struct.unpack_from('<f',data,at+28)[0])
 if kind=='hkpConvexVerticesShape':return convex(ctx,ob)
 return []

def transform(p,m):
 tx,ty,tz=m[:3];qx,qy,qz,qw=m[4:8];sx,sy,sz=m[8:11];x,y,z=p[0]*sx,p[1]*sy,p[2]*sz
 # Quaternion q v q^-1, normalized to tolerate roundoff.
 n=qx*qx+qy*qy+qz*qz+qw*qw
 if n<1e-8:raise ValueError('invalid instance quaternion')
 # Matrix from normalized quaternion, preserves negative scales in input.
 xx,yy,zz=qx*qx/n,qy*qy/n,qz*qz/n;xy,xz,yz=qx*qy/n,qx*qz/n,qy*qz/n;wx,wy,wz=qw*qx/n,qw*qy/n,qw*qz/n
 return (tx+(1-2*(yy+zz))*x+2*(xy-wz)*y+2*(xz+wy)*z,
         ty+2*(xy+wz)*x+(1-2*(xx+zz))*y+2*(yz-wx)*z,
         tz+2*(xz-wy)*x+2*(yz+wx)*y+(1-2*(xx+yy))*z)

def polygons(ctx):
 data,ds,objs,lf,gf,arr=ctx
 cache={};counts=collections.Counter()
 for ob,kind in objs.items():
  if kind!='hkpStaticCompoundShape':continue
  first=lf.get(ob+0x30);n=u32(data,ds+ob+0x38)&0x3fffffff
  if first is None or n>100000:continue
  for i in range(n):
   offset=first+i*80;shape=gf.get(offset+48);kind=objs.get(shape)
   if kind is None:counts['missing_shape']+=1;continue
   if kind not in ['hkpBvCompressedMeshShape','hkpBoxShape','hkpCapsuleShape','hkpCylinderShape','hkpConvexVerticesShape']:
    counts['skipped_'+kind]+=1;continue
   if shape not in cache:
    try:cache[shape]=shapes(ctx,shape,kind)
    except (ValueError,IndexError,struct.error,KeyError) as e:
     counts['shape_parse_error']+=1;cache[shape]=[];continue
   raw=cache[shape]
   if not raw:continue
   m=struct.unpack_from('<12f',data,ds+offset)
   if not all(math.isfinite(v) and abs(v)<1e6 for v in m):continue
   counts['instances_'+kind]+=1
   for tri in raw:
    try:face=tuple(transform(v,m) for v in tri)
    except ValueError:continue
    if all(math.isfinite(v) for p in face for v in p):yield face,counts

def clip_polygon(poly,axis,limit,keep_greater):
 def inside(p):return p[axis]>=limit-1e-5 if keep_greater else p[axis]<=limit+1e-5
 out=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  ina,inb=inside(a),inside(b)
  if ina!=inb:
   t=(limit-a[axis])/(b[axis]-a[axis]);out.append(tuple(a[j]+t*(b[j]-a[j]) for j in range(3)))
  if inb:out.append(b)
 return out

def split_face(face):
 xlo=min(v[0] for v in face);xhi=max(v[0] for v in face);zlo=min(v[2] for v in face);zhi=max(v[2] for v in face)
 gx0=math.floor((xlo-X0)/GRID);gx1=math.floor((xhi-X0)/GRID)
 gz0=math.floor((zlo-Z0)/GRID);gz1=math.floor((zhi-Z0)/GRID)
 if gx1-gx0>4 or gz1-gz0>4:return
 for gx in range(max(0,gx0),min(39,gx1)+1):
  for gz in range(max(0,gz0),min(31,gz1)+1):
   x=X0+gx*GRID;z=Z0+gz*GRID
   poly=list(face)
   for axis,v,g in [(0,x,True),(0,x+GRID,False),(2,z,True),(2,z+GRID,False)]:
    if poly:poly=clip_polygon(poly,axis,v,g)
   if len(poly)<3:continue
   for i in range(1,len(poly)-1):
    tri=(poly[0],poly[i],poly[i+1]);a,b,c=tri
    nx=(b[1]-a[1])*(c[2]-a[2])-(b[2]-a[2])*(c[1]-a[1]);ny=(b[2]-a[2])*(c[0]-a[0])-(b[0]-a[0])*(c[2]-a[2]);nz=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
    if nx*nx+ny*ny+nz*nz<1e-9:continue
    yield gx,gz,tuple((p[0]-x,p[1],p[2]-z) for p in tri)

def convert_one(name,raw):
 data=yaz0(raw) if raw.startswith(b'Yaz0') else raw
 offset=data.find(HKX_MAGIC,1)
 if offset<0:raise ValueError('missing embedded Havok collision objects')
 ctx=pack(data[offset:]);counts=collections.Counter();chunks=collections.defaultdict(bytearray);total=0
 for tri,c in polygons(ctx):
  counts=c
  for gx,gz,face in split_face(tri):
   chunks[gx,gz]+=struct.pack('<9f',*(v for p in face for v in p));total+=1
 return chunks,total,dict(counts)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('source',type=Path);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--limit',type=int,default=0);args=ap.parse_args()
 root=args.source
 if not root.is_dir():raise SystemExit('Expected an extracted RomFS directory')
 files=sorted(root.rglob('*.shksc'))
 if args.limit:files=files[:args.limit]
 if not files:raise SystemExit('No *.shksc found')
 out=args.output;target=out/'decor';target.mkdir(parents=True,exist_ok=True)
 # Incrementally build 250m bins without holding every static shape in memory.
 blobs=target/'partial';blobs.mkdir(exist_ok=True)
 manifest=target/'decor_manifest.json';prev={}
 if manifest.exists():
  try:prev={x['name']:x for x in json.loads(manifest.read_text())['sources']}
  except (ValueError,KeyError):pass
 sources=[];errors=[];start=time.monotonic();new=0
 for path in files:
  name=path.name;raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
  old=prev.get(name)
  if old and old['sha256']==digest and all((blobs/(f'{x}.bin')).exists() for x in old.get('blobs',[])):
   sources.append(old);print(f'{name} [cached]',flush=True);continue
  try:
   chunks,total,counts=convert_one(name,raw)
   chunk_names=[]
   for (gx,gz),payload in chunks.items():
    key=f'{gx:02}-{gz:02}_{name}';(blobs/(key+'.bin')).write_bytes(payload);chunk_names.append(key)
   if old:
    for key in old.get('blobs',[]):
     if key not in chunk_names:(blobs/(key+'.bin')).unlink(missing_ok=True)
   row={'name':name,'sha256':digest,'triangles':total,'objects':counts,'blobs':chunk_names}
   sources.append(row);new+=1
   print(f'{name:<25} {total:>8} collision triangles / {sum(v for k,v in counts.items() if k.startswith("instances_"))} objects',flush=True)
  except Exception as e:
   errors.append((name,str(e)));print(f'[WARN] {name}: {e}',flush=True)
   if old:sources.append(old)
  # Incremental manifest always, avoid losing progress on Ctrl+C.
  tmp=manifest.with_suffix('.json.tmp');tmp.write_text(json.dumps({'sources':sources,'errors':errors}));tmp.replace(manifest)
 # Write final BTRI to temporary file for every tile, preserving original terrain caches separately.
 buckets=collections.defaultdict(list)
 for row in sources:
  for key in row['blobs']:
   tile=key.split('_',1)[0];buckets[tile].append(key)
 for tile,keys in buckets.items():
  gx,gz=map(int,tile.split('-'));count=sum((blobs/(key+'.bin')).stat().st_size//36 for key in keys)
  final=target/(tile+'.btri');tmp=target/(tile+'.tmp')
  with tmp.open('wb') as f:
   f.write(struct.pack('<4sIiiIii6f',b'BTRI',1,gx,gz,count,X0+gx*GRID,Z0+gz*GRID,0,0,0,250,10000,250))
   for key in keys:
    with (blobs/(key+'.bin')).open('rb') as part:
     while data:=part.read(1024*1024):f.write(data)
  tmp.replace(final)
 print(f'[DECOR] {len(sources)} files processed, {len(buckets)} tiles, {len(errors)} errors, {time.monotonic()-start:.1f}s; updated={new}',flush=True)

if __name__=='__main__':main()