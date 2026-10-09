import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import pymupdf
from fastapi import FastAPI
from fastapi.testclient import TestClient
import docpilot_scanner as scanner
import docpilot_escl as escl

with tempfile.TemporaryDirectory() as directory:
 folder=Path(directory)
 scanner.data_dir=lambda:folder
 scanner.supported=lambda:True
 device='escl-api:fixture'
 scanner._state.update(running=False,session=None,pages=0,status='idle',preview_pending=False)
 def acquire(action,target,selected,settings_folder):
  assert selected==device and settings_folder==folder
  if action=='probe':return {'available':True,'message':'API accessible'}
  target.mkdir(parents=True,exist_ok=True)
  with pymupdf.open() as pdf:
   page=pdf.new_page(width=595,height=842)
   page.insert_text((50,50),'Test local sans facture')
   pdf.save(target/'page.pdf')
  return {'pdf':True}
 app=FastAPI();scanner.install(app);client=TestClient(app)
 with patch.object(escl,'acquire',side_effect=acquire):
  assert scanner.probe(device)['available']
  scanner.worker(device)
  assert scanner.snapshot()['pages']==1 and scanner.preference()['default_device_id']==device
  response=client.get('/api/v1/scanner/preview')
  assert response.status_code==200 and response.headers['content-type']=='application/pdf'
  first=client.get('/api/v1/scanner/pdf').content
  scanner.worker(device)
  with pymupdf.open(stream=client.get('/api/v1/scanner/pdf').content,filetype='pdf') as pdf:
   assert len(pdf)==2 and abs(pdf[0].rect.width-595)<.1
 previous=client.get('/api/v1/scanner/pdf').content
 with patch.object(escl,'acquire',side_effect=ValueError('Certificat changé')):
  scanner.worker(device)
  assert scanner.snapshot()['status']=='error' and scanner.snapshot()['pages']==2
  assert client.get('/api/v1/scanner/pdf').content==previous
 assert client.post('/api/v1/scanner',json={'action':'scan','device':device},headers={'origin':'https://invalid.example'}).status_code==403
 assert not list(folder.rglob('page.pdf'))
 # A valid incoming PDF survives a failed commit instead of being discarded.
 with patch.object(escl,'acquire',side_effect=acquire), patch.object(scanner,'received_pdf',side_effect=OSError('Disque indisponible')):
  scanner.worker(device)
  assert list(folder.rglob('page.pdf'))
  assert client.get('/api/v1/scanner/pdf').content==previous
print('PASS: API routing, probe, PDF preview, multipage preservation, certificate failure, origin protection and failed-commit recovery')
