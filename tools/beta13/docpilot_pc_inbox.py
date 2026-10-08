"""Explicit local discovery. Never imports or deletes a source automatically."""
import hashlib, json, os, re, socket, sqlite3, threading, time, uuid
from contextlib import contextmanager
from pathlib import Path

EXTENSIONS={'.pdf','.jpg','.jpeg','.png','.webp','.tif','.tiff','.heic','.heif','.doc','.docx','.xls','.xlsx','.odt','.ods'}
SKIP={'fournisseurs-créanciers','fournisseurs-creanciers','commun','windows','program files','program files (x86)','programdata','appdata','$recycle.bin','system volume information','.git','node_modules','docpilot-partage'}
WORDS=re.compile(r'\b(?:factur\w*|invoice\w*|rechnung\w*|fattur\w*)\b',re.I)
_lock=threading.RLock()
_cancel=threading.Event()
_state={'running':False,'phase':'idle','visited':0,'found':0,'errors':0,'message':'La recherche démarre uniquement sur votre demande.'}

def data_dir():
    from app.core.config import get_settings
    return Path(get_settings().data_dir)

@contextmanager
def database():
    folder=data_dir();folder.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(folder/'pc-inbox.sqlite3',timeout=10);db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,path TEXT UNIQUE,root TEXT,signature TEXT,sha TEXT,kind TEXT,status TEXT,matches TEXT,doc_id INTEGER,verified INTEGER,dismissed INTEGER DEFAULT 0,updated REAL)')
        db.execute('CREATE TABLE IF NOT EXISTS events(at REAL,action TEXT,path TEXT,sha TEXT,actor TEXT,device TEXT)')
        with db:yield db
    finally:db.close()

def signature(path):
    stat=path.stat()
    return [stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]

def digest_file(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()

def local_roots():
    if os.name=='nt':
        import ctypes
        kernel=ctypes.windll.kernel32;roots=[]
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            drive=letter+':\\'
            if kernel.GetDriveTypeW(drive)==3:roots.append(Path(drive))
        return roots
    return [Path.home()/name for name in ('Desktop','Documents','Downloads') if (Path.home()/name).is_dir()]

def synology_roots():
    if os.name!='nt':return []
    import subprocess,sys
    folder=Path(os.environ.get('LOCALAPPDATA',''))/'SynologyDrive'/'SystemFolders'
    if not folder.is_dir():return []
    # Synology exposes task roots through its own shortcuts, including custom
    # local folder names. No credentials or documents are read here.
    command="$s=New-Object -ComObject WScript.Shell; @((Get-ChildItem -LiteralPath '"+str(folder).replace("'","''")+"' -Filter '*.lnk' -Recurse -File | ForEach-Object {$s.CreateShortcut($_.FullName).TargetPath})) | ConvertTo-Json -Compress"
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        import ctypes
        values=json.loads(result.stdout.decode('cp'+str(ctypes.windll.kernel32.GetOEMCP())))
        if isinstance(values,str):values=[values]
        return [Path(v).resolve() for v in (values or []) if isinstance(v,str) and v]
    except (OSError,ValueError,subprocess.TimeoutExpired) as error:raise OSError('Les dossiers synchronisés Synology ne peuvent pas être identifiés ; recherche différée.') from error

def excluded_roots():
    roots=[data_dir().resolve(),*synology_roots()]
    try:
        import docpilot_workspace as w
        catalogue=w.read_catalogue()
        if catalogue and catalogue.get('root'):roots.append(Path(catalogue['root']).resolve())
        import docpilot_startup_sha as sha
        roots.extend(Path(record['root']).resolve() for record in list(sha._records.values()) if record.get('root'))
    except (ImportError,AttributeError):pass
    try:
        from app.core.db import get_engine
        from sqlalchemy import text
        with get_engine().connect() as db:
            for row in db.execute(text('SELECT root_path FROM storage_configs WHERE active=1')):
                if row[0]:roots.append(Path(row[0]).resolve())
    except Exception:pass
    return list(dict.fromkeys(roots))

def allowed(path,root,excluded=None):
    path=Path(path);root=Path(root)
    if path.is_symlink() or root.is_symlink():return False
    if os.name=='nt':
        try:
            if path.lstat().st_file_attributes&(0x400|0x1000):return False
        except OSError:return False
    resolved=path.resolve();base=root.resolve()
    if not resolved.is_relative_to(base):return False
    if os.name=='nt':
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(resolved.anchor)!=3:return False
        # Do not follow junctions or trigger downloads from cloud placeholders.
        try:
            if path.stat().st_file_attributes&0x400:return False
        except OSError:return False
    parts=[part.casefold() for part in resolved.parts]
    if any(part in SKIP or 'synology' in part or part=='synodrive' for part in parts):return False
    if any(resolved.is_relative_to(value) for value in (excluded if excluded is not None else excluded_roots())):return False
    return True

def classify(path):
    if WORDS.search(path.stem.replace('_',' ').replace('-',' ')):return 'invoice'
    if path.suffix.lower()=='.pdf':
        try:
            import pymupdf
            with pymupdf.open(path) as pdf:
                text='\n'.join(pdf[i].get_text()[:20000] for i in range(min(2,len(pdf))))
                if WORDS.search(text):return 'invoice'
                if len(text.strip())>100:return None
        except Exception:pass
    # Image-only PDFs, photos and Office files may be invoices. Keep them as
    # candidates for review rather than silently claiming they are invoices.
    return 'possible'

def verdict(digest):
    matches=[];verified=False;status='to_process';doc_id=None
    try:
        import docpilot_duplicates
        evidence=docpilot_duplicates.lookup(digest)
        matches=evidence.get('matches',[]);verified=bool(evidence.get('verification_complete'))
        if matches:status='duplicate'
    except (ImportError,OSError,ValueError):pass
    try:
        from app.core.db import get_engine
        from sqlalchemy import text
        with get_engine().connect() as db:
            row=db.execute(text('SELECT id,status,final_path,dry_run FROM documents WHERE sha256=:sha OR stored_sha256=:sha ORDER BY id DESC LIMIT 1'),{'sha':digest}).first()
            if not row:
                row=db.execute(text('SELECT d.id,d.status,d.final_path,d.dry_run FROM documents d JOIN document_sources s ON s.document_id=d.id WHERE s.source_sha256=:sha ORDER BY d.id DESC LIMIT 1'),{'sha':digest}).first()
        if row:
            doc_id=row[0]
            if not matches:status='processed' if row[1] in ('FILED','STORED','VALIDATED') and row[2] and not row[3] else 'imported'
    except Exception:pass
    return status,matches,doc_id,verified

def audit(action,row):
    actor=os.environ.get('USERNAME') or os.environ.get('USER') or 'Utilisateur local';device=socket.gethostname()
    with database() as db:db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(time.time(),action,row['path'],row['sha'],actor,device))
    try:
        from sqlalchemy.orm import Session
        from app.core.db import get_engine
        from app.pipeline.audit.logger import log_event
        with Session(get_engine()) as session:
            log_event(session,action,detail={'location':row['path'],'sha256':row['sha'],'actor_name':actor,'device_name':device})
            session.commit()
    except Exception:pass  # The dedicated local audit above remains durable.

