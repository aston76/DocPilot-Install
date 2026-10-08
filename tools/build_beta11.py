"""Reproduce beta.11 from the public beta.10 package; no private data inputs."""
import hashlib,json,marshal,pathlib,struct,urllib.request,zipfile,zlib

ROOT=pathlib.Path(__file__).resolve().parent
SOURCES=ROOT/'beta11'
OUT=pathlib.Path('release-package');OUT.mkdir(exist_ok=True)
BASE=OUT/'beta10.zip'
BASE_SHA='b5bf587a5a4442269f1256e5538f63443123dd0244ced07e1faefe8038821c81'
TAG='v0.1.0-beta.11'
if not BASE.exists():
    request=urllib.request.Request('https://github.com/aston76/DocPilot-Install/releases/download/v0.1.0-beta.10/DocPilot-Windows-portable.zip',headers={'User-Agent':'DocPilot-Build'})
    with urllib.request.urlopen(request,timeout=120) as response,BASE.open('wb') as output:
        while chunk:=response.read(1024*1024):output.write(chunk)
assert hashlib.file_digest(BASE.open('rb'),'sha256').hexdigest()==BASE_SHA
with zipfile.ZipFile(BASE) as base:data=base.read('DocPilot.exe')
cookie=data.rfind(b'MEI\x0c\x0b\x0a\x0b\x0e')
magic,size,offset,length,version,library=struct.unpack('!8sIIII64s',data[cookie:cookie+88]);assert version==312
start=cookie+88-size;entries=[];pos=start+offset
while pos<start+offset+length:
    n,at,packed,raw,flag,kind=struct.unpack('!iIIIBc',data[pos:pos+18]);entries.append([data[pos+18:pos+n],data[start+at:start+at+packed],raw,flag,kind]);pos+=n
modules=['docpilot_dates','docpilot_diagnostics','docpilot_sync','docpilot_workspace','docpilot_auto_engine','docpilot_chatgpt','docpilot_update']
changed=[]
for entry in entries:
    if entry[4]!=b'z':continue
    pyz=zlib.decompress(entry[1]) if entry[3] else entry[1]
    toc=dict(marshal.loads(pyz[struct.unpack('!i',pyz[8:12])[0]:]));output=bytearray(pyz[:12]);new=[]
    for name,(kind,at,length) in toc.items():
        blob=pyz[at:at+length]
        if name in modules:
            source=(SOURCES/(name+'.py')).read_text(encoding='utf-8')
            blob=zlib.compress(marshal.dumps(compile(source,name+'.py','exec')),6);changed.append(name)
        elif name in ('app.main','app.pipeline.decide.heuristics'):
            extra='\nimport docpilot_diagnostics,docpilot_sync,docpilot_workspace\ndocpilot_diagnostics.install(app)\ndocpilot_sync.install(app)\ndocpilot_workspace.install(app)\n' if name=='app.main' else '\n'+(SOURCES/'invoice_date_patch.py').read_text(encoding='utf-8')
            source='import marshal as _beta11_marshal\nexec(_beta11_marshal.loads('+repr(zlib.decompress(blob))+'),globals())\n'+extra
            blob=zlib.compress(marshal.dumps(compile(source,name.replace('.','/')+'.py','exec')),6);changed.append(name)
        new.append((name,(kind,len(output),len(blob))));output.extend(blob)
    for name in modules:
        if name in toc:continue
        blob=zlib.compress(marshal.dumps(compile((SOURCES/(name+'.py')).read_text(encoding='utf-8'),name+'.py','exec')),6)
        new.append((name,(0,len(output),len(blob))));output.extend(blob);changed.append(name)
    at=len(output);output.extend(marshal.dumps(new));output[8:12]=struct.pack('!i',at)
    entry[1]=zlib.compress(bytes(output)) if entry[3] else bytes(output);entry[2]=len(output)
assert set(changed)==set(modules+['app.main','app.pipeline.decide.heuristics'])
payload=bytearray();toc_out=bytearray()
for name,blob,raw,flag,kind in entries:
    toc_out.extend(struct.pack('!iIIIBc',18+len(name),len(payload),len(blob),raw,flag,kind)+name);payload.extend(blob)
exe=data[:start]+payload+toc_out+struct.pack('!8sIIII64s',magic,len(payload)+len(toc_out)+88,len(payload),len(toc_out),version,library)+data[cookie+88:]
(OUT/'DocPilot.exe').write_bytes(exe)
replace={'DocPilot.exe':exe,'version.json':(json.dumps({'version':TAG})+'\n').encode()}
for name in ['web/index.html','web/assets/index-CEFd-v_U.js','web/assets/index-WlkB-kjt.css']:
    replace[name]=(SOURCES/name).read_bytes()
for name in ['Discover-DocPilotArchive.ps1','Find-DocPilotNAS.ps1','DocPilot-Update.ps1','Install-DocPilot.ps1','Installer-DocPilot.ps1','Installer-DocPilot.cmd']:
    replace[name]=(ROOT.parent/name).read_bytes()
target=OUT/'DocPilot-Windows-portable.zip'
with zipfile.ZipFile(BASE) as base,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as result:
    for info in base.infolist():
        if info.filename not in replace:result.writestr(info,base.read(info))
    for name,blob in replace.items():result.writestr(name,blob)
forbidden={'archive-catalogue.json','archive-companies.json','docpilot.db','profile.sql','schema.sql','root-path.txt','archive-sha256-index.json','archive-sha256-cache.json','synology-monitor-state.json'}
with zipfile.ZipFile(target) as result:
    assert result.testzip() is None
    assert not any(pathlib.PurePosixPath(name).name in forbidden or name.endswith(('.dpapi','.log')) or name.startswith(('deployment-profile/','archive-audit/','inbox/')) for name in result.namelist())
    for name,blob in replace.items():assert result.read(name)==blob
sha=hashlib.file_digest(target.open('rb'),'sha256').hexdigest()
(OUT/(target.name+'.sha256')).write_text(sha+'  '+target.name+'\n',encoding='ascii')
(OUT/'verification.json').write_text(json.dumps({'tag':TAG,'sha256':sha,'bytes':target.stat().st_size,'modified_modules':changed,'private_files_excluded':True},indent=2),encoding='utf-8')
print(json.dumps({'tag':TAG,'sha256':sha,'bytes':target.stat().st_size}))
