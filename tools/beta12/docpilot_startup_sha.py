"""Background SHA indexing after workspace verification; one queue per process."""
import hashlib,json,os,threading,time,queue
from pathlib import Path
from contextvars import copy_context
from functools import wraps
from contextlib import asynccontextmanager

_lock=threading.RLock()
_tasks=queue.Queue()
_requested=set()
_records={}
_states={}
_pending=set()
_worker=None
_periodic_stop=threading.Event()

def refresh_catalogue(root):
    """Refresh local folder choices; preserve labels/aliases of existing suppliers."""
    import docpilot_workspace as w
    with w._lock:
        current=w.read_catalogue()
        if not current or root_key(current.get('root',''))!=root_key(root):return
        if not w.identity(root,current.get('company')):return
        fresh=w.bounded(lambda:w.catalogue_for(root,current['company']),5)
        existing={item['path']:item for item in current.get('entries',[])}
        entries=list(current.get('entries',[]))+[item for item in fresh['entries'] if item['path'] not in existing]
        if entries!=current.get('entries',[]):
            w.save_catalogue(dict(current,entries=entries))
            from app.api import documents as d
            clear=getattr(d._archive,'_workspace_clear_catalogue',None)
            if clear:clear()

def refresh_requested():
    import docpilot_workspace as w
    if not w._state.get('ready'):return
    with _lock:roots=[_records.get(key,{}).get('root',key) for key in _requested]
    for root in roots:request_scan(root,once=False)

def periodic():
    while not _periodic_stop.wait(60):refresh_requested()

def root_key(root):
    return os.path.normcase(os.path.abspath(str(root)))

def cache_path(root):
    name=hashlib.sha256(root_key(root).encode()).hexdigest()[:24]
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'DocPilot'/('archive-sha256-'+name+'.json')

def record(root):
    key=root_key(root)
    with _lock:
        if key not in _records:
            try:
                value=json.loads(cache_path(root).read_text(encoding='utf-8'))
                if root_key(value['root'])!=key:raise ValueError('Wrong archive cache')
            except (OSError,ValueError,KeyError):value={'root':str(root),'entries':{},'files':{},'snapshot_at':None}
            _records[key]=value
        return _records[key]

def progress(root):
    with _lock:
        data=record(root);state=_states.get(root_key(root),{})
        return {key:data.get(key) for key in ('root','snapshot_at','last_scan','scan_errors','scan_error_examples')} | {
            'indexed_files':sum(len(paths) for paths in data.get('entries',{}).values()),
            'running':state.get('phase') in ('queued','discovering','hashing'),
            'phase':state.get('phase','idle'),'processed_files':state.get('processed_files',0),
            'total_files':state.get('total_files'),'percent':state.get('percent'),
            'scan_message':state.get('message','Scan automatique en attente de vérification du dossier.'),
            'verification_complete':state.get('phase')=='complete',
            'scanned_files':state.get('processed_files',data.get('scanned_files',0))}

def fingerprint(stat):return [stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]

def files_in(root):
    if not root.is_dir():raise OSError('Dossier de travail inaccessible.')
    files=[];errors=[]
    for directory,dirs,names in os.walk(root,followlinks=False,onerror=lambda error:errors.append(str(error))):
        dirs[:]=[name for name in dirs if not (Path(directory)/name).is_symlink()]
        for name in names:
            path=Path(directory)/name
            if path.is_symlink() or name.endswith('.docpilot-part'):continue
            if path.resolve().is_relative_to(root):files.append(path)
    return files,errors

def read_hash(path,before):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    if fingerprint(path.stat())!=fingerprint(before):raise OSError('Fichier modifié pendant le scan.')
    return digest.hexdigest()

def scan(root):
    import docpilot_workspace as w
    root=Path(root);key=root_key(root)
    with _lock:_states[key]={'phase':'discovering','processed_files':0,'total_files':None,'percent':None,'message':'Recherche des fichiers à vérifier…'}
    if not w.identity(root,root.parent.name):raise OSError('Archive incorrecte ou inaccessible. Relancez la détection du dossier.')
    files,errors=w.bounded(lambda:files_in(root),15)
    previous=record(root);found={};saved={};timeouts=0
    with _lock:_states[key].update(phase='hashing',total_files=len(files),percent=0,message='Vérification SHA-256 en arrière-plan…')
    for index,path in enumerate(files,1):
        relative=path.relative_to(root).as_posix()
        try:
            before=w.bounded(path.stat)
            # Avoid automatically downloading every on-demand Drive document.
            if getattr(before,'st_file_attributes',0)&(0x1000|0x40000|0x400000):
                raise OSError('Fichier uniquement en ligne : rendez-le disponible hors connexion pour le vérifier.')
            signature=fingerprint(before);old=previous.get('files',{}).get(relative)
            digest=old[3] if old and old[:3]==signature else w.bounded(lambda:read_hash(path,before),20)
            found.setdefault(digest,[]).append(relative);saved[relative]=signature+[digest]
        except (OSError,ValueError) as error:
            errors.append(relative+': '+str(error))
            if isinstance(error,TimeoutError):timeouts+=1
        with _lock:_states[key].update(processed_files=index,percent=round(100*index/len(files),1))
        if timeouts>=2:
            errors.append('Scan arrêté : plusieurs fichiers ne répondent pas. Vérifiez le réseau puis relancez le scan.')
            break
        time.sleep(.005)
    data={'root':str(root),'entries':found,'files':saved,'snapshot_at':None,
          'last_scan':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scanned_files':len(saved),
          'scan_errors':len(errors),'scan_error_examples':errors[:5]}
    target=cache_path(root);target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');os.replace(temporary,target)
    with _lock:
        _records[key]=data
        _states[key].update(phase='partial' if errors else 'complete',percent=None if errors else 100,
            message='Scan incomplet : '+str(len(errors))+' erreur(s). Vérifiez les fichiers et relancez le scan.' if errors else 'Scan automatique terminé : '+str(len(saved))+' fichier(s) vérifié(s).')
    # New supplier folders created on another PC become local routing choices.
    refresh_catalogue(root)
    return progress(root)

