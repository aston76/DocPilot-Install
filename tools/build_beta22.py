"""Build beta.22 from the verified public beta.20 package; exclude local data."""
import hashlib,json,marshal,pathlib,struct,urllib.request,zipfile,zlib

ROOT=pathlib.Path(__file__).resolve().parent
SOURCES=ROOT/'beta22'
OUT=pathlib.Path('release-package22');OUT.mkdir(exist_ok=True)
BASE=ROOT.parent/'release-package21/beta20.zip'
BASE.parent.mkdir(parents=True,exist_ok=True)
BASE_SHA='789d0b0bd6c6dd52d871e58685a5c4793a0105c4adc5fcc4e8df901e7b801f93'
TAG='v0.1.0-beta.22'
if not BASE.exists():
 request=urllib.request.Request('https://github.com/aston76/DocPilot-Install/releases/download/v0.1.0-beta.20/DocPilot-Windows-portable.zip',headers={'User-Agent':'DocPilot-Build'})
 with urllib.request.urlopen(request,timeout=120) as response,BASE.open('wb') as output:
  while chunk:=response.read(1024*1024):output.write(chunk)
with BASE.open('rb') as handle:assert hashlib.file_digest(handle,'sha256').hexdigest()==BASE_SHA
with zipfile.ZipFile(BASE) as base:data=base.read('DocPilot.exe')
cookie=data.rfind(b'MEI\x0c\x0b\x0a\x0b\x0e')
magic,size,offset,length,version,library=struct.unpack('!8sIIII64s',data[cookie:cookie+88]);assert version==312
start=cookie+88-size;entries=[];pos=start+offset
while pos<start+offset+length:
 n,at,packed,raw,flag,kind=struct.unpack('!iIIIBc',data[pos:pos+18]);entries.append([data[pos+18:pos+n],data[start+at:start+at+packed],raw,flag,kind]);pos+=n
changed=[]
for entry in entries:
 if entry[4]!=b'z':continue
 pyz=zlib.decompress(entry[1]) if entry[3] else entry[1]
 toc=dict(marshal.loads(pyz[struct.unpack('!i',pyz[8:12])[0]:]));output=bytearray(pyz[:12]);new=[]
 for name,(kind,at,length) in toc.items():
  blob=pyz[at:at+length]
  if name=='docpilot_scanner':
   blob=zlib.compress(marshal.dumps(compile((SOURCES/(name+'.py')).read_text(encoding='utf-8-sig'),name+'.py','exec')),6);changed.append(name)
  elif name=='docpilot_update':
   source='import marshal as _beta22_marshal\nexec(_beta22_marshal.loads('+repr(zlib.decompress(blob))+'),globals())\nVERSION='+repr(TAG)+'\n_state.update(current=VERSION)\n'
   blob=zlib.compress(marshal.dumps(compile(source,'docpilot_update.py','exec')),6);changed.append(name)
  new.append((name,(kind,len(output),len(blob))));output.extend(blob)
 assert 'docpilot_escl' not in toc
 blob=zlib.compress(marshal.dumps(compile((SOURCES/'docpilot_escl.py').read_text(encoding='utf-8-sig'),'docpilot_escl.py','exec')),6)
 new.append(('docpilot_escl',(0,len(output),len(blob))));output.extend(blob);changed.append('docpilot_escl')
 at=len(output);output.extend(marshal.dumps(new));output[8:12]=struct.pack('!i',at)
 entry[1]=zlib.compress(bytes(output)) if entry[3] else bytes(output);entry[2]=len(output)
assert set(changed)=={'docpilot_scanner','docpilot_escl','docpilot_update'}
payload=bytearray();toc_out=bytearray()
for name,blob,raw,flag,kind in entries:
 toc_out.extend(struct.pack('!iIIIBc',18+len(name),len(payload),len(blob),raw,flag,kind)+name);payload.extend(blob)
exe=data[:start]+payload+toc_out+struct.pack('!8sIIII64s',magic,len(payload)+len(toc_out)+88,len(payload),len(toc_out),version,library)+data[cookie+88:]
(OUT/'DocPilot.exe').write_bytes(exe)
replace={'DocPilot.exe':exe,'version.json':(json.dumps({'version':TAG})+'\n').encode()}
asset='web/assets/index-CEFd-v_U.js'
with zipfile.ZipFile(BASE) as base:frontend=base.read(asset).decode('utf-8').replace('\r\n','\n')
old=(ROOT/'beta20/scanner_ui.js').read_text(encoding='utf-8').replace('export function','function',1).strip()
new=(SOURCES/'scanner_ui.js').read_text(encoding='utf-8').replace('export function','function',1).strip()
assert frontend.count(old)==1
replace[asset]=frontend.replace(old,new).encode('utf-8')
target=OUT/'DocPilot-Windows-portable.zip'
with zipfile.ZipFile(BASE) as base,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as result:
 for info in base.infolist():
  if info.filename not in replace:result.writestr(info,base.read(info))
 for name,blob in replace.items():result.writestr(name,blob)
forbidden={'escl-connections.json','archive-catalogue.json','archive-companies.json','docpilot.db','profile.sql','root-path.txt'}
with zipfile.ZipFile(target) as result:
 assert result.testzip() is None
 assert not any(pathlib.PurePosixPath(n).name in forbidden or n.endswith(('.der','.dpapi','.log')) or n.startswith('scanner/certificates/') for n in result.namelist())
sha=hashlib.file_digest(target.open('rb'),'sha256').hexdigest()
(OUT/(target.name+'.sha256')).write_text(sha+'  '+target.name+'\n',encoding='ascii')
(OUT/'verification.json').write_text(json.dumps({'tag':TAG,'sha256':sha,'bytes':target.stat().st_size,'modified_modules':changed,'private_files_excluded':True},indent=2),encoding='utf-8')
print(json.dumps({'tag':TAG,'sha256':sha,'bytes':target.stat().st_size}),flush=True)