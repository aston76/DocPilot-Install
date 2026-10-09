"""Background SHA indexing after workspace verification; one queue per process."""
import hashlib,json,os,threading,time,queue
import docpilot_hash_store as store
import sqlite3,logging
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
_remote={}
_dirty=set()
_watched=set()
_watch_handles={}
_stores={}
_rescan=set()
_catalogue_checked={}

def refresh_catalogue(root,force=False):
    """Map shared relative destinations to this PC; keep local custom names."""
    import docpilot_workspace as w
    key=root_key(root)
    if not force and time.monotonic()-_catalogue_checked.get(key,float('-inf'))<300:return
    with w._lock:
        current=w.read_catalogue()
        if not current or root_key(current.get('root',''))!=key:return
        if not w.identity(root,current.get('company')):return
        fresh=w.bounded(lambda:w.catalogue_for(root,current['company']),5)
        try:peers,errors=w.bounded(lambda:store.shared_catalogue(root,current['company']),5)
        except (OSError,ValueError):peers=[];errors=['Partage inaccessible']
        previous={item['path']:item for item in current.get('entries',[])}
        entries={path:dict(item,aliases=list(item.get('aliases',[]))) for path,item in previous.items()}
        visible={item['path']:item for item in fresh['entries']}
        for path,item in visible.items():
            if path not in entries:entries[path]=dict(item)
            # The actual year folders, rather than a remote machine's drive,
            # determine how this destination is offered locally.
            elif item.get('layout')=='year':entries[path]['layout']='year'
        pending=set()
        for item in peers:
            path=item['path']
            if path not in visible:pending.add(path);continue
            target=entries[path]
            if target.get('filename_label')==target.get('supplier'):
                target['filename_label']=item['filename_label']
            target['aliases']=list(dict.fromkeys(target.get('aliases',[])+item.get('aliases',[])))
        updated=dict(current,entries=list(entries.values()))
        if updated['entries']!=current.get('entries',[]):
            w.save_catalogue(updated)
            from app.api import documents as d
            clear=getattr(d._archive,'_workspace_clear_catalogue',None)
            if clear:clear()
        try:
            import docpilot_catalogue_directory
            docpilot_catalogue_directory.update_from_catalogue(fresh)
        except ImportError:pass
        except Exception:
            logging.getLogger(__name__).warning('Récupération du répertoire local différée ; catalogue conservé')
        with _lock:
            record(root).update(catalogue_pending=len(pending),catalogue_sync_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        try:w.bounded(lambda:store.publish(root,record(root),cache_path(root).parent,updated),5)
        except (OSError,ValueError):errors.append('Publication inaccessible')
        with _lock:
            if errors:record(root)['shared_status']='partial'
            _catalogue_checked[key]=time.monotonic()

def refresh_requested():
    import docpilot_workspace as w
    if not w._state.get('ready'):return
    with _lock:roots=[_records.get(key,{}).get('root',key) for key in _requested]
    for root in roots:request_scan(root,once=False)

def refresh_shared(root):
    import docpilot_workspace as w
    key=root_key(root)
    try:
        hints,errors=w.bounded(lambda:store.shared_hints(root),5)
        entries={}
        for relative,values in hints.items():
            for value in values:entries.setdefault(value[3],set()).add(relative)
        with _lock:
            _remote[key]=entries
            record(root)['shared_status']='partial' if errors else 'available'
        if key in _dirty:
            w.bounded(lambda:store.publish(root,record(root),cache_path(root).parent,w.read_catalogue()),5)
            with _lock:_dirty.discard(key)
    except (OSError,ValueError):
        with _lock:record(root)['shared_status']='unavailable'

def periodic():
    next_scan=time.monotonic()+300
    while not _periodic_stop.wait(5):
        with _lock:roots=[_records.get(key,{}).get('root',key) for key in _requested]
        for root in roots:
            refresh_shared(root)
            try:refresh_catalogue(root)
            except (OSError,ValueError):logging.getLogger(__name__).warning('Synchronisation du catalogue différée')
        if time.monotonic()>=next_scan:
            refresh_requested();next_scan=time.monotonic()+300

def watch_archive(root):
    """Windows change notifications; periodic reconciliation is the fallback."""
    if os.name!='nt':return
    import ctypes,struct
    from ctypes import wintypes
    key=root_key(root);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.ReadDirectoryChangesW.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD,wintypes.BOOL,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD),ctypes.c_void_p,ctypes.c_void_p]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.CreateFileW(str(root),1,7,None,3,0x02000000,None)
    if handle==wintypes.HANDLE(-1).value:
        with _lock:_watched.discard(key)
        return
    with _lock:_watch_handles[key]=handle
    buffer=ctypes.create_string_buffer(32768);returned=wintypes.DWORD()
    try:
        while not _periodic_stop.is_set():
            if not kernel.ReadDirectoryChangesW(handle,buffer,len(buffer),True,0x1|0x2|0x8|0x10,ctypes.byref(returned),None,None):break
            offset=0;changed=returned.value==0
            while offset<returned.value:
                next_offset,action,length=struct.unpack_from('III',buffer.raw,offset)
                name=buffer.raw[offset+12:offset+12+length].decode('utf-16-le')
                if not name.startswith('DocPilot-Partage'):changed=True
                if not next_offset:break
                offset+=next_offset
            if changed:
                with _lock:
                    if key in _pending:_rescan.add(key)
                time.sleep(.5);request_scan(root,once=False)
    finally:
        kernel.CloseHandle(handle)
        with _lock:_watch_handles.pop(key,None);_watched.discard(key)

