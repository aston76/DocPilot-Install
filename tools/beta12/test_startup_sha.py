"""Test index/cache/queue in temporary folders with no production database."""
import sys,types,tempfile,hashlib,threading,time,os,importlib.util
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
# Use the same verified workspace probe implementation shipped in beta.11.
workspace_path=Path(__file__).resolve().parent.parent/'beta11/docpilot_workspace.py'
spec=importlib.util.spec_from_file_location('docpilot_workspace',workspace_path)
w=importlib.util.module_from_spec(spec);sys.modules[spec.name]=w;spec.loader.exec_module(w)
sys.modules['docpilot_update']=types.SimpleNamespace(_state={'status':'current'})
import docpilot_startup_sha as sha
assert not sha.online_only(types.SimpleNamespace(st_file_attributes=0x40000,st_reparse_tag=0)), 'Extended attributes alone are not an online-only placeholder'
assert sha.online_only(types.SimpleNamespace(st_file_attributes=0x40000,st_reparse_tag=0x9000001A))
assert sha.online_only(types.SimpleNamespace(st_file_attributes=0x1000,st_reparse_tag=0))
def wait():
    deadline=time.monotonic()+5
    while sha._pending and time.monotonic()<deadline:time.sleep(.01)
    assert not sha._pending,'Scan did not finish'
with tempfile.TemporaryDirectory() as temporary:
    os.environ['LOCALAPPDATA']=temporary
    base=Path(temporary);roots=[]
    program=base/'program';program.mkdir();w.program_dir=lambda:program
    for company in ('Example','Other'):
        root=base/company/w.LEAF
        (root/'Factures').mkdir(parents=True);(root/'Contrats').mkdir();roots.append(root)
    first,second=roots
    (first/'Factures/a.pdf').write_bytes(b'%PDF test');(first/'Factures/unfinished.docpilot-part').write_bytes(b'partial')
    (second/'Factures/b.pdf').write_bytes(b'%PDF other')
    if os.name=='nt':
        import ctypes
        buffer=ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(str(base),buffer,len(buffer)):
            alias=Path(buffer.value)/'Example'/w.LEAF
            assert len(sha.files_in(alias)[0])==1,'8.3 parent aliases must not hide archive files'
    assert sha.request_scan(first)['phase']=='blocked';assert not sha._pending
    w._state.update(ready=True)
    entered=threading.Event();release=threading.Event();original=sha.read_hash;calls=[]
    def blocked(path,before):
        calls.append(path);entered.set();release.wait(3);return original(path,before)
    sha.read_hash=blocked
    sha.request_scan(first);assert entered.wait(5),{'state':sha.progress(first),'identity':w.identity(first,'Example'),'attributes':(first/'Factures/a.pdf').stat().st_file_attributes}
    assert sha.progress(first)['running'] and sha.progress(first)['total_files']==1
    sha.request_scan(first);assert len(sha._pending)==1,'Duplicate startup scan queued'
    sha.request_scan(second);assert len(sha._pending)==2
    release.set();wait();assert len(calls)==2
    assert sha.progress(first)['verification_complete'] and sha.progress(first)['percent']==100
    digest=hashlib.sha256(b'%PDF test').hexdigest()
    assert sha.record(first)['entries'][digest]==['Factures/a.pdf']
    assert digest not in sha.record(second)['entries'],'Company caches mixed'
    before=len(calls);sha.request_scan(first,once=False);wait();assert len(calls)==before,'Unchanged file rehashed'
    (first/'Factures/a.pdf').write_bytes(b'%PDF changed longer');sha.request_scan(first,once=False);wait()
    assert len(calls)==before+1 and digest not in sha.record(first)['entries']
    (first/'Factures/a.pdf').unlink();sha.request_scan(first,once=False);wait()
    assert not sha.record(first)['entries'] and sha.progress(first)['percent']==100
    (first/'Factures/a.pdf').write_bytes(b'bad')
    def failed(*args):raise OSError('Unreadable test file')
    sha.read_hash=failed;sha.request_scan(first,once=False);wait()
    assert sha.progress(first)['phase']=='partial' and not sha.progress(first)['verification_complete']
    assert sha.progress(first)['percent'] is None
    sha.read_hash=original
    # Periodic scan finds files/folders arriving from another Synology client.
    (second/'Factures/New supplier').mkdir();(second/'Factures/New supplier/new.pdf').write_bytes(b'new invoice')
    w.save_catalogue({'root':str(second),'company':'Other','entries':[{'path':'Factures/New supplier','category':'Factures','supplier':'New supplier','filename_label':'Custom label','aliases':['Alias'],'layout':'direct'}]})
    (second/'Factures/Another supplier').mkdir();(second/'Factures/Another supplier/extra.pdf').write_bytes(b'extra invoice')
    # Cache-clear import normally reaches the actual packaged API; use a stub here.
    api=types.ModuleType('app.api');api.documents=types.SimpleNamespace(_archive=types.SimpleNamespace())
    sys.modules['app.api']=api
    sha.refresh_requested();wait()
    assert sha.progress(second)['indexed_files']==3
    entries=w.read_catalogue()['entries']
    assert any(e['path']=='Factures/Another supplier' for e in entries)
    assert next(e for e in entries if e['path']=='Factures/New supplier')['aliases']==['Alias']
    # Missing archive must report an error and finish, not remain running.
    sha.request_scan(base/'missing',once=False);wait();assert sha.progress(base/'missing')['phase']=='error'
    assert (second/'Factures/b.pdf').read_bytes()==b'%PDF other'
print('PASS: startup guard, one background scan per root, real progress, queued companies, separate caches, unchanged-file reuse, modification/removal, partial/error states, no NAS writes.')
