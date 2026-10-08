import sys,tempfile,types,hashlib,os,time
from pathlib import Path
from contextlib import asynccontextmanager
sys.path.insert(0,str(Path(__file__).parent))
import docpilot_startup_sha as sha
@asynccontextmanager
async def lifespan(app):yield
with tempfile.TemporaryDirectory() as temporary:
    os.environ['LOCALAPPDATA']=temporary
    root=Path(temporary)/'Example'/'Fournisseurs-Créanciers';folder=root/'Factures';folder.mkdir(parents=True)
    selected=folder/'selected.pdf';selected.write_bytes(b'target')
    for i in range(400): (folder/f'other-{i}.pdf').write_bytes(b'unrelated')
    digest=hashlib.sha256(b'target').hexdigest();value=sha.fingerprint(selected.stat())+[digest]
    sha.index_store(root).save({'files':{'Factures/selected.pdf':value},'entries':{},'last_scan':'test'})
    key=sha.root_key(root);sha._requested.add(key);sha._states[key]={'phase':'complete','processed_files':1}
    archive=types.SimpleNamespace(catalogue=lambda:{'root':str(root),'company':'Example'})
    d=types.SimpleNamespace(_archive=archive,_mark_filed=lambda *a,**k:None)
    sys.modules['app.api']=types.SimpleNamespace(documents=d)
    sys.modules['docpilot_duplicates']=types.SimpleNamespace()
    sys.modules['docpilot_workspace']=types.SimpleNamespace(_state={'ready':True},apply_root=lambda:None,check=lambda:{'ready':False},identity=lambda *a:True,bounded=lambda fn,*args:fn())
    app=types.SimpleNamespace(router=types.SimpleNamespace(lifespan_context=lifespan))
    sha.install(app);duplicates=sys.modules['docpilot_duplicates']
    original=sha.read_hash;calls=[]
    def read(path,before):calls.append(path);return original(path,before)
    sha.read_hash=read
    result=duplicates.lookup(digest)
    assert result['matches']==['Factures/selected.pdf'] and not calls,'Unchanged verified match must not read any sibling or rehash'
    remote=folder/'remote.pdf';remote.write_bytes(b'remote');remote_digest=hashlib.sha256(b'remote').hexdigest()
    sha._remote[key]={remote_digest:{'Factures/remote.pdf'}}
    assert duplicates.lookup(remote_digest)['matches']==['Factures/remote.pdf']
    assert calls==[remote],'Only the matching peer candidate should be read'
    remote.unlink();result=duplicates.lookup(remote_digest)
    assert not result['matches'] and not result['verification_complete'] and result['peer_pending']
    # Successful filing is visible to the next lookup before a background scan.
    new=folder/'new.pdf';new.write_bytes(b'new');new_digest=hashlib.sha256(b'new').hexdigest()
    doc=types.SimpleNamespace(dry_run=False,final_path='Factures/new.pdf',sha256=new_digest)
    d._mark_filed(None,doc,'Factures/new.pdf',new_digest,True,False)
    assert duplicates.lookup(new_digest)['matches']==['Factures/new.pdf']
    assert 'Factures/new.pdf' in sha.index_store(root).find(new_digest)
print('PASS: no sibling reads among 400 files, no rehash of an unchanged verified candidate, verified remote hint, missing peer remains incomplete, immediate index update after filing.')
