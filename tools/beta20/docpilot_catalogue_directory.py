"""Recover missing directory rows from a verified local archive catalogue.

Windows retains its existing mapping: supplier folders are LegalEntity rows.
No invoice is read, no NAS directory is written, no retired row is reactivated.
"""
import threading,time,unicodedata
from pathlib import Path

_lock=threading.RLock()
_state={'running':False,'status':'idle','message':'Récupération des noms des dossiers en attente.','discovered':0,'added':0}
_checked=0

def name_key(value):return ' '.join(unicodedata.normalize('NFKC',value).split()).casefold()

def reconcile(session,catalogue):
    from sqlalchemy import select
    from app.domain import LegalEntity
    from app.pipeline.audit.logger import log_event
    existing={name_key(row.name) for row in session.scalars(select(LegalEntity)).all()}
    names={}
    skipped=0
    for entry in catalogue.get('entries',[]):
        name=entry.get('supplier')
        relative=entry.get('path')
        if not isinstance(name,str) or not isinstance(relative,str):continue
        parts=relative.replace('\\','/').split('/')
        if len(parts)!=2 or parts[0] not in ('Factures','Contrats','Douanes','Tarifs','Tarifs-Liste de prix fournisseurs') or parts[1]!=name or name in ('.','..') or '\\' in name:continue
        name=name.strip()
        if not name or len(name)>128 or any(ord(char)<32 for char in name):skipped+=1;continue
        names.setdefault(name_key(name),(name,relative))
    added=0
    for key,(name,relative) in names.items():
        if key in existing:continue
        session.add(LegalEntity(name=name,active=True))
        log_event(session,'entity_created',new_value=name,detail={'source':'archive_catalogue','location':str(Path(catalogue['root'])/relative)})
        existing.add(key);added+=1
    session.commit()
    return {'discovered':len(names),'added':added,'skipped':skipped}

def update_from_catalogue(catalogue):
    from app.core.db import get_session
    sessions=get_session()
    with _lock:
        try:
            result=reconcile(next(sessions),catalogue)
            _state.update(result,status='partial' if result['skipped'] else 'complete',message=f"{result['discovered']} nom(s) trouvés dans les dossiers · {result['added']} ajouté(s)."+(' Certains noms trop longs ou invalides restent à vérifier.' if result['skipped'] else ''))
            return result
        except Exception:
            _state.update(status='error',message='Récupération différée : le répertoire local n’a pas pu être actualisé. Réessayez. La liste existante est conservée.')
            raise
        finally:sessions.close()

def snapshot():
    with _lock:return dict(_state)

def begin(force=False):
    global _checked
    with _lock:
        if _state['running'] or (not force and time.monotonic()-_checked<300):return snapshot()
        _state.update(running=True,status='reading',message='Lecture des noms dans les dossiers configurés…',added=0)
    def worker():
        global _checked
        try:
            import docpilot_workspace as w
            with w._lock:
                current=w.read_catalogue()
                if not current or not w._state.get('ready') or not w.identity(current.get('root',''),current.get('company')):
                    raise ValueError('Dossier de travail indisponible. Vérifiez le stockage avant de récupérer les noms.')
                fresh=w.bounded(lambda:w.catalogue_for(current['root'],current['company']),5)
                # Commit only a complete traversal. A timeout/disconnection must
                # neither prune the catalogue nor import a partial traversal.
                entries={item['path']:item for item in current.get('entries',[])}
                for item in fresh['entries']:entries.setdefault(item['path'],item)
                updated=dict(current,entries=list(entries.values()))
                w.save_catalogue(updated)
                update_from_catalogue(fresh)
                from app.api import documents as d
                clear=getattr(d._archive,'_workspace_clear_catalogue',None)
                if clear:clear()
        except Exception:
            with _lock:_state.update(status='error',message='Récupération incomplète : vérifiez le dossier de travail et Synology Drive, puis réessayez. La liste existante est conservée.')
        finally:
            with _lock:_state['running']=False;_checked=time.monotonic()
    threading.Thread(target=worker,daemon=True,name='catalogue-directory-recovery').start()
    return snapshot()

def install(app):
    from fastapi import APIRouter,Request
    from docpilot_inline_filing import local
    router=APIRouter()
    @router.get('/api/v1/catalogue-directory')
    def status(request:Request):local(request);return snapshot()
    @router.post('/api/v1/catalogue-directory')
    def recover(request:Request):local(request);return begin(force=True)
    @app.middleware('http')
    async def recover_when_viewed(request,call_next):
        if request.method=='GET' and request.url.path=='/api/v1/legal-entities':
            try:local(request)
            except Exception:pass
            else:begin()
        return await call_next(request)
    app.router.routes[0:0]=router.routes
