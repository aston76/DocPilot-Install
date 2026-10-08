"""Resolve and verify archive identity before any filing, on each workstation."""
import json,os,subprocess,sys,threading,time,unicodedata,re,queue
from contextvars import copy_context
from pathlib import Path
from functools import wraps
from contextlib import asynccontextmanager

LEAF='Fournisseurs-Créanciers'
_lock=threading.RLock()
_state={'state':'checking','ready':False,'root':None,'message':'Vérification du dossier de travail…','choices':[]}
_checked=0
_checking=threading.Lock()

def key(value):
    text=unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower()
    text=re.sub(r'\b(?:sa|sarl|srl|ag|gmbh|ltd)\b','',text)
    return re.sub(r'[^a-z0-9]','',text)

def program_dir():
    return Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def data_dir():
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'DocPilot'

def bounded(call,seconds=2):
    result=queue.Queue(maxsize=1);context=copy_context()
    def worker():
        try:result.put((True,context.run(call)))
        except Exception as error:result.put((False,error))
    threading.Thread(target=worker,daemon=True,name='archive-probe').start()
    try:ok,value=result.get(timeout=seconds)
    except queue.Empty:raise TimeoutError('Le dossier réseau ne répond pas.')
    if not ok:raise value
    return value

def identity(root,company=None):
    try:return bounded(lambda:_identity(root,company))
    except (OSError,ValueError):return False

def _identity(root,company=None):
    root=Path(root)
    try:
        if key(root.name)!=key(LEAF) or not root.is_dir() or root.is_symlink():return False
        if company and key(root.parent.name)!=key(company):return False
        categories={key(p.name) for p in root.iterdir() if p.is_dir() and not p.is_symlink()}
        return key('Factures') in categories and bool(categories & {key(v) for v in ('Contrats','Douanes','Tarifs','Tarifs-Liste de prix fournisseurs')})
    except OSError:return False

def search_roots():
    roots=[Path.home()/'SynologyDrive',Path.home()/'Commun']
    script=program_dir()/'Discover-DocPilotArchive.ps1'
    if os.name=='nt' and script.is_file():
        try:
            result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],capture_output=True,timeout=12,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode==0:
                # Windows PowerShell stdout uses the active console encoding.
                import ctypes
                encoding='cp'+str(ctypes.windll.kernel32.GetOEMCP())
                values=json.loads(result.stdout.decode(encoding))
                roots.extend(Path(value) for value in values)
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
    return list(dict.fromkeys(roots))

def discover(company=None,roots=None):
    found={};deadline=time.monotonic()+12
    def probe(base):
        if not base.is_dir():return []
        leaves=(LEAF,'Fournisseurs-Creanciers')
        candidates=[base]+[base/leaf for leaf in leaves]
        for scope in (base,base/'Commun'):
            if not scope.is_dir():continue
            if company:candidates.extend(scope/company/leaf for leaf in leaves)
            for index,child in enumerate(scope.iterdir()):
                if index>=300:break
                if child.is_dir() and not child.is_symlink():candidates.extend(child/leaf for leaf in leaves)
        return [{'root':str(candidate.resolve()),'company':candidate.parent.name} for candidate in candidates if _identity(candidate,company)]
    for value in roots if roots is not None else search_roots():
        if time.monotonic()>=deadline:break
        try:
            for choice in bounded(lambda:probe(Path(value)),min(2,max(.01,deadline-time.monotonic()))):
                found[os.path.normcase(choice['root'])]=choice
        except (OSError,ValueError):continue
    return list(found.values())

def read_catalogue():
    path=program_dir()/'archive-catalogue.json'
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return None

def catalogue_for(root,company):
    entries=[]
    for category in ('Factures','Contrats','Douanes','Tarifs','Tarifs-Liste de prix fournisseurs'):
        folder=Path(root)/category
        if not folder.is_dir():continue
        for supplier in folder.iterdir():
            if supplier.is_dir() and not supplier.is_symlink():
                entries.append({'path':category+'/'+supplier.name,'category':category,'supplier':supplier.name,'filename_label':supplier.name,'aliases':[supplier.name],'layout':'year' if any(p.is_dir() and p.name.isdigit() and len(p.name)==4 for p in supplier.iterdir()) else 'direct'})
    return {'root':str(root),'company':company,'entries':entries}

def save_catalogue(record):
    path=program_dir()/'archive-catalogue.json'
    pending=path.with_suffix('.json.pending')
    pending.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(pending,path)

def apply_root(session,d,root,company,catalogue):
    from sqlalchemy import select
    root=Path(root).resolve()
    if not identity(root,company):raise ValueError('Ce dossier ne correspond pas à l’archive attendue de '+company+'.')
    record=dict(catalogue or catalogue_for(root,company),root=str(root),company=company)
    # Only the local storage configuration changes; the NAS is read-only here.
    from app.domain.system import StorageConfig
    storage=session.scalars(select(StorageConfig).where(StorageConfig.active==True)).first()
    if storage:
        storage.root_path=str(root);storage.provider_type='local'
    else:
        storage=StorageConfig(name='Archive '+company,provider_type='local',root_path=str(root),dry_run=True,active=True)
        session.add(storage)
    save_catalogue(record)
    session.commit()
    # The company wrapper retains the original LRU cache in a closure.
    clear=getattr(d._archive,'_workspace_clear_catalogue',None)
    if clear:clear()
    _state.update(state='ready',ready=True,root=str(root),company=company,message='Dossier vérifié : '+str(root),choices=[])

