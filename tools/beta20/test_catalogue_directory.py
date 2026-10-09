"""Complete folder recovery, idempotence, retired names and failure preservation."""
import sys,types,tempfile,importlib.util,time
from pathlib import Path
from sqlalchemy import create_engine,select,String,Boolean
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column,sessionmaker
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parent))
import docpilot_catalogue_directory as recovery
class Base(DeclarativeBase):pass
class LegalEntity(Base):
    __tablename__='legal_entities'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(128),unique=True)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
events=[]
sys.modules['app.domain']=types.SimpleNamespace(LegalEntity=LegalEntity)
sys.modules['app.pipeline.audit.logger']=types.SimpleNamespace(log_event=lambda *args,**kw:events.append(kw))
spec=importlib.util.spec_from_file_location('docpilot_workspace',Path(__file__).parent.parent/'beta11/docpilot_workspace.py')
w=importlib.util.module_from_spec(spec);sys.modules[spec.name]=w;spec.loader.exec_module(w)
def local(request):
    if request.headers.get('origin')=='https://bad.invalid':raise HTTPException(403,'Origin')
sys.modules['docpilot_inline_filing']=types.SimpleNamespace(local=local)
sys.modules['app.api']=types.SimpleNamespace(documents=types.SimpleNamespace(_archive=types.SimpleNamespace(_workspace_clear_catalogue=lambda:None)))
with tempfile.TemporaryDirectory() as temporary:
    base=Path(temporary);program=base/'program';program.mkdir();w.program_dir=lambda:program
    root=base/'Company'/w.LEAF
    (root/'Contrats'/'Contract Only').mkdir(parents=True)
    for number in range(36):(root/'Factures'/f'Supplier {number:02}'/'2026').mkdir(parents=True)
    engine=create_engine('sqlite:///'+str(base/'test.db'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine)
    def get_session():
        with factory() as session:yield session
    sys.modules['app.core.db']=types.SimpleNamespace(get_session=get_session)
    with factory() as session:
        for number in range(6):session.add(LegalEntity(name=f'Supplier {number:02}',active=number!=3))
        session.commit()
    w.save_catalogue({'root':str(root),'company':'Company','entries':[]})
    w._state.update(ready=True,root=str(root),company='Company')
    app=FastAPI();recovery.install(app)
    @app.get('/api/v1/legal-entities')
    def names():
        with factory() as session:return [{'name':row.name,'active':row.active} for row in session.scalars(select(LegalEntity)).all()]
    client=TestClient(app)
    def settled():
        for _ in range(500):
            result=recovery.snapshot()
            if not result['running']:return result
            time.sleep(.01)
        raise AssertionError('Recovery stalled')
    client.get('/api/v1/legal-entities');result=settled()
    assert result['status']=='complete' and result['added']==31 and result['discovered']==37,result
    rows=client.get('/api/v1/legal-entities').json();assert len(rows)==37
    assert next(row for row in rows if row['name']=='Supplier 03')['active'] is False
    assert any(event['detail']['location']==str(root/'Contrats'/'Contract Only') for event in events)
    client.post('/api/v1/catalogue-directory');result=settled();assert result['added']==0
    assert client.post('/api/v1/catalogue-directory',headers={'origin':'https://bad.invalid'}).status_code==403
    # Timeout preserves custom catalogue labels and all database rows.
    catalogue=w.read_catalogue();catalogue['entries'][0]['filename_label']='Custom';w.save_catalogue(catalogue)
    original=w.catalogue_for
    w.catalogue_for=lambda *args:(_ for _ in ()).throw(TimeoutError('offline'))
    client.post('/api/v1/catalogue-directory');result=settled()
    assert result['status']=='error' and len(client.get('/api/v1/legal-entities').json())==37
    assert w.read_catalogue()['entries'][0]['filename_label']=='Custom'
    w.catalogue_for=original
    # Invalid hints cannot create arbitrary database names or escape the archive.
    with factory() as session:
        result=recovery.reconcile(session,{'root':str(root),'entries':[{'supplier':'Injected','path':'../../Injected'}]})
        assert result['added']==0 and result['discovered']==0
    engine.dispose()
print('PASS: all 37 folder names recovered from six rows, inactive choice respected, exact audit paths, no duplicate names, origin protection and offline data preservation.')
