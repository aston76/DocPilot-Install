"""Read provider-confirmed per-file sync state. Never hydrate archived files."""
import ctypes
import os
import threading
import re
import time
from contextlib import nullcontext
from datetime import datetime,timezone
from pathlib import Path

_log_lock=threading.Lock()
_log_checked=0
_uploaded={}

def upload_confirmation(path,stat):
    """Accept explicit upload completion only when newer than the current file."""
    global _log_checked
    key=os.path.normcase(os.path.normpath(str(path)))
    with _log_lock:
        if time.monotonic()-_log_checked>8:
            _log_checked=time.monotonic()
            folder=Path(os.environ.get('LOCALAPPDATA',''))/'SynologyDrive/log'
            try:logs=sorted(folder.glob('daemon.log*'),key=lambda p:p.stat().st_mtime,reverse=True)[:4]
            except OSError:logs=[]
            for log in logs:
                try:
                    with log.open('rb') as stream:
                        stream.seek(max(0,log.stat().st_size-512*1024))
                        text=stream.read().decode('utf-8',errors='replace')
                    for line in text.splitlines():
                        match=re.search(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}).*Reset local lock state for file '(.+)' after upload\.",line)
                        if match:
                            when=datetime.fromisoformat(match[1]).timestamp()
                            name=os.path.normcase(os.path.normpath(match[2]))
                            _uploaded[name]=max(when,_uploaded.get(name,0))
                except (OSError,ValueError):continue
            if len(_uploaded)>2000:
                oldest=sorted(_uploaded,key=_uploaded.get)[:-1000]
                for old in oldest:_uploaded.pop(old,None)
        confirmed=_uploaded.get(key)
    return confirmed if confirmed is not None and confirmed>=max(stat.st_mtime,stat.st_ctime)-1 else None

def placeholder_state(path):
    stat=Path(path).lstat()
    if os.name!='nt':return None
    api=ctypes.WinDLL('cldapi')
    fn=api.CfGetPlaceholderStateFromAttributeTag
    fn.argtypes=[ctypes.c_uint32,ctypes.c_uint32]
    fn.restype=ctypes.c_uint32
    state=fn(stat.st_file_attributes,stat.st_reparse_tag)
    return None if state==0xffffffff else state

def file_status(path,simulation=False):
    info={'path':str(path),'percent':None,'bytes_transferred':None,'total_bytes':None,
          'source':'État fourni par Windows/Synology Drive','state':'unknown','label':'État NAS non confirmé',
          'message':'Synology Drive ne fournit pas ici le pourcentage de transfert. La copie locale ne confirme pas la réception sur le NAS.'}
    if simulation:
        return info | {'state':'simulation','label':'Simulation : aucun transfert','message':'Le mode simulation ne copie pas le document sur le NAS.'}
    try:
        stat=Path(path).lstat()
        info['total_bytes']=stat.st_size
        state=placeholder_state(path)
        if state is not None and state & 1:
            if state & 8:
                info.update(state='synced',label='Synchronisé · 100 %',percent=100,bytes_transferred=stat.st_size,
                            message='Contenu déclaré synchronisé par Synology Drive/Windows.')
            else:
                info.update(state='pending',label='Synchronisation à confirmer',message='Le fichier est suivi par Synology Drive, mais n’est pas déclaré synchronisé. Progression intermédiaire non fournie.')
        if info['state']=='unknown' and upload_confirmation(path,stat):
            info.update(state='synced',label='Envoi terminé · 100 %',percent=100,bytes_transferred=stat.st_size,
                        source='Journal Synology Drive : envoi terminé',message='Le journal Synology confirme la fin d’un envoi postérieur à la dernière modification locale de ce fichier.')
    except FileNotFoundError:
        info.update(state='missing',label='Fichier introuvable',message='Le fichier classé est absent à cet emplacement. Vérifiez le dossier ou un éventuel déplacement.')
    except (OSError,AttributeError):
        info.update(state='unavailable',label='Dossier inaccessible',message='Vérifiez Synology Drive, le réseau et les droits d’accès. Réception sur le NAS non confirmée.')
    return info

def client_state():
    base=Path(os.environ.get('LOCALAPPDATA',''))/'SynologyDrive'
    running=False
    if os.name=='nt':
        try:
            pid=int((base/'daemon.pid').read_text().strip())
            api=ctypes.WinDLL('kernel32',use_last_error=True)
            api.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
            api.OpenProcess.restype=ctypes.c_void_p
            handle=api.OpenProcess(0x1000,0,pid)
            if handle:
                try:
                    buf=ctypes.create_unicode_buffer(32768);size=ctypes.c_uint32(len(buf))
                    api.QueryFullProcessImageNameW.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)]
                    running=bool(api.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size))) and Path(buf.value).name.lower()=='cloud-drive-daemon.exe'
                finally:
                    api.CloseHandle.argtypes=[ctypes.c_void_p];api.CloseHandle(handle)
        except (OSError,ValueError):pass
    return {'running':running,'label':'Synology Drive actif' if running else 'Synology Drive arrêté ou non détecté',
            'message':'Client actif ; la connexion au serveur et la réception sont vérifiées séparément par fichier.' if running else 'Ouvrez Synology Drive Client pour reprendre la synchronisation.'}

def install(app):
    from app.api import documents as d
    from fastapi import APIRouter,Depends,Request,HTTPException
    from docpilot_inline_filing import local
    from sqlalchemy import select
    router=APIRouter(dependency_overrides_provider=app)
    def document_sync(session,doc):
        if not doc.final_path:return {'document_id':doc.id,'state':'not_filed','label':'Aucun fichier classé à synchroniser','percent':None,'message':'Complétez puis validez le document pour lancer sa copie.'}
        try:
            with d._company_context(session,doc) if hasattr(d,'_company_context') else nullcontext():
                root=d._filing_root(session)
                path=d._safe_destination(root,doc.final_path)
                info=file_status(path,doc.dry_run)
        except (OSError,ValueError,HTTPException):
            info={'state':'unavailable','label':'Archive inaccessible','percent':None,'message':'Vérifiez la configuration du dossier de cette société.'}
        return info | {'document_id':doc.id,'filename':doc.final_filename or Path(doc.final_path).name}
    @router.get('/api/v1/documents/{doc_id}/sync')
    def sync(doc_id:int,request:Request,session=Depends(d.get_session)):
        local(request)
        doc=session.get(d.Document,doc_id)
        if not doc:raise HTTPException(404,'Document introuvable')
        return {'client':client_state(),'file':document_sync(session,doc),'checked_at':datetime.now(timezone.utc).isoformat()}
    @router.get('/api/v1/sync/status')
    def status(request:Request,session=Depends(d.get_session)):
        local(request)
        docs=session.scalars(select(d.Document).where(d.Document.final_path.is_not(None),d.Document.status!='DELETED').order_by(d.Document.id.desc()).limit(100)).all()
        return {'client':client_state(),'files':[document_sync(session,doc) for doc in docs],'checked_at':datetime.now(timezone.utc).isoformat()}
    app.router.routes[0:0]=router.routes
