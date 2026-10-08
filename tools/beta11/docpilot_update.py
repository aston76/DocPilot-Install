"""Local-only update control; installation is delegated to the bundled script."""
import json, re, subprocess, sys, threading, urllib.request
from pathlib import Path

REPOSITORY = 'aston76/DocPilot-Install'
VERSION = 'v0.1.0-beta.11'
_lock = threading.Lock()
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
        _state.update(latest=release['tag_name'], available=available, status='available' if available else 'current', message='')
        if install and available:
            script = Path(sys.executable).parent / 'DocPilot-Update.ps1'
            if not script.is_file():
                raise ValueError('Script de mise a jour absent')
            _state.update(status='installing', message='Telechargement et verification en cours')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-Mode', 'Update', '-Restart'], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=1800, capture_output=True)
            if result.returncode:
                raise ValueError('Mise a jour interrompue ; consultez le journal updater.log')
    except Exception as error:
        _state.update(status='error', message=str(error))
    finally:
        _lock.release()

def begin(install):
    if not _lock.acquire(blocking=False):
        return dict(_state)
    _state.update(status='checking', message='')
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
        return dict(_state)

    @router.post('/api/v1/system/update')
    async def update(request: Request):
        local(request)
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, 'Demande invalide') from None
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