def check(session,d,roots=None,force=False):
    global _checked
    with _lock:
        if not force and time.monotonic()-_checked<10:return dict(_state)
        _checked=time.monotonic()
        catalogue=read_catalogue()
        company=(catalogue or {}).get('company')
        expected=(catalogue or {}).get('root')
        if expected and identity(expected,company):
            if _state.get('ready') and _state.get('root')==str(Path(expected).resolve()):return dict(_state)
            apply_root(session,d,expected,company,catalogue)
            return dict(_state)
        choices=discover(company,roots)
        if len(choices)==1:
            apply_root(session,d,choices[0]['root'],choices[0]['company'],catalogue)
        else:
            _state.update(state='ambiguous' if choices else 'missing',ready=False,root=None,company=company,choices=choices,
                message='Plusieurs archives correspondent. Choisissez le dossier de cette société avant de classer.' if choices else 'Archive de travail introuvable ou incorrecte. Vérifiez le lecteur réseau ou Synology Drive, puis relancez la détection.')
        return dict(_state)

def install(app):
    from app.api import documents as d
    from fastapi import APIRouter,Depends,Request,HTTPException
    from docpilot_inline_filing import local
    from starlette.responses import JSONResponse
    # Find and retain the original cached catalogue function beneath wrappers.
    def find_cache(fn,seen=None):
        seen=seen or set()
        if id(fn) in seen:return None
        seen.add(id(fn))
        if hasattr(fn,'cache_clear'):return fn.cache_clear
        for cell in getattr(fn,'__closure__',[]) or []:
            value=cell.cell_contents
            if callable(value):
                result=find_cache(value,seen)
                if result:return result
    d._archive._workspace_clear_catalogue=find_cache(d._archive.catalogue)
    original_catalogue=d._archive.catalogue
    def portable_catalogue():
        try:
            record=bounded(original_catalogue)
            if not record or identity(record.get('root',''),record.get('company')):return record
        except (OSError,ValueError):record=None
        # Repair company-specific paths too, without changing another company's root.
        import docpilot_companies
        selected=docpilot_companies._company.get()
        base=read_catalogue()
        if not selected or (base and key(selected)==key(base['company'])):return record or base
        choices=discover(selected)
        if len(choices)==1:
            profile_path=program_dir()/'archive-companies.json'
            try:profiles=json.loads(profile_path.read_text(encoding='utf-8-sig'))
            except (OSError,ValueError):profiles={}
            profiles[selected]={'root':choices[0]['root']}
            pending=profile_path.with_suffix('.json.pending')
            with _lock:
                pending.write_text(json.dumps(profiles,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(pending,profile_path)
            return catalogue_for(choices[0]['root'],selected)
        return {'root':str(program_dir()/'archive-not-configured'), 'company':selected,'entries':[]}
    d._archive.catalogue=portable_catalogue
    original_root=d._filing_root
    @wraps(original_root)
    def verified_root(session):
        # Revalidate even after startup: a disconnected/replaced drive must fail.
        try:
            catalogue=d._archive.catalogue()
            if not catalogue:raise ValueError('Archive non configurée')
            root=Path(catalogue['root'])
            if not identity(root,catalogue.get('company')):raise ValueError('Le dossier de travail ne correspond plus à l’archive attendue.')
            return root.resolve()
        except (OSError,ValueError,KeyError) as error:
            raise HTTPException(423,{'code':'workspace_invalid','message':str(error)+' Ouvrez Dossier de travail et relancez la détection.'}) from None
    d._filing_root=verified_root
    @app.middleware('http')
    async def protect_work(request,call_next):
        guarded=request.method=='POST' and (request.url.path=='/api/v1/documents/upload' or request.url.path.endswith(('/reanalyze','/reclassify','/validate','/quick-filing')))
        if guarded:
            from starlette.concurrency import run_in_threadpool
            state=dict(_state)
            valid=state['ready'] and await run_in_threadpool(identity,state['root'],state.get('company'))
            if not valid:
                return JSONResponse({'detail':{'code':'workspace_invalid','message':'Dossier de travail incorrect ou inaccessible. Ouvrez Dossier de travail et relancez la détection avant de traiter ou classer.'}},status_code=423)
        return await call_next(request)
    router=APIRouter(dependency_overrides_provider=app)
    def begin_check():
        if not _checking.acquire(blocking=False):return
        if not _state.get('ready'):_state.update(state='checking',ready=False,message='Recherche et vérification du dossier de travail…')
        def worker():
            from app.core.db import get_session
            sessions=get_session()
            try:
                session=next(sessions)
                check(session,d,force=True)
            except Exception:
                _state.update(state='error',ready=False,root=None,message='La vérification du dossier a échoué. Relancez la détection dans Dossier de travail.')
            finally:
                sessions.close();_checking.release()
        threading.Thread(target=worker,daemon=True,name='workspace-discovery').start()
    @router.get('/api/v1/workspace')
    def status(request:Request):
        local(request)
        if time.monotonic()-_checked>=10:begin_check()
        return dict(_state)
    @router.post('/api/v1/workspace/check')
    def recheck(request:Request):
        local(request)
        begin_check()
        return dict(_state)
    @router.post('/api/v1/workspace/select')
    async def choose(request:Request,session=Depends(d.get_session)):
        local(request)
        body=await request.json()
        root=body.get('root') if isinstance(body,dict) else None
        if not isinstance(root,str):raise HTTPException(422,'Choisissez un dossier de travail.')
        catalogue=read_catalogue();company=(catalogue or {}).get('company') or Path(root).parent.name
        with _lock:
            if not identity(root,company):raise HTTPException(422,'Dossier incorrect : société, archive et catégories ne correspondent pas.')
            apply_root(session,d,root,company,catalogue)
        return dict(_state)
    app.router.routes[0:0]=router.routes
    original_lifespan=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application) as context:
            begin_check()
            yield context
    app.router.lifespan_context=lifespan
