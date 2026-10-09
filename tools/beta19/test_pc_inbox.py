import os, sys, tempfile, types
import pymupdf
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import docpilot_pc_inbox as pc
# Unit tests must never open the real application database.
sys.modules['app.core.db']=types.SimpleNamespace(get_engine=lambda:(_ for _ in ()).throw(OSError('No application DB in this isolated test')))

with tempfile.TemporaryDirectory(dir=os.environ.get('RUNNER_TEMP')) as temporary:
    base=Path(temporary);root=base/'PC';root.mkdir()
    archive=root/'Archive';archive.mkdir()
    (archive/'facture-nas.pdf').write_bytes(b'never touch the NAS')
    synology=root/'SynologyDrive';synology.mkdir();(synology/'facture-sync.pdf').write_bytes(b'never touch synced files')
    system=root/'AppData';system.mkdir();(system/'invoice.pdf').write_bytes(b'not a local candidate')
    first=root/'facture-original.pdf';first.write_bytes(b'first invoice')
    duplicate=root/'invoice-duplicate.pdf';duplicate.write_bytes(b'existing invoice')
    unknown=root/'facture-photo.png';unknown.write_bytes(b'possible scanned invoice')
    pc.data_dir=lambda:base/'private-data'
    pc.excluded_roots=lambda:[archive.resolve(),pc.data_dir().resolve()]
    duplicate_hash=pc.digest_file(duplicate)
    sys.modules['docpilot_duplicates']=types.SimpleNamespace(lookup=lambda digest:{'matches':['Factures/Supplier/2026/invoice.pdf'] if digest==duplicate_hash else [],'verification_complete':True})
    pdf=pymupdf.open();page=pdf.new_page();page.insert_text((50,50),'Invoice 12345 - Total CHF 150.00');pdf.save(root/'reference-12345.pdf');pdf.close()
    pdf=pymupdf.open();page=pdf.new_page();page.insert_text((50,50),'A normal document without accounting data. '+('Some ordinary reading material. '*10));pdf.save(root/'notes.pdf');pdf.close()
    (root/'photo-vacances.png').write_bytes(b'ignore')
    (root/'tableau.xlsx').write_bytes(b'ignore')
    pc.scan([root])
    state=pc.snapshot();assert state['total']==4,state
    assert next(row for row in state['items'] if row['path'].endswith('reference-12345.pdf'))['kind']=='invoice'
    assert not any('SynologyDrive' in row['path'] or '/Archive/' in row['path'] or 'AppData' in row['path'] for row in state['items'])
    item=next(row for row in state['items'] if row['path']==str(duplicate.resolve()))
    assert item['status']=='duplicate' and item['matches']
    assert pc.snapshot(filter='duplicates')['total']==1
    assert next(row for row in state['items'] if row['path']==str(unknown.resolve()))['kind']=='invoice'
    app=FastAPI();pc.install(app);client=TestClient(app)
    assert client.get('/api/v1/pc-inbox').status_code==200
    assert client.get('/api/v1/pc-inbox?offset=-1').status_code==422
    assert client.post('/api/v1/pc-inbox',json={'action':'scan'},headers={'origin':'https://attacker.invalid'}).status_code==403
    assert client.post('/api/v1/pc-inbox',json={'action':'arbitrary'}).status_code==422
    assert client.get('/api/v1/pc-inbox/'+item['id']+'/file').content==duplicate.read_bytes()
    assert client.post('/api/v1/pc-inbox/'+item['id']+'/remove',json={'delete_file':True}).status_code==422
    # Removing a row leaves the source intact and remembers dismissal.
    assert client.post('/api/v1/pc-inbox/'+item['id']+'/remove',json={'delete_file':False}).status_code==200
    assert duplicate.exists()
    original_hash=pc.digest_file;reads=[]
    pc.digest_file=lambda path:reads.append(path) or original_hash(path)
    pc.scan([root]);assert not reads,'Unchanged candidates must reuse the local cache'
    assert all(row['id']!=item['id'] for row in pc.snapshot()['items'])
    # An explicit confirmed deletion affects only its discovered local file.
    row=next(row for row in pc.snapshot()['items'] if row['path']==str(first.resolve()))
    first.write_bytes(b'changed content after scan')
    assert client.post('/api/v1/pc-inbox/'+row['id']+'/remove',json={'delete_file':True,'confirm':True}).status_code==409
    assert first.exists()
    pc.scan([root]);assert first in reads
    assert client.post('/api/v1/pc-inbox/'+row['id']+'/remove',json={'delete_file':True,'confirm':True}).status_code==200
    assert not first.exists() and (archive/'facture-nas.pdf').read_bytes()==b'never touch the NAS'
    # A formerly local candidate that now falls inside an archive is protected.
    row=next(row for row in pc.snapshot()['items'] if row['path']==str(unknown.resolve()))
    pc.excluded_roots=lambda:[root.resolve()]
    assert client.post('/api/v1/pc-inbox/'+row['id']+'/remove',json={'delete_file':True,'confirm':True}).status_code==409
    assert unknown.exists()
    pc.excluded_roots=lambda:[archive.resolve(),pc.data_dir().resolve()]
    pc._state['running']=True
    assert client.post('/api/v1/pc-inbox',json={'action':'clear'}).status_code==409
    pc._state['running']=False
    assert client.post('/api/v1/pc-inbox',json={'action':'clear'},headers={'origin':'https://attacker.invalid'}).status_code==403
    assert client.post('/api/v1/pc-inbox',json={'action':'clear'}).status_code==200
    assert pc.snapshot()['total']==0 and duplicate.exists() and unknown.exists()
    pc.scan([root]);assert pc.snapshot()['total']==3
    assert not any(Path(r['path']).name in ('photo-vacances.png','tableau.xlsx') for r in pc.snapshot()['items'])
    assert any(event['action']=='pc_source_deleted' and event['actor'] and event['device'] for event in pc.snapshot()['events'])
print('PASS: local invoice candidates, NAS/system/Drive exclusions, verified duplicates, pagination/filtering, no cross-origin scan, dismissed sources preserved, unchanged hash reuse, changed-file protection, explicit deletion and durable actor/device/path audit.')
