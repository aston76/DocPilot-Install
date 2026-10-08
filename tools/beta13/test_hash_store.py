import tempfile,sys,hashlib,time,json,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from docpilot_hash_store import Store,publish,shared_hints,valid_relative
with tempfile.TemporaryDirectory() as temporary:
    base=Path(temporary);root=base/'archive';root.mkdir()
    db=Store(base/'pc1'/'index.sqlite3');digest=hashlib.sha256(b'invoice').hexdigest()
    files={f'Factures/{i}.pdf':[10,i,i,digest if i==12000 else hashlib.sha256(str(i).encode()).hexdigest()] for i in range(25000)}
    data={'files':files,'entries':{},'last_scan':'test'}
    db.save(data)
    start=time.perf_counter();assert db.find(digest)==['Factures/12000.pdf'];elapsed=time.perf_counter()-start
    with db.connect() as conn:
        plan=conn.execute('EXPLAIN QUERY PLAN SELECT path FROM files WHERE sha=?',(digest,)).fetchall()
        assert any('files_sha' in str(row) for row in plan),'Hash lookup must use SQL index'
    publish(root,data,base/'pc1');hints,errors=shared_hints(root)
    assert hints['Factures/12000.pdf'][0][3]==digest and not errors
    # Independent PCs never edit the same shared snapshot.
    publish(root,{'files':{'Factures/second.pdf':[5,1,1,digest]}},base/'pc2')
    assert len(list((root/'.docpilot-index/v1').glob('*.json')))==2
    assert not list(root.rglob('*.sqlite3')),'SQLite must never live on the NAS'
    bad=root/'.docpilot-index/v1/bad.json';bad.write_text(json.dumps({'schema':1,'files':{'../../escape':[1,2,3,digest]}}))
    assert '../../escape' not in shared_hints(root)[0]
    assert not valid_relative('a/../b') and not valid_relative('C:/file')
    db.put('Factures/new.pdf',[1,2,3,digest]);assert len(db.find(digest))==2
    db.save({'files':{},'entries':{},'last_scan':'next'});assert not db.find(digest)
    print(f'PASS: 25000-row indexed lookup in {elapsed*1000:.2f} ms on this test machine; independent snapshots, path validation, no shared SQLite, removal and incremental insertion.')
