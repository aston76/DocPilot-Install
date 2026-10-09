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
 def failure(*args,**kwargs):raise ValueError('Scanner disconnected')
 sc.bridge=failure;sc.worker('test');assert sc.snapshot()['status']=='error' and sc.snapshot()['pages']==2 and sc.snapshot()['pdf_available']
 sc._state['running']=True;assert client.post('/api/v1/system/quit',json={'quit':True}).status_code==409;assert client.post('/api/v1/scanner',json={'action':'reset'}).status_code==409;sc._state['running']=False
 assert client.post('/api/v1/scanner',json={'action':'reset'}).status_code==200
 assert client.get('/api/v1/scanner/pdf').status_code==404
 print('PASS: local scanner listing, origin protection, compressed multipage PDF, physical page sizing, cancel/error preservation, reset protection and isolated cleanup')
