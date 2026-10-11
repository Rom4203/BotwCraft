#!/usr/bin/env python3
"""Surgically patch EXACT test20's SkyClient.class without compiling/replacing gameplay classes.

Only changes two constant-pool UTF8 class owners, leaving every byte of all
method code, camera, player, commands and protocol unchanged. Checks source
hash to prevent applying to a different version.
"""
import hashlib,struct,sys,zipfile,io
from pathlib import Path
OLD_SHA='0a1cbd5387b42f955104c4f0df3cdcfd8cc0d3e15ad897b2cefd5ba689fee47b'
MAPPINGS={
 b'dev/skycraft/client/render/WorldExporter':b'dev/skycraft/client/BotwCraftPerf',
 b'dev/skycraft/client/FrameExporter':b'dev/skycraft/client/BotwCraftPerf',
}
def patch_class(data):
    assert data[:4]==b'\xca\xfe\xba\xbe'
    cp_count=struct.unpack_from('>H',data,8)[0]
    offset=10
    out=bytearray(data[:offset]);matches={k:0 for k in MAPPINGS}
    index=1
    while index<cp_count:
        tag=data[offset];offset+=1;out.append(tag)
        if tag==1:
            size=struct.unpack_from('>H',data,offset)[0];offset+=2
            payload=data[offset:offset+size];offset+=size
            if payload in MAPPINGS:
                matches[payload]+=1;payload=MAPPINGS[payload]
            out.extend(struct.pack('>H',len(payload)));out.extend(payload)
        else:
            size={3:4,4:4,5:8,6:8,7:2,8:2,9:4,10:4,11:4,12:4,15:3,16:2,17:4,18:4,19:2,20:2}.get(tag)
            if size is None:raise ValueError('Unknown CP tag '+str(tag))
            out.extend(data[offset:offset+size]);offset+=size
            if tag in (5,6):index+=1
        index+=1
    out.extend(data[offset:])
    if any(v!=1 for v in matches.values()):raise ValueError('Unsafe class owner multiplicity '+str(matches))
    return bytes(out)

def patch(jar,helper,dest):
    src=Path(jar).read_bytes();hash=hashlib.sha256(src).hexdigest()
    if hash!=OLD_SHA: raise ValueError('Refusing unknown gameplay JAR: '+hash)
    helperbytes=Path(helper).read_bytes()
    with zipfile.ZipFile(io.BytesIO(src)) as original, zipfile.ZipFile(dest,'w') as output:
        entries=original.infolist();names=[i.filename for i in entries]
        name='dev/skycraft/client/SkyClient.class'
        if names.count(name)!=1 or 'dev/skycraft/client/BotwCraftPerf.class' in names:
            raise ValueError('Unsupported JAR layout')
        for item in entries:
            contents=original.read(item)
            if item.filename==name:
                contents=patch_class(contents)
            # Keep original compression, timestamps, manifest, mods and entries.
            output.writestr(item,contents)
        output.writestr('dev/skycraft/client/BotwCraftPerf.class',helperbytes,compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(dest) as patched,zipfile.ZipFile(io.BytesIO(src)) as original:
        changes=[]
        for name in original.namelist():
            if original.read(name)!=patched.read(name):changes.append(name)
        if changes!=['dev/skycraft/client/SkyClient.class']:
            raise AssertionError('Unexpected changes to user working JAR: '+str(changes))
        assert patched.read('dev/skycraft/client/BotwCraftSession.class')==original.read('dev/skycraft/client/BotwCraftSession.class')
    print('OK: original V7 JAR verified',hash)
    print('OK: exactly two call-site owners redirected; every method bytecode and BotwCraftSession unchanged')
    print('NEW JAR',dest,'SHA256',hashlib.sha256(Path(dest).read_bytes()).hexdigest())
if __name__=='__main__':patch(*sys.argv[1:])
