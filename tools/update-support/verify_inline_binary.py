import pathlib,sys,struct,marshal,zlib,importlib.abc,importlib.util
root=pathlib.Path(__file__).resolve().parent
sys.path[:0]=[str(root/'tools/verification-deps'),str(root/'_internal')]
data=(pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else root/'DocPilot.inline.exe').read_bytes();cookie=data.rfind(b'MEI\x0c\x0b\x0a\x0b\x0e')
_,size,offset,length,_,_=struct.unpack('!8sIIII64s',data[cookie:cookie+88]);start=cookie+88-size;pos=start+offset
while pos<start+offset+length:
 n,at,compressed,_,flag,kind=struct.unpack('!iIIIBc',data[pos:pos+18])
 if kind==b'z':pyz=zlib.decompress(data[start+at:start+at+compressed]) if flag else data[start+at:start+at+compressed]
 pos+=n
toc=dict(marshal.loads(pyz[struct.unpack('!i',pyz[8:12])[0]:]))
class Loader(importlib.abc.MetaPathFinder,importlib.abc.Loader):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.startswith(('app','docpilot_','multipart','python_multipart')) and fullname in toc:return importlib.util.spec_from_loader(fullname,self,is_package=toc[fullname][0]==1)
 def create_module(self,spec):return None
 def exec_module(self,module):
  _,at,length=toc[module.__name__];module.__file__=str(root/(module.__name__.replace('.','/')+'.py'));exec(marshal.loads(zlib.decompress(pyz[at:at+length])),module.__dict__)
sys.meta_path.insert(0,Loader())
from app.api import documents as d
from fastapi import FastAPI
import docpilot_inline_filing as inline
if len(sys.argv)>1:
 import docpilot_update
 assert docpilot_update.VERSION=='v0.1.0-beta.8'
for name in ('_previous_perform_filing','_mark_filed','_to_out','_archive','_duplicates','_safe_destination'):
 assert hasattr(d,name),name
app=FastAPI();inline.install(app)
paths=app.openapi()['paths'];assert '/api/v1/documents/{doc_id}/quick-filing' in paths
assert set(paths['/api/v1/documents/{doc_id}/quick-filing'])=={'get','post'}
print('Packaged backend loaded without server startup: existing filing engine and GET/POST route registration verified.')
import tempfile,hashlib,datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.domain.base import Base
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as folder:
 base=pathlib.Path(folder);nas=base/'nas';nas.mkdir();source=base/'invoice.pdf';source.write_bytes(b'%PDF-test')
 engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
 with Session(engine) as session:
  supplier=d.LegalEntity(name='Fournisseur Test');company=d.Creditor(name='Viniwine');session.add_all([supplier,company]);session.flush()
  doc=d.Document(sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_channel='MANUAL',received_at=datetime.datetime.now(datetime.timezone.utc),status='TO_VALIDATE',original_filename='test.pdf',legal_entity_id=supplier.id,creditor_id=company.id,invoice_date=datetime.date(2026,1,20),amount_minor=12345,currency='CHF',proposed_filename='Fournisseur Test.pdf',confidence={})
  session.add(doc);session.commit()
  d._filing_root=lambda session:nas;d._inbox_path=lambda doc:source;d._dry_run=lambda session:True
  d._duplicates.lookup=lambda *a:{'matches':[],'snapshot_at':None,'last_scan':None,'scan_errors':0,'algorithm':'SHA-256','source':'test'}
  app.dependency_overrides[d.get_session]=lambda:session
  client=TestClient(app);url=f'/api/v1/documents/{doc.id}/quick-filing';option=client.get(url).json()
  result=client.post(url,json={'confirmed':True,'path':option['path'],'expected':option['expected']})
  assert result.status_code==200,result.text
  assert result.json()['dry_run'] and result.json()['status']=='VALIDATED',result.text
  assert result.json()['final_path'].replace('\\','/')=='Factures/Fournisseur Test/Fournisseur Test.pdf',result.text
  assert not (nas/'Factures').exists()
  print('Actual packaged models, database, filing engine and response verified in isolated simulation.')