def scan(roots=None):
    try:
        excluded=excluded_roots();roots=roots or local_roots()
        with database() as db:cached={row['path']:dict(row) for row in db.execute('SELECT * FROM candidates')}
        for root in roots:
            root=Path(root)
            if not allowed(root,root,excluded):continue
            def error(_error):
                with _lock:_state['errors']+=1
            for folder,dirs,files in os.walk(root,followlinks=False,onerror=error):
                if _cancel.is_set():break
                dirs[:]=[name for name in dirs if allowed(Path(folder)/name,root,excluded)]
                for name in files:
                    if _cancel.is_set():break
                    with _lock:_state['visited']+=1
                    if _state['visited']>200000:
                        _cancel.set();_state['message']='Recherche limitée à 200 000 fichiers ; résultat partiel.';break
                    path=Path(folder)/name
                    if path.suffix.lower() not in EXTENSIONS or not allowed(path,root,excluded):continue
                    try:
                        before=signature(path)
                        if before[0]>100*1024*1024:continue
                        key=str(path.resolve());old=cached.get(key)
                        same=old and json.loads(old['signature'])==before
                        if same and old['dismissed']:continue
                        kind=old['kind'] if same else classify(path)
                        if not kind:continue
                        digest=old['sha'] if same else digest_file(path)
                        if signature(path)!=before:continue
                        status,matches,doc_id,verified=verdict(digest)
                        identifier=old['id'] if old else uuid.uuid4().hex
                        with database() as db:
                            db.execute('INSERT OR REPLACE INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,0,?)',(identifier,key,str(root.resolve()),json.dumps(before),digest,kind,status,json.dumps(matches),doc_id,int(verified),time.time()))
                        with _lock:_state['found']+=1
                    except (OSError,ValueError):
                        with _lock:_state['errors']+=1
                if _cancel.is_set():break
            if _cancel.is_set():break
        with _lock:
            _state.update(phase='partial' if _cancel.is_set() or _state['errors'] else 'complete')
            if not _cancel.is_set():_state['message']=str(_state['found'])+' document(s) trouvé(s). Les fichiers originaux sont conservés.'
    except Exception:
        with _lock:_state.update(phase='error',message='Recherche interrompue. Vous pouvez réessayer.')
    finally:
        with _lock:_state['running']=False

