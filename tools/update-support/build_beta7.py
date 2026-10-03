"""Add the update API to beta.6 without altering its repaired launcher."""
import pathlib, struct, marshal, zlib, json, hashlib, shutil, zipfile
root=pathlib.Path(__file__).resolve().parent
with zipfile.ZipFile(root/'release-preparation/v0.1.0-beta.6/DocPilot-Windows-portable.zip') as source:
    data=source.read('DocPilot.exe')
assert hashlib.sha256(data).hexdigest()=='81e4103f7a138023766e59fe798f8110fc5ebff419eb079b8c289d4ceb1ab5c7'
cookie=data.rfind(b'MEI\x0c\x0b\x0a\x0b\x0e')
magic,size,offset,length,version,library=struct.unpack('!8sIIII64s',data[cookie:cookie+88]);start=cookie+88-size
entries=[];pos=start+offset
while pos<start+offset+length:
    n,at,compressed,raw,flag,kind=struct.unpack('!iIIIBc',data[pos:pos+18])
    entries.append([data[pos+18:pos+n],data[start+at:start+at+compressed],raw,flag,kind]);pos+=n
launcher_before=next(e[1] for e in entries if e[0].rstrip(b'\0')==b'launcher')
for entry in entries:
    if entry[0].rstrip(b'\0')==b'launcher':
        code=zlib.decompress(entry[1]) if entry[3] else entry[1]
        wrapper='import sys as _profile_sys, marshal as _profile_marshal\nif "--import-profile" in _profile_sys.argv:\n import docpilot_profile\n docpilot_profile.main()\nelse:\n exec(_profile_marshal.loads('+repr(code)+'),globals())\n'
        raw=marshal.dumps(compile(wrapper,'launcher.py','exec'))
        entry[1]=zlib.compress(raw) if entry[3] else raw;entry[2]=len(raw)
for entry in entries:
    if entry[4]!=b'z':continue
    pyz=zlib.decompress(entry[1]) if entry[3] else entry[1]
    toc=dict(marshal.loads(pyz[struct.unpack('!i',pyz[8:12])[0]:]));output=bytearray(pyz[:12]);new=[]
    for name,(kind,at,length) in toc.items():
        blob=pyz[at:at+length]
        if name=='app.main':
            code=marshal.loads(zlib.decompress(blob))
            wrapper='import marshal as _update_marshal\nexec(_update_marshal.loads('+repr(marshal.dumps(code))+'),globals())\nimport docpilot_update\ndocpilot_update.install(app)\n'
            blob=zlib.compress(marshal.dumps(compile(wrapper,code.co_filename,'exec')),6)
        new.append((name,(kind,len(output),len(blob))));output.extend(blob)
    for module in ['docpilot_update','docpilot_profile']:
        blob=zlib.compress(marshal.dumps(compile((root/(module+'.py')).read_text(encoding='utf-8'),module+'.py','exec')),6)
        new.append((module,(0,len(output),len(blob))));output.extend(blob)
    toc_at=len(output);output.extend(marshal.dumps(new));output[8:12]=struct.pack('!i',toc_at)
    entry[1]=zlib.compress(bytes(output)) if entry[3] else bytes(output);entry[2]=len(output)
payload=bytearray();toc=bytearray()
for name,blob,raw,flag,kind in entries:
    toc.extend(struct.pack('!iIIIBc',18+len(name),len(payload),len(blob),raw,flag,kind)+name);payload.extend(blob)
newcookie=struct.pack('!8sIIII64s',magic,len(payload)+len(toc)+88,len(payload),len(toc),version,library)
out=root/'release-preparation/v0.1.0-beta.7';out.mkdir(exist_ok=True)
(out/'DocPilot.exe').write_bytes(data[:start]+payload+toc+newcookie+data[cookie+88:])
patched_launcher=next(e for e in entries if e[0].rstrip(b'\0')==b'launcher')
launcher_code=marshal.loads(zlib.decompress(patched_launcher[1]) if patched_launcher[3] else patched_launcher[1])
assert (zlib.decompress(launcher_before) if patched_launcher[3] else launcher_before) in launcher_code.co_consts
js=root/'web/assets/index-CEFd-v_U.js';text=js.read_text(encoding='utf-8')
if 'function AppUpdateButton' not in text:
    text+='\n'+(root/'app_update_button.js').read_text(encoding='utf-8')
    anchor='o.jsx("button",{className:"pilot-quit",onClick:quitDocPilot,children:"Quitter"})'
    assert text.count(anchor)==1
    text=text.replace(anchor,'o.jsx(AppUpdateButton,{}),'+anchor)
    js.write_text(text,encoding='utf-8')
else:
    at=text.rfind('\nfunction AppUpdateButton')
    assert at>=0
    js.write_text(text[:at]+'\n'+(root/'app_update_button.js').read_text(encoding='utf-8'),encoding='utf-8')
css=root/'web/assets/index-WlkB-kjt.css'
text=css.read_text(encoding='utf-8')
if '.pilot-update-panel' not in text:
    text+='\n.pilot-update{position:relative}.pilot-update-button{font-size:13px;padding:8px 10px;border:1px solid #334155;border-radius:8px;background:transparent;color:inherit}.pilot-update-panel{position:absolute;right:0;top:44px;width:min(350px,90vw);background:#111827;color:#f8fafc;padding:18px;border:1px solid #475569;border-radius:12px;box-shadow:0 12px 28px #0006;z-index:100}.pilot-update-panel p{margin:10px 0;font-size:13px}.pilot-update-panel small{display:block;margin-bottom:12px;line-height:1.5}.pilot-update-panel button{padding:8px 12px;border-radius:8px}\n'
    css.write_text(text,encoding='utf-8')
html=root/'web/index.html';html.write_text(html.read_text(encoding='utf-8').replace('simple-ui-20261002','updates-20261003'),encoding='utf-8')
(root/'version.json').write_text(json.dumps({'version':'v0.1.0-beta.7'}),encoding='utf-8')
print('beta.7 prepared; beta.6 launcher preserved; update UI attached')