def root_key(root):
    return os.path.normcase(os.path.abspath(str(root)))

def cache_path(root):
    name=hashlib.sha256(root_key(root).encode()).hexdigest()[:24]
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'DocPilot'/('archive-sha256-'+name+'.json')

def index_store(root):
    key=root_key(root)
    with _lock:
        if key not in _stores:_stores[key]=store.Store(cache_path(root).with_suffix('.sqlite3'))
        return _stores[key]

def record(root):
    key=root_key(root)
    with _lock:
        if key not in _records:
            database=index_store(root)
            value=database.load(root)
            # Migrate the old cache once; never erase it until conversion succeeds.
            if not value.get('last_scan'):
                try:
                    old=json.loads(cache_path(root).read_text(encoding='utf-8'))
                    if root_key(old['root'])==key:
                        old['files']={p:v for p,v in old.get('files',{}).items() if store.valid_relative(p) and isinstance(v,list) and len(v)==4}
                        database.save(old);value=database.load(root)
                except (OSError,ValueError,KeyError):pass
            _records[key]=value
        return _records[key]

def progress(root):
    with _lock:
        data=record(root);state=_states.get(root_key(root),{})
        return {key:data.get(key) for key in ('root','snapshot_at','last_scan','scan_errors','scan_error_examples','shared_status','shared_hints','catalogue_pending','catalogue_sync_at')} | {
            'indexed_files':data.get('indexed_files',len(data.get('files',{}))),
            'running':state.get('phase') in ('queued','discovering','hashing'),
            'phase':state.get('phase','idle'),'processed_files':state.get('processed_files',0),
            'total_files':state.get('total_files'),'percent':state.get('percent'),
            'scan_message':state.get('message','Scan automatique en attente de vérification du dossier.'),
            'verification_complete':state.get('phase')=='complete',
            'scanned_files':state.get('processed_files',data.get('scanned_files',0))}

def fingerprint(stat):return [stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]

def online_only(stat):
    attributes=getattr(stat,'st_file_attributes',0)
    cloud=(getattr(stat,'st_reparse_tag',0)&0xFFFF0FFF)==0x9000001A
    return bool(attributes&0x1000 or (cloud and attributes&(0x40000|0x400000)))

