"""Local-only update control; installation is delegated to the bundled script."""
import json, os, re, subprocess, sys, threading, urllib.request
from pathlib import Path

REPOSITORY = 'aston76/DocPilot-Install'
VERSION = 'v0.1.0-beta.19'
_lock = threading.Lock()
_ack_complete = False
_state = {'current': VERSION, 'latest': None, 'available': False, 'status': 'idle', 'message': ''}

def version_key(tag):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?', tag or '')
    if not match:
        raise ValueError('Version inconnue')
    major, minor, patch, beta = match.groups()
    return (int(major), int(minor), int(patch), int(beta) if beta else 1000000)

def latest_release():
    url = f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=20'
    request = urllib.request.Request(url, headers={'User-Agent': 'DocPilot-Updater'})
    with urllib.request.urlopen(request, timeout=15) as response:
        releases = json.load(response)
    valid = []
    for release in releases:
        if release.get('draft'):
            continue
        try:
            key = version_key(release['tag_name'])
        except (ValueError, KeyError):
            continue
        names = {asset.get('name') for asset in release.get('assets', [])}
        if {'DocPilot-Windows-portable.zip', 'DocPilot-Windows-portable.zip.sha256'} <= names:
            valid.append((key, release))
    if not valid:
        raise ValueError('Aucune version complete disponible')
    return max(valid, key=lambda item: item[0])[1]

def _worker(install):
    try:
        release = latest_release()
        available = version_key(release['tag_name']) > version_key(VERSION)
        _state.update(latest=release['tag_name'], available=available, status='available' if available else 'current', message='Une nouvelle version est disponible.' if available else 'Vous avez la dernière version.')
        if install and available:
            script = Path(sys.executable).parent / 'DocPilot-Update.ps1'
            if not script.is_file():
                raise ValueError('Script de mise a jour absent')
            progress_path=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'DocPilot'/'update-state.json'
            progress_path.parent.mkdir(parents=True,exist_ok=True)
            progress_path.write_text(json.dumps({'status':'starting','version':release['tag_name']}),encoding='utf-8')
            _state.update(status='installing', message='La fenêtre de mise à jour va s’ouvrir…')
            # The updater owns its native progress window and survives the API exit.
            process=subprocess.Popen(['powershell.exe','-STA','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Mode','Update','-Restart'],
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0),
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,cwd=os.environ.get('TEMP',str(Path.home())))
            def monitor():
                code=process.wait()
                try:
                    phase=json.loads(progress_path.read_text(encoding="utf-8-sig")).get("status")
                except (OSError,ValueError):phase=None
                if phase not in ("complete","current","error"):
                    message="La mise à jour s’est interrompue. Réessayez."
                    _state.update(status="error",message=message)
                    progress_path.write_text(json.dumps({"status":"error","message":message}),encoding="utf-8")
            threading.Thread(target=monitor,daemon=True).start()
    except Exception as error:
        _state.update(status='error', message=str(error))
    finally:
        _lock.release()

def update_status():
    value=dict(_state)
    path=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'DocPilot'/'update-state.json'
    try:
        progress=json.loads(path.read_text(encoding='utf-8-sig'))
        phase=progress.get('status')
        if phase in ('downloading','verifying','extracting','waiting','installing') and value['status']=='installing':
            value.update(phase=phase,percent=progress.get('percent'),message=progress.get('message',''))
        elif phase in ('complete','current') and progress.get('version')==VERSION:
            # The running binary is proof that installation and restart finished.
            if (value['status'] in ('idle','current','complete') and not value.get('available')) or (value['status']=='installing' and value.get('latest')==VERSION):
                _state.update(status='current',available=False,latest=VERSION,message='Vous avez la dernière version.')
                value=dict(_state)
        elif value['status']=='installing' and phase=='complete':
            # This process still runs the old code. Wait for the new process.
            value.update(available=False,phase='restarting',percent=100,message='Installation terminée. DocPilot redémarre automatiquement…')
        elif value['status']=='installing' and phase=='error':
            _state.update(status='error',available=False,message=progress.get('message',''))
            value=dict(_state)
    except (OSError,ValueError):pass
    return value

def begin(install):
    if not _lock.acquire(blocking=False):
        return dict(_state)
    if _state['status']=='installing':
        _lock.release();return update_status()
    _state.update(status='checking', available=False, message='Vérification de la dernière version…')
    threading.Thread(target=_worker, args=(install,), daemon=True).start()
    return dict(_state)

def install(app):
    from fastapi import APIRouter, HTTPException, Request
    from contextlib import asynccontextmanager
    from starlette.responses import JSONResponse
    router = APIRouter(dependency_overrides_provider=app)

    @app.middleware('http')
    async def pause_new_analysis(request: Request, call_next):
        if _state['status'] == 'installing' and request.method == 'POST' and (request.url.path == '/api/v1/documents/upload' or request.url.path.endswith('/reclassify')):
            return JSONResponse({'detail': 'Mise a jour en cours : ajoutez le document apres le redemarrage.'}, status_code=423)
        return await call_next(request)

    def local(request):
        if request.client and request.client.host not in ('127.0.0.1', '::1', 'testclient'):
            raise HTTPException(403, 'Acces local uniquement')
        if request.headers.get('origin') not in (None, 'http://127.0.0.1:8765', 'http://localhost:8765') or request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, 'Origine refusee')

    @router.get('/api/v1/system/update')
    def status(request: Request):
        local(request)
        return update_status()

    @router.post('/api/v1/system/update')
    async def update(request: Request):
        local(request)
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, 'Demande invalide') from None
        global _ack_complete
        if body=={'action':'dismiss'}:
            _ack_complete=True
            return update_status()
        if body not in ({'action': 'check'}, {'action': 'install'}):
            raise HTTPException(422, 'Action invalide')
        return begin(body['action'] == 'install')

    app.router.routes[0:0] = router.routes
    original_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application) as context:
            begin(True)
            yield context
    app.router.lifespan_context = lifespan
