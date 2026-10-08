"""Embedded SQLite index; optional per-device snapshots on the existing archive.

No SQLite file is opened on SMB/Drive. Shared snapshots are hints, not proof of
absence or a distributed lock. Candidate bytes remain verified by the caller.
"""
import hashlib,json,os,sqlite3,uuid
from pathlib import Path,PurePosixPath

SCHEMA=1

def valid_relative(path):
    return isinstance(path,str) and bool(path) and not path.startswith(('/', '\\')) and '\\' not in path and ':' not in path and all(p not in ('','.','..') for p in path.split('/'))

class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,size INTEGER,mtime INTEGER,ctime INTEGER,sha TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS files_sha ON files(sha)')
            db.execute('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    def connect(self):
        return sqlite3.connect(self.path,timeout=10)
    def load(self,root):
        with self.connect() as db:
            files={p:[size,mtime,ctime,sha] for p,size,mtime,ctime,sha in db.execute('SELECT path,size,mtime,ctime,sha FROM files')}
            meta={k:json.loads(v) for k,v in db.execute('SELECT key,value FROM metadata')}
        entries={}
        for p,v in files.items():entries.setdefault(v[3],[]).append(p)
        return dict(meta,root=str(root),files=files,entries=entries,indexed_files=len(files))
    def save(self,data):
        rows=[(p,*v) for p,v in data['files'].items()]
        metadata={k:v for k,v in data.items() if k not in ('files','entries')}
        with self.connect() as db:
            db.execute('CREATE TEMP TABLE latest(path TEXT PRIMARY KEY,size INTEGER,mtime INTEGER,ctime INTEGER,sha TEXT)')
            db.executemany('INSERT INTO latest VALUES(?,?,?,?,?)',rows)
            db.execute('DELETE FROM files WHERE path NOT IN (SELECT path FROM latest)')
            db.execute('INSERT INTO files SELECT * FROM latest WHERE 1 ON CONFLICT(path) DO UPDATE SET size=excluded.size,mtime=excluded.mtime,ctime=excluded.ctime,sha=excluded.sha WHERE files.size IS NOT excluded.size OR files.mtime IS NOT excluded.mtime OR files.ctime IS NOT excluded.ctime OR files.sha IS NOT excluded.sha')
            db.executemany('INSERT OR REPLACE INTO metadata VALUES(?,?)',[(k,json.dumps(v,ensure_ascii=False)) for k,v in metadata.items()])
    def put(self,path,value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)',(path,*value))
    def find(self,digest):
        with self.connect() as db:return [row[0] for row in db.execute('SELECT path FROM files WHERE sha=?',(digest,))]

def device_id(local):
    path=Path(local)/'index-device-id'
    try:
        value=path.read_text().strip();uuid.UUID(value);return value
    except (OSError,ValueError):
        value=str(uuid.uuid4());path.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive create prevents two local launchers inventing different IDs.
        try:
            with path.open('x') as out:out.write(value)
        except FileExistsError:return path.read_text().strip()
        return value

def shared_hints(root):
    hints={};errors=[];folder=Path(root)/'.docpilot-index'/'v1'
    if not folder.is_dir():return hints,errors
    for path in list(folder.glob('*.json'))[:128]:
        try:
            if path.is_symlink() or path.stat().st_size>32*1024*1024:continue
            data=json.loads(path.read_text(encoding='utf-8'))
            if data.get('schema')!=SCHEMA:continue
            for p,v in data.get('files',{}).items():
                if not valid_relative(p) or not isinstance(v,list) or len(v)!=4:continue
                if not all(isinstance(n,int) and n>=0 for n in v[:3]):continue
                if not isinstance(v[3],str) or len(v[3])!=64 or any(c not in '0123456789abcdef' for c in v[3]):continue
                hints.setdefault(p,[]).append(v)
        except (OSError,ValueError,AttributeError):errors.append(path.name)
    return hints,errors

def publish(root,data,local):
    folder=Path(root)/'.docpilot-index'/'v1'
    if not folder.resolve().is_relative_to(Path(root).resolve()):raise OSError('Index partagé hors archive')
    folder.mkdir(parents=True,exist_ok=True)
    if folder.is_symlink() or not folder.resolve().is_relative_to(Path(root).resolve()):raise OSError('Index partagé hors archive')
    path=folder/(device_id(local)+'.json')
    payload=json.dumps({'schema':SCHEMA,'files':data['files']},ensure_ascii=False,separators=(',',':'))
    if path.exists() and path.read_text(encoding='utf-8')==payload:return
    temporary=folder/(path.stem+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(payload,encoding='utf-8');os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