def request_scan(root,once=True):
    global _worker
    import docpilot_workspace as w
    if not w._state.get('ready'):
        return {'running':False,'phase':'blocked','indexed_files':0,'verification_complete':False,'percent':None,'scan_message':'Vérifiez le dossier de travail avant de lancer le scan SHA-256.'}
    key=root_key(root)
    with _lock:
        if key in _pending or (once and key in _requested):return progress(root)
        _requested.add(key);_pending.add(key)
        _states[key]={'phase':'queued','processed_files':0,'total_files':None,'percent':None,'message':'Scan SHA-256 automatique planifié après vérification du dossier.'}
        _tasks.put((str(root),copy_context()))
        if _worker is None or not _worker.is_alive():
            _worker=threading.Thread(target=run_queue,daemon=True,name='startup-sha256');_worker.start()
    return progress(root)

def run_queue():
    global _worker
    while True:
        with _lock:
            try:root,context=_tasks.get_nowait()
            except queue.Empty:
                _worker=None
                return
        key=root_key(root)
        try:
            import docpilot_update
            # Let the updater finish checking before starting expensive reads.
            deadline=time.monotonic()+20
            while docpilot_update._state.get('status')=='checking' and time.monotonic()<deadline:time.sleep(.2)
            if docpilot_update._state.get('status')=='installing':
                with _lock:_states[key].update(phase='deferred',message='Scan différé pendant la mise à jour ; il démarrera à la réouverture.')
            else:context.run(scan,root)
        except Exception as error:
            with _lock:_states[key].update(phase='error',percent=None,message='Scan SHA-256 interrompu : '+str(error))
        finally:
            with _lock:_pending.discard(key)
            _tasks.task_done()

def install(app):
    import docpilot_duplicates as duplicates,docpilot_workspace as w
    from app.api import documents as d
    original_catalogue=d._archive.catalogue
    def catalogue():
        value=original_catalogue()
        if value and w._state.get('ready') and value.get('root'):
            root=value['root']
            if root_key(root) not in _requested and w.identity(root,value.get('company')):request_scan(root)
        return value
    d._archive.catalogue=catalogue
    original_apply=w.apply_root
    @wraps(original_apply)
    def apply(*args,**kwargs):
        result=original_apply(*args,**kwargs)
        request_scan(w._state['root'])
        return result
    w.apply_root=apply
    original_check=w.check
    @wraps(original_check)
    def check(*args,**kwargs):
        result=original_check(*args,**kwargs)
        if result.get('ready'):
            try:refresh_catalogue(result['root'])
            except (OSError,ValueError):pass
        return result
    w.check=check
    def selected_root():
        value=d._archive.catalogue()
        if not value:raise OSError('Dossier de travail non configuré.')
        return value['root']
    def load():
        try:return record(selected_root())
        except (OSError,ValueError):return {'entries':{},'snapshot_at':None}
    def status(root=None):
        try:return progress(root or selected_root())
        except (OSError,ValueError):return {'running':False,'phase':'blocked','indexed_files':0,'scan_errors':0,'verification_complete':False,'percent':None,'scan_message':'Vérifiez le dossier de travail pour démarrer le scan SHA-256.'}
    duplicates.load=load
    duplicates.status=status
    duplicates.start_scan=lambda root:request_scan(root,once=False)
    duplicates.scan=scan
    original_lookup=duplicates.lookup
    @wraps(original_lookup)
    def lookup(*digests):
        evidence=original_lookup(*digests)
        state=status()
        if not state['verification_complete']:
            evidence.update(verification_complete=False,scan_message=state['scan_message'])
        return evidence
    duplicates.lookup=lookup
    original_lifespan=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application) as context:
            _periodic_stop.clear()
            threading.Thread(target=periodic,daemon=True,name='sha256-refresh').start()
            try:yield context
            finally:_periodic_stop.set()
    app.router.lifespan_context=lifespan
