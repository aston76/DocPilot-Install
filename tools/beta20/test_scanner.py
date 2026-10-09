from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi import FastAPI
from fastapi.testclient import TestClient
import sys
sys.path.insert(0,str(Path(__file__).parent))
import docpilot_scanner as sc
import pymupdf
with TemporaryDirectory() as tmp:
 sc.data_dir=lambda:Path(tmp)
 sc.supported=lambda:True
 def fixture(action,folder,device=None):
  folder.mkdir(parents=True,exist_ok=True)
  if action=='list':return {'devices':[{'id':'test','name':'Test scanner'}]}
  pix=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,300,600),False);pix.clear_with(255);pix.save(folder/'page.png')
  return {'cancelled':False,'dpi':300}
 sc.bridge=fixture
 app=FastAPI();sc.install(app);client=TestClient(app)
 assert client.get('/api/v1/scanner/devices').json()['devices'][0]['id']=='test'
 assert client.post('/api/v1/scanner',json={'action':'scan','device':'test'},headers={'origin':'https://bad.invalid'}).status_code==403
 assert client.post('/api/v1/scanner',json={'action':'wrong'}).status_code==422
 sc.worker('test');first=client.get('/api/v1/scanner/pdf');assert first.status_code==200
 pdf=pymupdf.open(stream=first.content,filetype='pdf');assert len(pdf)==1 and abs(pdf[0].rect.width-72)<.1;pdf.close()
 sc.worker('test');assert sc.snapshot()['pages']==2
 pdf=pymupdf.open(stream=client.get('/api/v1/scanner/pdf').content,filetype='pdf');assert len(pdf)==2;pdf.close()
 sc.bridge=lambda *args,**kwargs:{'cancelled':True};sc.worker('test');assert sc.snapshot()['pages']==2
 assert '2 page(s)' in sc.snapshot()['message'] and 'annulée' not in sc.snapshot()['message']
 sc._state['running']=True
 assert client.get('/api/v1/scanner/preview').content==client.get('/api/v1/scanner/preview').content
 assert client.get('/api/v1/scanner/preview').status_code==200
 assert client.get('/api/v1/scanner/pdf').status_code==409
 sc._state['running']=False
 def failure(*args,**kwargs):raise ValueError('Scanner disconnected')
 sc.bridge=failure;sc.worker('test');assert sc.snapshot()['status']=='error' and sc.snapshot()['pages']==2 and sc.snapshot()['pdf_available']
 sc._state['running']=True;assert client.post('/api/v1/system/quit',json={'quit':True}).status_code==409;assert client.post('/api/v1/scanner',json={'action':'reset'}).status_code==409;sc._state['running']=False
 assert client.post('/api/v1/scanner',json={'action':'reset'}).status_code==200
 assert client.get('/api/v1/scanner/pdf').status_code==404
 assert client.get('/api/v1/scanner/preview').status_code==404
 sc.bridge=lambda *args,**kwargs:{'cancelled':True};sc.worker('test')
 assert sc.snapshot()['pages']==0 and not sc.snapshot()['preview_available']
 assert 'Aucune page reçue' in sc.snapshot()['message'] and 'conservées' not in sc.snapshot()['message']
 # Some drivers report cancellation after delivering a valid image. Keep the evidence.
 def delivered(action,folder,device=None):
  fixture(action,folder,device);return {'cancelled':True,'dpi':300}
 sc.bridge=delivered;sc.worker('test');assert sc.snapshot()['pages']==1 and sc.snapshot()['preview_available']
 assert client.get('/api/v1/scanner/preview').status_code==200
 assert client.get('/api/v1/scanner/preview',headers={'origin':'https://bad.invalid'}).status_code==403
 # A received raster is visible before PDF completion, without consuming it.
 sc._state.update(status='preparing',running=True)
 received=client.get('/api/v1/scanner/preview');assert received.status_code==200 and received.headers['content-type']=='image/jpeg'
 sc._state.update(status='ready',running=False)
 assert client.get('/api/v1/scanner/preview').headers['cache-control']=='no-store'
 sc.reset()
 print('PASS: local scanner listing, origin protection, compressed multipage PDF, physical page sizing, cancel/error preservation, reset protection and isolated cleanup')

with TemporaryDirectory() as tmp:
 sc.data_dir=lambda:Path(tmp)
 entries=[{'id':'wrong','name':'MA3500','connection':'WSD-old'},{'id':'right','name':'MA3500','connection':'USB'},{'id':'right','name':'MA3500','connection':'USB'}]
 items,preferred=sc.normalize_devices(entries)
 assert len(items)==2 and preferred is None
 assert len({d['label'] for d in items})==2
 sc.remember('right')
 items,preferred=sc.normalize_devices(entries)
 assert preferred=='right' and items[0]['id']=='right'
 assert sc.preference()['default_device_id']=='right'
 items,preferred=sc.normalize_devices([{'id':'new','name':'Other','windows_default':True}])
 assert preferred=='new', 'Absent saved scanner must fall back only to an unambiguous default'
 sc.bridge=lambda *args,**kwargs:{'available':True,'message':'Connected'}
 assert sc.probe('right')['available']
 assert not sc._state.get('probing')
 sc.bridge=lambda *args,**kwargs:(_ for _ in ()).throw(ValueError('offline'))
 assert not sc.probe('wrong')['available']
 assert not sc._state.get('probing')
 app=FastAPI();sc.install(app);client=TestClient(app)
 assert client.post('/api/v1/scanner',json={'action':'select','device':'right'}).status_code==200
 assert sc.preference()['default_device_id']=='right'
 assert client.post('/api/v1/scanner',json={'action':'probe','device':'right'},headers={'origin':'https://bad.invalid'}).status_code==403
print('PASS: distinct connections, exact duplicate IDs removed, persistent preferred scanner, default fallback, connection checks and origin protection.')

with TemporaryDirectory() as tmp:
 sc.data_dir=lambda:Path(tmp)
 entries=[{'id':'a-same-suffix','name':'MA3500','connection':'WSD'},{'id':'b-same-suffix','name':'MA3500','connection':'WSD'}]
 devices,preferred=sc.normalize_devices(entries)
 assert len({d['label'] for d in devices})==2, 'Same port descriptions must still have distinct visible labels'
print('PASS: scanner labels remain distinct even when Windows reports identical ports.')
assert 'hors ligne' in sc.driver_error('0x80210005')
assert 'préchauffage' in sc.driver_error('0x80210007')
assert 'Aucune feuille' in sc.driver_error('0x80210003')
assert 'Code pilote' in sc.driver_error('0xDEADBEEF')
assert "$true)" in sc._SCRIPT and 'for($attempt=0;$attempt -lt 2;' in sc._SCRIPT
print('PASS: empty acquisition is not reported as duplicate/cancellation, actual image kept, busy preview stays readable, stable PDF export guarded, driver diagnostics.')
