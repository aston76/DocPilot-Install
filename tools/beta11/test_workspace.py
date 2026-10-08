"""Isolated discovery/default tests; no production folders or database."""
import sys,tempfile,time,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import docpilot_workspace as w
class Storage:
    active=True
    def __init__(self,**values):self.__dict__.update(values)
class Select:
    def where(self,*args):return self
sys.modules['sqlalchemy']=types.SimpleNamespace(select=lambda *a:Select())
sys.modules['app.domain.system']=types.SimpleNamespace(StorageConfig=Storage)
class Session:
    storage=None
    commits=0
    def scalars(self,*a):return self
    def first(self):return self.storage
    def add(self,value):self.storage=value
    def commit(self):self.commits+=1
def archive(base,company='Example Sàrl'):
    root=base/company/w.LEAF
    for name in ['Factures','Contrats']:(root/name).mkdir(parents=True,exist_ok=True)
    return root
with tempfile.TemporaryDirectory() as temporary:
    base=Path(temporary);program=base/'program';program.mkdir();w.program_dir=lambda:program
    first=archive(base/'Drive');other=archive(base/'mapped')
    assert w.identity(first,'Example')
    assert not w.identity(first,'Other Company')
    assert not w.identity(first.parent,'Example')
    assert len(w.discover('Example',[base/'Drive',first]))==1
    original_roots=w.search_roots;w.search_roots=lambda:[base/'Drive']
    assert len(w.discover('Example'))==1,'Automatic roots must receive a separate probe deadline'
    w.search_roots=original_roots
    assert len(w.discover('Example',[base/'Drive',base/'mapped']))==2
    archive(base/'custom'/'Commun');assert len(w.discover('Example',[base/'custom']))==1
    session=Session();d=types.SimpleNamespace(_archive=types.SimpleNamespace())
    state=w.check(session,d,[base/'none'],force=True)
    assert state['state']=='missing' and not state['ready']
    state=w.check(session,d,[base/'Drive',base/'mapped'],force=True)
    assert state['state']=='ambiguous' and not state['ready']
    w.save_catalogue({'root':str(base/'another-PC'/'Example'/w.LEAF),'company':'Example','entries':[{'path':'Factures/Existing','supplier':'Existing'}]})
    state=w.check(session,d,[base/'Drive'],force=True)
    assert state['ready'] and state['root']==str(first.resolve())
    assert session.storage.root_path==str(first.resolve()) and session.storage.dry_run
    assert w.read_catalogue()['entries'][0]['supplier']=='Existing'
    count=session.commits;w.check(session,d,[],force=True);assert session.commits==count
    (first/'Contrats').rmdir()
    state=w.check(session,d,[],force=True);assert not state['ready']
    assert session.storage.root_path==str(first.resolve())
    started=time.monotonic()
    try:w.bounded(lambda:time.sleep(1),.03);raise AssertionError('Timeout expected')
    except TimeoutError:pass
    assert time.monotonic()-started<.5
    assert not list(base.rglob('*.pdf'))
print('PASS: mapped/local/custom Commun roots, identity, ambiguity, missing drive, stale path repair, persistent default, preserved catalogue, disconnected drive, bounded wait; no NAS writes.')
