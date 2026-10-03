import sys, pathlib
from types import SimpleNamespace
sys.path[:0]=[str(pathlib.Path('tools/verification-deps').resolve()),str(pathlib.Path('_internal').resolve())]
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