def files_in(root):
    if not root.is_dir():raise OSError('Dossier de travail inaccessible.')
    resolved_root=root.resolve()
    files=[];errors=[]
    for directory,dirs,names in os.walk(root,followlinks=False,onerror=lambda error:errors.append(str(error))):
        dirs[:]=[name for name in dirs if name!='DocPilot-Partage' and not (Path(directory)/name).is_symlink()]
        for name in names:
            path=Path(directory)/name
            if path.is_symlink() or name.endswith('.docpilot-part'):continue
            if path.resolve().is_relative_to(resolved_root):files.append(path)
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
    previous={**record(root),'files':dict(record(root).get('files',{}))};found={};saved={};timeouts=0
    try:hints,shared_errors=w.bounded(lambda:store.shared_hints(root),5)
    except (OSError,ValueError):hints={};shared_errors=['Index partagé inaccessible']
    with _lock:_states[key].update(phase='hashing',total_files=len(files),percent=0,message='Vérification SHA-256 en arrière-plan…')
    for index,path in enumerate(files,1):
        relative=path.relative_to(root).as_posix()
        try:
            before=w.bounded(path.stat)
            # Avoid automatically downloading every on-demand Drive document.
            if online_only(before):
                raise OSError('Fichier uniquement en ligne : rendez-le disponible hors connexion pour le vérifier.')
            signature=fingerprint(before);old=previous.get('files',{}).get(relative)
            if old and old[:3]==signature: digest=old[3]
            else:
                # A peer hint is rehashed locally before becoming authoritative.
                # It avoids a missing remote result, but never trusts metadata alone.
                digest=w.bounded(lambda:read_hash(path,before),20)
            found.setdefault(digest,[]).append(relative);saved[relative]=signature+[digest]
        except (OSError,ValueError) as error:
            errors.append(relative+': '+str(error))
            if isinstance(error,TimeoutError):timeouts+=1
        with _lock:_states[key].update(processed_files=index,percent=round(100*index/len(files),1))
        if timeouts>=2:
            errors.append('Scan arrêté : plusieurs fichiers ne répondent pas. Vérifiez le réseau puis relancez le scan.')
            break
    data={'root':str(root),'entries':found,'files':saved,'snapshot_at':None,
          'last_scan':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scanned_files':len(saved),
          'scan_errors':len(errors),'scan_error_examples':errors[:5]}
    with _lock:
        current=record(root)
        for relative,value in current.get('files',{}).items():
            if relative not in previous.get('files',{}):
                saved.setdefault(relative,value);found.setdefault(value[3],[]).append(relative)
    data['indexed_files']=len(saved)
    data['shared_hints']=sum(len(values) for values in hints.values())
    data['shared_status']='available' if not shared_errors else 'partial'
    try:
        w.bounded(lambda:store.publish(root,data,cache_path(root).parent),5)
    except (OSError,ValueError):data['shared_status']='unavailable'
    index_store(root).save(data)
    with _lock:
        _records[key]=data
        _states[key].update(phase='partial' if errors else 'complete',percent=None if errors else 100,
            message='Scan incomplet : '+str(len(errors))+' erreur(s). Vérifiez les fichiers et relancez le scan.' if errors else 'Scan automatique terminé : '+str(len(saved))+' fichier(s) vérifié(s).')
    # New supplier folders created on another PC become local routing choices.
    refresh_catalogue(root,force=True)
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
        if os.name=='nt' and key not in _watched:
            _watched.add(key);threading.Thread(target=watch_archive,args=(str(root),),daemon=True,name='archive-changes').start()
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
            with _lock:
                again=key in _rescan;_rescan.discard(key)
            if again:request_scan(root,once=False)

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
    def lookup(*digests):
        requested={value for value in digests if value}
        evidence={'matches':[],'algorithm':'SHA-256','source':'Index local et index partagé Synology',
                  'verification_scope':'Fichiers indexés de l’archive configurée','checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                  'scan_errors':0,'verification_complete':False,'peer_pending':[]}
        try:
            root=Path(selected_root());key=root_key(root);data=record(root);state=status()
            evidence.update(root=str(root),last_scan=data.get('last_scan'),snapshot_at=data.get('snapshot_at'),
                            verification_complete=state['verification_complete'],scan_message=state['scan_message'])
            if data.get('shared_status') in ('unavailable','partial'):
                evidence['verification_complete']=False
                evidence['scan_message']='Index partagé indisponible ou partiel ; vérification locale uniquement.'
            candidates=set()
            with _lock:
                for digest in requested:
                    candidates.update(data.get('entries',{}).get(digest,[]))
                    candidates.update(_remote.get(key,{}).get(digest,[]))
            for relative in candidates:
                if not store.valid_relative(relative):continue
                path=root/relative
                try:
                    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):continue
                    before=w.bounded(path.stat)
                    if online_only(before):raise OSError('Copie uniquement en ligne')
                    old=data.get('files',{}).get(relative)
                    digest=old[3] if old and old[:3]==fingerprint(before) else w.bounded(lambda:read_hash(path,before),20)
                    if digest in requested:evidence['matches'].append(relative)
                    else:
                        evidence['verification_complete']=False
                        request_scan(root,once=False)
                except (OSError,ValueError):
                    evidence['peer_pending'].append(relative);evidence['verification_complete']=False
                    evidence['scan_errors']+=1
            evidence['matches']=sorted(set(evidence['matches']))
            if evidence['peer_pending']:evidence['scan_message']='Une copie indexée est encore inaccessible ou en cours de synchronisation.'
        except (OSError,ValueError) as error:
            evidence.update(scan_message=str(error),scan_errors=1,verification_complete=False)
        return evidence
    duplicates.lookup=lookup
    original_mark=d._mark_filed
    @wraps(original_mark)
    def mark_filed(session,doc,*args,**kwargs):
        result=original_mark(session,doc,*args,**kwargs)
        if not getattr(doc,'dry_run',True) and getattr(doc,'final_path',None):
            try:
                root=Path(selected_root());path=Path(doc.final_path)
                if not path.is_absolute():path=root/path
                if path.resolve().is_relative_to(root.resolve()):
                    relative=path.relative_to(root).as_posix();signature=fingerprint(path.stat());digest=args[1] if len(args)>1 else doc.sha256
                    with _lock:
                        data=record(root);old=data['files'].get(relative)
                        if old and relative in data['entries'].get(old[3],[]):data['entries'][old[3]].remove(relative)
                        data['files'][relative]=signature+[digest]
                        if relative not in data['entries'].setdefault(digest,[]):data['entries'][digest].append(relative)
                        data['indexed_files']=len(data['files']);index_store(root).put(relative,signature+[digest]);_dirty.add(root_key(root))
            except (OSError,ValueError,sqlite3.Error):
                logging.exception('Document classé ; actualisation de l’index différée')
        return result
    d._mark_filed=mark_filed
    original_lifespan=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application) as context:
            _periodic_stop.clear()
            threading.Thread(target=periodic,daemon=True,name='sha256-refresh').start()
            try:yield context
            finally:
                _periodic_stop.set()
                if os.name=='nt':
                    import ctypes
                    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
                    kernel.CancelIoEx.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
                    with _lock:handles=list(_watch_handles.values())
                    for handle in handles:kernel.CancelIoEx(handle,None)
    app.router.lifespan_context=lifespan
