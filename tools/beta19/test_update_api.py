import sys, pathlib, tempfile, os, json
from types import SimpleNamespace
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import docpilot_update as update
assert update.version_key('v0.1.0-beta.7')>update.version_key('v0.1.0-beta.6')
assert update.version_key('v0.1.0')>update.version_key('v0.1.0-beta.7')
try:update.version_key('malformed')
except ValueError:pass
else:raise AssertionError('Malformed version accepted')
app=FastAPI();update.install(app);client=TestClient(app)
assert client.get('/api/v1/system/update').status_code==200
assert client.post('/api/v1/system/update',json={'action':'install'},headers={'origin':'https://example.com'}).status_code==403
assert client.post('/api/v1/system/update',json={'action':'install'},headers={'sec-fetch-site':'cross-site'}).status_code==403
assert client.post('/api/v1/system/update',json={'action':'erase'}).status_code==422
assert client.post('/api/v1/system/update',content='broken').status_code==422
update._state['status']='installing'
assert client.post('/api/v1/documents/upload').status_code==423
assert client.get('/api/v1/system/update').status_code==200
update._state['status']='idle'
calls=[];original_begin=update.begin;update.begin=lambda install:calls.append(install) or dict(update._state)
with TestClient(app) as started:
    assert calls==[True], 'Automatic check must run with the existing app lifespan'
calls.clear()
assert client.post('/api/v1/system/update',json={'action':'check'}).status_code==200
assert client.post('/api/v1/system/update',json={'action':'install'}).status_code==200
assert calls==[False,True];update.begin=original_begin
# An unavailable server must not start an installer or crash the application.
original_latest=update.latest_release
update.latest_release=lambda:(_ for _ in ()).throw(OSError('Offline'))
assert update._lock.acquire(blocking=False)
update._worker(True)
assert update._state['status']=='error' and not update._lock.locked()
update.latest_release=original_latest
print('Update API verified: version ordering, cross-origin rejection, action validation, offline recovery.')

with tempfile.TemporaryDirectory() as temporary:
    os.environ['LOCALAPPDATA']=temporary
    path=pathlib.Path(temporary)/'DocPilot/update-state.json';path.parent.mkdir()
    update._state.update(status='installing',available=True,latest='new')
    path.write_text(json.dumps({'status':'downloading','percent':35,'message':'Downloading'}))
    assert client.get('/api/v1/system/update').json()['percent']==35
    path.write_text(json.dumps({'status':'error','message':'Offline'}))
    assert client.get('/api/v1/system/update').json()['status']=='error'
    assert update._state['status']=='error','Retry must be possible after error'
    update._state.update(status='current',available=False,latest=update.VERSION)
    path.write_text(json.dumps({'status':'complete','version':update.VERSION}))
    assert client.get('/api/v1/system/update').json()['status']=='current'
    assert client.post('/api/v1/system/update',json={'action':'dismiss'}).status_code==200
    assert client.get('/api/v1/system/update').json()['status']=='current','OK must dismiss the completed modal'
print('PASS: durable progress across requests, retry after error, completion acknowledged once.')

with tempfile.TemporaryDirectory() as temporary:
    os.environ['LOCALAPPDATA']=temporary
    path=pathlib.Path(temporary)/'DocPilot/update-state.json';path.parent.mkdir()
    path.write_text(json.dumps({'status':'complete','version':update.VERSION}))
    update._state.update(status='installing',available=True,latest=update.VERSION)
    for _ in range(3):
        status=update.update_status()
        assert status['status']=='current' and not status['available']
    update.latest_release=lambda:{'tag_name':update.VERSION}
    assert update._lock.acquire(False)
    update._worker(True)
    assert update._state['status']=='current' and not update._state['available']
    update.latest_release=original_latest
    assert "'-ShowProgress'" not in pathlib.Path(update.__file__).read_text()
print('PASS: completed version never offered again; repeated install is a no-op; silent installer.')

    # A previous successful installation must not hide a subsequent release.
with tempfile.TemporaryDirectory() as temporary:
    os.environ['LOCALAPPDATA']=temporary
    path=pathlib.Path(temporary)/'DocPilot/update-state.json';path.parent.mkdir()
    path.write_text(json.dumps({'status':'complete','version':update.VERSION}))
    update._state.update(status='available',available=True,latest='v0.1.0-beta.20')
    assert update.update_status()['available']
    update._state.update(status='checking',available=False)
    assert update.update_status()['status']=='checking'
print('PASS: old completion cannot hide a future release or interrupt its check.')

with tempfile.TemporaryDirectory() as temporary:
    os.environ['LOCALAPPDATA']=temporary
    path=pathlib.Path(temporary)/'DocPilot/update-state.json';path.parent.mkdir()
    path.write_text(json.dumps({'status':'complete','version':update.VERSION}))
    update._state.update(status='error',available=False,latest=None,message='Offline')
    result=update.update_status()
    assert result['status']=='current' and not result['available']
    assert result['verification_status']=='error' and result['check_error']=='Offline'
    assert 'Vérification des nouvelles versions indisponible' in result['message']
    assert 'dernière version' not in result['message'] and result['latest'] is None
    for _ in range(3):
        again=update.update_status()
        assert again['message']==result['message'] and again['latest'] is None
    update._state.update(status='checking',available=False)
    assert update.update_status()['status']=='checking'
    update.latest_release=lambda:{'tag_name':update.VERSION}
    assert update._lock.acquire(False)
    update._worker(False)
    assert update.update_status()['verification_status']=='ok'
    assert update.update_status()['check_error'] is None
    update.latest_release=original_latest
    # A known newer release whose installation failed remains a real error.
    update._state.update(status='error',available=True,latest='v0.1.0-beta.20',message='Script absent')
    assert update.update_status()['status']=='error'
    update._state.update(status='error',available=False,latest='v0.1.0-beta.20',message='Offline')
    assert update.update_status()['status']=='error'
print('PASS: successful install/restart and failed online check are distinct; lookup failure stays visible without claiming latest; known newer release errors remain actionable.')