def snapshot(offset=0,filter="all"):
    clause={"all":"","to_process":" AND status=\'to_process\'","duplicates":" AND status IN (\'duplicate\',\'processed\')"}.get(filter,"")
    offset=max(0,int(offset))
    with database() as db:
        rows=[dict(row) for row in db.execute('SELECT * FROM candidates WHERE dismissed=0'+clause+' ORDER BY updated DESC LIMIT 100 OFFSET ?',(offset,))]
        total=db.execute('SELECT COUNT(*) FROM candidates WHERE dismissed=0'+clause).fetchone()[0]
        events=[dict(row) for row in db.execute('SELECT * FROM events ORDER BY at DESC LIMIT 50')]
    for row in rows:
        row['matches']=json.loads(row['matches']);row.pop('signature',None);row.pop('root',None)
    with _lock:return dict(_state,items=rows,total=total,offset=offset,limit=100,events=events)

def candidate(identifier,validate=True):
    with database() as db:row=db.execute('SELECT * FROM candidates WHERE id=? AND dismissed=0',(identifier,)).fetchone()
    if not row:raise ValueError('Document introuvable dans la liste.')
    row=dict(row)
    if validate:
        if not allowed(Path(row['path']),Path(row['root'])):raise ValueError('Ce fichier ne peut pas être modifié : archive ou chemin déplacé.')
        if signature(Path(row['path']))!=json.loads(row['signature']):raise ValueError('Le fichier a changé depuis la recherche. Relancez la détection.')
    return row

def remove(identifier,delete_file=False):
    row=candidate(identifier,validate=delete_file)
    if delete_file:
        audit('pc_source_delete_requested',row)
        Path(row['path']).unlink()
    with database() as db:db.execute('UPDATE candidates SET dismissed=1 WHERE id=?',(identifier,))
    audit('pc_source_deleted' if delete_file else 'pc_candidate_dismissed',row)

def install(app):
    from fastapi import APIRouter,HTTPException,Request
    from fastapi.responses import FileResponse
    router=APIRouter()
    def local(request):
        if request.client and request.client.host not in ('127.0.0.1','::1','testclient'):raise HTTPException(403,'Accès local uniquement')
        if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'Origine refusée')
        origin=request.headers.get('origin')
        if origin and origin not in ('http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:3005','http://localhost:3005'):raise HTTPException(403,'Origine refusée')
    @router.get('/api/v1/pc-inbox')
    def status(request:Request,offset:int=0,filter:str="all"):
        local(request)
        if offset<0 or filter not in ("all","to_process","duplicates"):raise HTTPException(422,"Page invalide")
        return snapshot(offset,filter)
    @router.post('/api/v1/pc-inbox')
    async def start(request:Request):
        local(request)
        try:body=await request.json()
        except ValueError:raise HTTPException(422,'Demande invalide')
        if body=={'action':'cancel'}:_cancel.set();return snapshot()
        if body!={'action':'scan'}:raise HTTPException(422,'Action invalide')
        with _lock:
            if not _state['running']:
                _cancel.clear();_state.update(running=True,phase='scanning',visited=0,found=0,errors=0,message='Recherche sur les disques locaux, hors Synology et archives…')
                threading.Thread(target=scan,daemon=True,name='pc-invoice-discovery').start()
        return snapshot()
    @router.get('/api/v1/pc-inbox/{identifier}/file')
    def file(identifier:str,request:Request):
        local(request)
        try:row=candidate(identifier)
        except (ValueError,OSError) as error:raise HTTPException(409,str(error))
        audit('pc_candidate_opened_for_import',row)
        return FileResponse(row['path'],filename=Path(row['path']).name,content_disposition_type='inline')
    @router.post('/api/v1/pc-inbox/{identifier}/refresh')
    def refresh(identifier:str,request:Request):
        local(request)
        try:
            row=candidate(identifier)
            status,matches,doc_id,verified=verdict(row['sha'])
            with database() as db:db.execute('UPDATE candidates SET status=?,matches=?,doc_id=?,verified=? WHERE id=?',(status,json.dumps(matches),doc_id,int(verified),identifier))
        except (ValueError,OSError) as error:raise HTTPException(409,str(error))
        return snapshot()
    @router.post('/api/v1/pc-inbox/{identifier}/remove')
    async def delete(identifier:str,request:Request):
        local(request)
        try:body=await request.json()
        except ValueError:raise HTTPException(422,'Demande invalide')
        if body not in ({'delete_file':False},{'delete_file':True,'confirm':True}):raise HTTPException(422,'Choisissez explicitement le retrait ou la suppression du fichier.')
        try:remove(identifier,body['delete_file'])
        except (ValueError,OSError) as error:raise HTTPException(409,str(error))
        return snapshot()
    app.router.routes[0:0]=router.routes
