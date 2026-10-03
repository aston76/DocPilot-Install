import sys, pathlib, marshal, importlib.abc, importlib.util, tempfile, hashlib, json
from types import SimpleNamespace as NS
root=pathlib.Path(__file__).resolve().parent
sys.path[:0]=[str(root/'tools/verification-deps'),str(root/'_internal')]
class Loader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
 def find_spec(self,fullname,path=None,target=None):
  file=root/'recovered'/(fullname+'.marshal')
  if file.exists():
   code=marshal.loads(file.read_bytes());return importlib.util.spec_from_loader(fullname,self,is_package=code.co_filename.endswith('__init__.py'))
 def create_module(self,spec):return None
 def exec_module(self,module):exec(marshal.loads((root/'recovered'/(module.__name__+'.marshal')).read_bytes()),module.__dict__)
sys.meta_path.insert(0,Loader())
from app.pipeline.act.filing import file_document
from fastapi import FastAPI
from fastapi.testclient import TestClient
import docpilot_inline_filing as inline
with tempfile.TemporaryDirectory() as folder:
 base=pathlib.Path(folder);nas=base/'nas';nas.mkdir();source=base/'invoice.pdf';source.write_bytes(b'%PDF-test invoice')
 digest=hashlib.sha256(source.read_bytes()).hexdigest()
 doc=NS(id=19,status='TO_VALIDATE',error_message=None,sha256=digest,legal_entity_id=1,creditor_id=2,invoice_date='2026-01-20',amount_minor=12345,currency='CHF',proposed_path=None,proposed_filename='Fournisseur Test.pdf',year=None,confidence={})
 supplier=NS(name='Fournisseur Test');creditor=NS(name='Viniwine');evidence={'matches':[]};dry=True
 class Store:
  def get(self,model,key):return {'document':doc,'supplier':supplier,'creditor':creditor,'source':None}.get(model)
  def commit(self):pass
  def rollback(self):pass
 store=Store()
 archive=NS(info=lambda doc:{'document_type':'invoice'},category=lambda kind:'Factures',resolve=lambda *a,**k:None,catalogue=lambda:{'company':'Viniwine'},key=lambda name:name.lower(),monetary_kind=lambda kind:True)
 def perform(session,doc,conflict):return file_document(source,nas/doc.proposed_path,doc.proposed_filename,digest,dry_run=dry,on_conflict=conflict)
 def mark(session,doc,path,digest,verified,replaced,automatic):doc.status='FILED'
 d=NS(Document='document',LegalEntity='supplier',Creditor='creditor',DocumentSource='source',get_session=lambda:store,_archive=archive,_filing_root=lambda session:nas,_safe_destination=lambda root,path:root/path,_duplicates=NS(lookup=lambda *a:evidence),_previous_perform_filing=perform,_mark_filed=mark,_to_out=lambda session,doc:{'status':doc.status,'dry_run':dry})
 app=FastAPI();inline.install(app,d);client=TestClient(app)
 url='/api/v1/documents/19/quick-filing'
 option=client.get(url).json();assert option['path']=='Factures/Fournisseur Test' and not option['exists']
 payload={'confirmed':True,'path':option['path'],'expected':option['expected']}
 assert client.post(url,json=payload,headers={'origin':'https://example.org'}).status_code==403
 for path in ('../escape','Factures/../../escape','C:/escape','Factures\\escape','Contrats/Boris','Factures//Boris'):
  assert client.post(url,json={**payload,'path':path}).status_code==422,path
 assert client.post(url,json={**payload,'confirmed':False}).status_code==422
 doc.amount_minor=400000;assert client.post(url,json=payload).status_code==409;doc.amount_minor=12345
 evidence['matches']=['existing.pdf'];assert client.post(url,json=payload).status_code==409;evidence['matches']=[]
 result=client.post(url,json=payload);assert result.status_code==200,result.text
 assert not (nas/'Factures').exists(),'Simulation must not create folders'
 assert client.post(url,json=payload).status_code==409,'A second click must not file twice'
 doc.status='TO_VALIDATE';doc.proposed_path=None;dry=False
 payload['expected']=inline.snapshot(doc)
 result=client.post(url,json=payload);assert result.status_code==200,result.text
 final=nas/'Factures/Fournisseur Test/Fournisseur Test.pdf';assert final.read_bytes()==source.read_bytes()
 doc.status='TO_VALIDATE';payload['expected']=inline.snapshot(doc)
 assert client.post(url,json=payload).status_code==409,'Do not replace an existing file'
 assert final.read_bytes()==source.read_bytes()
 assert doc.confidence['manual_destination']['detail']=='Factures/Fournisseur Test'
 print('Inline filing: suggestion, origin, traversal, stale data, SHA duplicate, simulation, explicit new folder, file hash, repeated click and no overwrite passed.')
