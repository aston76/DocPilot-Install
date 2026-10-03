import pathlib, marshal, struct, zlib
root=pathlib.Path(__file__).resolve().parent
import zipfile, hashlib
with zipfile.ZipFile(root/'release-preparation/v0.1.0-beta.7/DocPilot-Windows-portable.zip') as base:
 data=base.read('DocPilot.exe')
assert hashlib.sha256(data).hexdigest()=='4ee3fb3537d07f1323934fc55f3212b4558f19255fd69955bfa12fd590771a56'
cookie=data.rfind(b'MEI\x0c\x0b\x0a\x0b\x0e')
magic,size,offset,length,version,library=struct.unpack('!8sIIII64s',data[cookie:cookie+88]);start=cookie+88-size
entries=[];pos=start+offset
while pos<start+offset+length:
 n,at,compressed,raw,flag,kind=struct.unpack('!iIIIBc',data[pos:pos+18]);entries.append([data[pos+18:pos+n],data[start+at:start+at+compressed],raw,flag,kind]);pos+=n
for entry in entries:
 if entry[4]!=b'z':continue
 pyz=zlib.decompress(entry[1]) if entry[3] else entry[1]
 toc=dict(marshal.loads(pyz[struct.unpack('!i',pyz[8:12])[0]:]));output=bytearray(pyz[:12]);new=[]
 for name,(kind,at,length) in toc.items():
  blob=pyz[at:at+length]
  if name=='app.main':
   code=zlib.decompress(blob)
   wrapper='import marshal as _inline_marshal\nexec(_inline_marshal.loads('+repr(code)+'),globals())\nimport docpilot_inline_filing\ndocpilot_inline_filing.install(app)\n'
   blob=zlib.compress(marshal.dumps(compile(wrapper,'app/main.py','exec')),6)
  if name=='docpilot_update':
   blob=zlib.compress(marshal.dumps(compile((root/'docpilot_update.py').read_text(encoding='utf-8'),'docpilot_update.py','exec')),6)
  new.append((name,(kind,len(output),len(blob))));output.extend(blob)
 blob=zlib.compress(marshal.dumps(compile((root/'docpilot_inline_filing.py').read_text(encoding='utf-8'),'docpilot_inline_filing.py','exec')),6)
 new.append(('docpilot_inline_filing',(0,len(output),len(blob))));output.extend(blob)
 toc_at=len(output);output.extend(marshal.dumps(new));output[8:12]=struct.pack('!i',toc_at)
 entry[1]=zlib.compress(bytes(output)) if entry[3] else bytes(output);entry[2]=len(output)
payload=bytearray();toc=bytearray()
for name,blob,raw,flag,kind in entries:
 toc.extend(struct.pack('!iIIIBc',18+len(name),len(payload),len(blob),raw,flag,kind)+name);payload.extend(blob)
newcookie=struct.pack('!8sIIII64s',magic,len(payload)+len(toc)+88,len(payload),len(toc),version,library)
(root/'release-preparation/v0.1.0-beta.8/DocPilot.exe').write_bytes(data[:start]+payload+toc+newcookie+data[cookie+88:])
# Only the queue component changes; preserve all previous controls.
js=root/'web/assets/index-CEFd-v_U.js';text=(root/'backup-before-inline-filing'/js.name).read_text(encoding='utf-8')
anchor='o.jsx("b",{children:doc.proposed_path||"Destination à confirmer"})'
assert text.count(anchor)==1
replacement='o.jsx("b",{children:doc.proposed_path||"Destination à confirmer"}),!archiveDuplicateFound(doc)&&doc.status==="TO_VALIDATE"&&(quickFilingReady(doc)?o.jsxs("details",{children:[o.jsx("summary",{children:"Modifier le dossier ici"}),o.jsx(InlineDestination,{doc,onChanged,simulation})]}):o.jsx(InlineDestination,{doc,onChanged,simulation}))'
text=text.replace(anchor,replacement)
text+='\n'+(root/'inline_destination.js').read_text(encoding='utf-8')
js.write_text(text,encoding='utf-8')
css=root/'web/assets/index-WlkB-kjt.css';text=(root/'backup-before-inline-filing'/css.name).read_text(encoding='utf-8')
css.write_text(text+'\n.pilot-inline-destination{display:grid;gap:8px;margin-top:10px}.pilot-inline-destination label{display:grid;gap:6px;font-size:13px}.pilot-inline-destination input{width:100%;box-sizing:border-box;padding:11px;border:1px solid #a7b7ad;border-radius:8px;font-size:14px}.pilot-inline-destination .pilot-primary{justify-self:start}.pilot-inline-destination small{overflow-wrap:anywhere}.pilot-quick-summary details summary{cursor:pointer;font-size:13px}\n',encoding='utf-8')
html=root/'web/index.html';html.write_text((root/'backup-before-inline-filing/index.html').read_text(encoding='utf-8').replace('updates-20261003','inline-filing-20261003'),encoding='utf-8')
print('Inline filing executable and queue prepared')
