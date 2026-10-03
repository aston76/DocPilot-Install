"""Offline profile import through DocPilot's bundled Python/SQLite runtime."""
import argparse, json, os, pathlib, shutil, sqlite3, datetime
from contextlib import closing

def apply(profile, root, program, data):
    profile,root,program,data=map(pathlib.Path,(profile,root,program,data))
    if not root.is_dir():raise ValueError('Dossier NAS inaccessible')
    data.mkdir(parents=True,exist_ok=True)
    backup=data/('profile-backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'));backup.mkdir()
    db=data/'docpilot.db';catalogue_path=program/'archive-catalogue.json'
    if db.exists():
        with closing(sqlite3.connect(db)) as source,closing(sqlite3.connect(backup/'docpilot.db')) as target:source.backup(target)
    if catalogue_path.exists():shutil.copy2(catalogue_path,backup/'archive-catalogue.json')
    catalogue=json.loads((profile/'archive-catalogue.json').read_text(encoding='utf-8-sig'))
    catalogue['root']=str(root)
    assert isinstance(catalogue['entries'],list) and all(isinstance(e.get('path'),str) for e in catalogue['entries'])
    temporary=catalogue_path.with_suffix('.json.pending')
    temporary.write_text(json.dumps(catalogue,ensure_ascii=False,indent=2),encoding='utf-8')
    script=(profile/'profile.sql').read_text(encoding='utf-8-sig').replace('__DOCPILOT_NAS_ROOT__',str(root).replace("'","''"))
    try:
        with closing(sqlite3.connect(db)) as connection:
            connection.executescript((profile/'schema.sql').read_text(encoding='utf-8-sig'))
            connection.executescript(script)
        os.replace(temporary,catalogue_path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {'destinations':len(catalogue['entries']),'backup':str(backup),'simulation':True}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--import-profile',required=True)
    parser.add_argument('--nas-root',required=True)
    parser.add_argument('--program-path',required=True)
    parser.add_argument('--data-path',required=True)
    args=parser.parse_args()
    result=apply(args.import_profile,args.nas_root,args.program_path,args.data_path)
    (pathlib.Path(args.data_path)/'profile-import-result.json').write_text(json.dumps(result),encoding='utf-8')
