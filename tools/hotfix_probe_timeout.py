import struct,zlib,marshal,pathlib,hashlib,sys
if sys.version_info[:2] != (3,12): raise RuntimeError('Python 3.12 required')
if len(sys.argv)!=3: raise SystemExit('Usage: python hotfix_probe_timeout.py ORIGINAL.exe OUTPUT.exe')
p=pathlib.Path(sys.argv[1])
output=pathlib.Path(sys.argv[2])
if p.resolve()==output.resolve() or output.exists(): raise RuntimeError('Choose a new output path')
b=p.read_bytes()
if hashlib.sha256(b).hexdigest()!='636321aca7a06d88c2ba30408a1e2b014174313e7ba6e79fe8dfbbb69ade123a': raise RuntimeError('Expected original beta.5 executable')
pos=b.rfind(b'MEI\x0c\x0b\x0a\x0b\x0e')
magic,size,off,length,version,lib=struct.unpack('!8sIIII64s',b[pos:pos+88]); start=pos+88-size
toc=b[start+off:start+off+length]; i=0; chunks=[]; entries=[]; cursor=0
while i<len(toc):
    n,entry,clen,ulen,compressed,kind=struct.unpack('!IIII B c',toc[i:i+18]); name=toc[i+18:i+n]; i+=n
    data=b[start+entry:start+entry+clen]
    if name.rstrip(b'\0')==b'launcher':
        raw=zlib.decompress(data) if compressed else data
        source=f'''import marshal as _repair_marshal, types as _repair_types
_repair_original_name=__name__
__name__="docpilot_launcher_repaired"
exec(_repair_marshal.loads({raw!r}),globals())
__name__=_repair_original_name
_repair_socket_factory=socket.socket
def _repair_probe_socket(*args,**kwargs):
    probe=_repair_socket_factory(*args,**kwargs)
    probe.settimeout(2.0)
    return probe
socket=_repair_types.SimpleNamespace(socket=_repair_probe_socket)
if __name__=="__main__":
    main()
'''
        raw=marshal.dumps(compile(source,'launcher.py','exec')); ulen=len(raw);data=zlib.compress(raw) if compressed else raw;clen=len(data)
    entries.append(struct.pack('!IIII B c',n,cursor,clen,ulen,compressed,kind)+name)
    chunks.append(data);cursor+=len(data)
newtoc=b''.join(entries); payload=b''.join(chunks)
cookie=struct.pack('!8sIIII64s',magic,len(payload)+len(newtoc)+88,len(payload),len(newtoc),version,lib)
output.write_bytes(b[:start]+payload+newtoc+cookie+b[pos+88:])
print(hashlib.sha256(output.read_bytes()).hexdigest())
