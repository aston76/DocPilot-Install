"""Import new local Kyocera PDFs through DocPilot's supported API.

Original PDFs are never moved, renamed or deleted. Existing files are excluded
explicitly by --initialize. Classification remains DocPilot's responsibility.
"""
import argparse
import ctypes
from contextlib import closing
import hashlib
import html
import json
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

MAX_BYTES = 50 * 1024 * 1024
NONLOCAL = 0x1000 | 0x40000 | 0x400000
TERMINAL = {'excluded_existing', 'duplicate', 'pending_review', 'filed_verified',
            'filed_reported', 'simulation', 'error', 'needs_check'}


def read_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    for key in ('source_dir', 'state_dir', 'docpilot_db', 'docpilot_exe'):
        if config.get(key):
            config[key] = os.path.expanduser(os.path.expandvars(config[key]))
    return config


def signature(path):
    stat = path.stat()
    if getattr(stat, 'st_file_attributes', 0) & NONLOCAL:
        raise ValueError('PDF non disponible localement ; téléchargement automatique désactivé.')
    if path.is_symlink():
        raise ValueError('Lien symbolique exclu.')
    return json.dumps([stat.st_size, stat.st_mtime_ns])


class Bridge:
    def __init__(self, config):
        self.config = config
        self.root = Path(config['state_dir'])
        self.root.mkdir(parents=True, exist_ok=True)
        self.source = Path(config['source_dir'])
        parsed = urllib.parse.urlsplit(config['api_url'])
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path:
            raise ValueError('API DocPilot : adresse locale 127.0.0.1 requise.')
        if str(self.source).startswith('\\\\'):
            raise ValueError('Le dossier SCAN doit être local, pas un chemin NAS.')
        self.db = sqlite3.connect(self.root / 'state.sqlite3')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS files (
            source TEXT PRIMARY KEY, signature TEXT NOT NULL,
            stable_since REAL NOT NULL, digest TEXT, state TEXT NOT NULL,
            document_id INTEGER, final_path TEXT, error TEXT, updated REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS submissions (
            digest TEXT PRIMARY KEY, state TEXT NOT NULL,
            document_id INTEGER, source TEXT NOT NULL, started REAL NOT NULL);
        ''')
        self.last_launch = 0
        self.last_refresh = 0

    def request(self, endpoint, body=None, content_type=None, timeout=15):
        headers = {'Accept': 'application/json'}
        if content_type:
            headers['Content-Type'] = content_type
        req = urllib.request.Request(self.config['api_url'] + endpoint,
                                     data=body, headers=headers)
        # Never send these files through a configured system proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as response:
            return json.load(response)

    def update(self, source, **values):
        values['updated'] = time.time()
        sql = ','.join(f'{key}=?' for key in values)
        self.db.execute(f'UPDATE files SET {sql} WHERE source=?',
                        [*values.values(), str(source)])
        self.db.commit()

    def initialize(self):
        if not self.source.is_dir():
            raise ValueError('Dossier SCAN introuvable.')
        for path in self.source.glob('*.pdf'):
            if self.db.execute('SELECT 1 FROM files WHERE source=?', (str(path),)).fetchone():
                continue
            sig = signature(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if signature(path) != sig:
                raise ValueError('Un PDF existant est en cours de modification.')
            now = time.time()
            self.db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?)',
                            (str(path), sig, now, digest, 'excluded_existing',
                             None, None, None, now))
            self.db.execute('INSERT OR IGNORE INTO submissions VALUES(?,?,?,?,?)',
                            (digest, 'excluded_existing', None, str(path), now))
        self.db.commit()
        self.render()

    def local_document(self, digest):
        path = Path(self.config['docpilot_db'])
        if not path.is_file():
            return None
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
            row = db.execute('''SELECT id FROM documents
                WHERE (sha256=? OR stored_sha256=?) AND status != 'DELETED'
                ORDER BY id DESC LIMIT 1''', (digest, digest)).fetchone()
            if not row:
                row = db.execute('''SELECT d.id FROM documents d JOIN document_sources s
                    ON s.document_id=d.id WHERE s.source_sha256=? AND d.status != 'DELETED'
                    ORDER BY d.id DESC LIMIT 1''', (digest,)).fetchone()
            return row[0] if row else None

    def capture(self, path):
        before = signature(path)
        size = json.loads(before)[0]
        if size <= 0 or size > MAX_BYTES:
            raise ValueError('Taille du PDF invalide : maximum 50 Mo.')
        data = path.read_bytes()
        if signature(path) != before:
            raise ValueError('Le PDF est encore en cours d’écriture.')
        if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-2048:]:
            raise ValueError('PDF incomplet ou invalide.')
        import pymupdf
        with pymupdf.open(stream=data, filetype='pdf') as pdf:
            if pdf.needs_pass or not len(pdf):
                raise ValueError('PDF protégé ou sans page.')
        return data, hashlib.sha256(data).hexdigest()

    def upload(self, path, data):
        boundary = 'DocPilotKyocera' + uuid.uuid4().hex
        # Multipart headers use a simple ASCII name. The original name is retained
        # in the bridge history; source path and file are never changed.
        name = 'kyocera-' + hashlib.sha256(data).hexdigest()[:12] + '.pdf'
        head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{name}"\r\nContent-Type: application/pdf\r\n\r\n').encode()
        body = head + data + f'\r\n--{boundary}--\r\n'.encode()
        return self.request('/api/v1/documents/upload', body,
                            'multipart/form-data; boundary=' + boundary, timeout=600)

    def receipt(self, path, document):
        identifier = document.get('id')
        if type(identifier) is not int:
            raise ValueError('DocPilot n’a pas confirmé l’identifiant du document.')
        status = document.get('status')
        final = document.get('final_path')
        error = document.get('error_message')
        if document.get('dry_run') and status in ('FILED', 'FILED_AUTO', 'VALIDATED', 'STORED'):
            state = 'simulation'
        elif status in ('FILED', 'FILED_AUTO', 'VALIDATED', 'STORED') and final:
            verified = False
            if not str(final).startswith('\\\\'):
                target = Path(final)
                try:
                    signature(target)
                    db_path = Path(self.config['docpilot_db'])
                    with closing(sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
                        stored = db.execute('SELECT stored_sha256 FROM documents WHERE id=?',
                                            (identifier,)).fetchone()
                    verified = bool(stored and stored[0] and target.is_file() and
                                    hashlib.sha256(target.read_bytes()).hexdigest() == stored[0])
                except (OSError, ValueError, sqlite3.Error):
                    pass
            state = 'filed_verified' if verified else 'filed_reported'
        elif status == 'DUPLICATE':
            state = 'duplicate'
        elif status == 'ERROR':
            state = 'error'
        else:
            state = 'pending_review'
        current = self.db.execute('SELECT state,document_id,final_path,error FROM files WHERE source=?',
                                  (str(path),)).fetchone()
        if current and tuple(current) == (state, identifier, final, error):
            return
        self.update(path, state=state, document_id=identifier, final_path=final, error=error)
        logging.info('%s : %s, document %s, emplacement %s', path.name, state, identifier, final)

    def available(self):
        try:
            self.request('/api/v1/health')
            return True
        except (OSError, ValueError):
            executable = self.config.get('docpilot_exe')
            if executable and time.time() - self.last_launch > 90:
                self.last_launch = time.time()
                subprocess.Popen([executable], cwd=str(Path(executable).parent),
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                logging.info('Ouverture de DocPilot pour un nouveau PDF en attente.')
            return False

    def poll(self):
        if not self.source.is_dir():
            logging.warning('Dossier SCAN indisponible.')
            self.render()
            return
        now = time.time()
        for path in self.source.glob('*.pdf'):
            try:
                sig = signature(path)
            except (OSError, ValueError):
                continue
            row = self.db.execute('SELECT * FROM files WHERE source=?', (str(path),)).fetchone()
            if not row or row['signature'] != sig:
                self.db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?)',
                                (str(path), sig, now, None, 'waiting', None, None, None, now))
                self.db.commit()
                continue
            if row['state'] in TERMINAL:
                continue
            if now - row['stable_since'] < self.config.get('stable_seconds', 15):
                continue
            if not self.available():
                continue
            try:
                data, digest = self.capture(path)
                self.update(path, digest=digest)
                known = self.db.execute('SELECT * FROM submissions WHERE digest=?', (digest,)).fetchone()
                if known:
                    if known['document_id']:
                        if str(path) != known['source']:
                            self.update(path, state='duplicate', document_id=known['document_id'],
                                        error='Ce même fichier a déjà été importé par la liaison automatique.')
                        else:
                            self.receipt(path, self.request('/api/v1/documents/' + str(known['document_id'])))
                    elif known['state'] == 'excluded_existing':
                        self.update(path, state='excluded_existing')
                    else:
                        found = self.local_document(digest)
                        if found:
                            self.db.execute('UPDATE submissions SET document_id=?,state=? WHERE digest=?',
                                            (found, 'imported', digest))
                            self.db.commit()
                            self.receipt(path, self.request('/api/v1/documents/' + str(found)))
                        elif now - known['started'] > 660:
                            self.update(path, state='needs_check', error='Import incertain : aucun renvoi automatique pour éviter un doublon.')
                    continue
                found = self.local_document(digest)
                if found:
                    self.db.execute('INSERT INTO submissions VALUES(?,?,?,?,?)',
                                    (digest, 'imported', found, str(path), now))
                    self.db.commit()
                    self.update(path, state='duplicate', document_id=found,
                                error='Ce même fichier est déjà enregistré dans DocPilot.')
                    continue
                self.db.execute('INSERT INTO submissions VALUES(?,?,?,?,?)',
                                (digest, 'submitting', None, str(path), now))
                self.db.commit()
                self.update(path, state='submitting', error=None)
                self.render()
                result = self.upload(path, data)
                if type(result.get('id')) is not int:
                    raise ValueError('Réponse DocPilot sans identifiant : vérifier l’import.')
                self.db.execute('UPDATE submissions SET document_id=?,state=? WHERE digest=?',
                                (result['id'], 'imported', digest))
                self.db.commit()
                self.receipt(path, result)
            except (OSError, ValueError, sqlite3.Error) as error:
                logging.exception('Import interrompu pour %s', path.name)
                # A timed-out POST may already have imported the file. Its durable
                # submission record prevents any blind retry.
                self.update(path, error=str(error)[:300])
        self.refresh_receipts()
        self.render()

    def refresh_receipts(self):
        if time.time() - self.last_refresh < 60:
            return
        self.last_refresh = time.time()
        rows = self.db.execute('SELECT * FROM files WHERE document_id IS NOT NULL AND state != ? ORDER BY updated DESC LIMIT 20',
                               ('excluded_existing',)).fetchall()
        for row in rows:
            if row['state'] == 'duplicate':
                continue
            try:
                self.receipt(Path(row['source']), self.request('/api/v1/documents/' + str(row['document_id'])))
            except (OSError, ValueError):
                pass

    def render(self):
        labels = {'excluded_existing': 'Exclu : présent avant activation', 'waiting': 'En attente du PDF complet',
                  'submitting': 'Analyse dans DocPilot', 'duplicate': 'Doublon : aucun nouvel import',
                  'pending_review': 'À vérifier dans DocPilot', 'filed_verified': 'Classé — fichier local confirmé',
                  'filed_reported': 'Classé selon DocPilot — fichier local à vérifier',
                  'simulation': 'Simulation : aucun classement réel', 'error': 'Erreur : à vérifier',
                  'needs_check': 'Import incertain : à vérifier'}
        rows = [dict(row) for row in self.db.execute('SELECT * FROM files ORDER BY updated DESC LIMIT 100')]
        payload = {'updated': time.time(), 'source_dir': str(self.source), 'files': rows}
        temporary = self.root / 'status.json.tmp'
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.root / 'status.json')
        lines = []
        for row in rows:
            destination = html.escape(row['final_path'] or '')
            if row['final_path'] and not str(row['final_path']).startswith('\\\\'):
                destination = '<a href="' + html.escape(Path(row['final_path']).as_uri(), quote=True) + '">' + destination + '</a>'
            doclink = (' — document ' + str(row['document_id'])) if row['document_id'] else ''
            lines.append('<tr><td>' + html.escape(Path(row['source']).name) + '</td><td>' +
                         html.escape(labels.get(row['state'], row['state']) + doclink) + '</td><td>' +
                         destination + '<small>' + html.escape(row['error'] or '') + '</small></td></tr>')
        page = '''<!doctype html><html lang="fr"><meta charset="utf-8"><meta http-equiv="refresh" content="15">
        <title>Kyocera → DocPilot</title><style>body{font:16px system-ui;margin:36px;color:#302129;background:#faf8f8}
        table{border-collapse:collapse;width:100%;background:white}td,th{padding:14px;text-align:left;border-bottom:1px solid #ddd}
        td{overflow-wrap:anywhere}small{display:block;color:#7b3343}a{color:#641b2c}</style>
        <h1>Kyocera → DocPilot</h1><p>Les nouveaux PDF sont importés et analysés automatiquement.
        DocPilot classe les factures reconnues ; les cas incertains restent à vérifier.</p>
        <p>Les originaux du dossier SCAN sont conservés. Un fichier confirmé dans le dossier local Synology Drive
        ne prouve pas sa réception sur le NAS.</p><p><a href="http://127.0.0.1:8765">Ouvrir DocPilot</a></p>
        <table><thead><tr><th>Document</th><th>État</th><th>Emplacement réel après classement</th></tr></thead><tbody>'''
        stamp = time.strftime('%d/%m/%Y à %H:%M:%S')
        page = page.replace('<h1>Kyocera → DocPilot</h1>', '<h1>Kyocera → DocPilot</h1><p>Dernière mise à jour : ' + stamp + '</p>')
        temporary = self.root / 'status.html.tmp'
        temporary.write_text(page + ''.join(lines) + '</tbody></table></html>', encoding='utf-8')
        temporary.replace(self.root / 'status.html')


def acquire_mutex():
    if os.name != 'nt':
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.WaitForSingleObject.restype = ctypes.c_ulong
    handle = kernel.CreateMutexW(None, False, 'Local\\DocPilotKyoceraAuto-' + os.environ.get('USERNAME', 'user'))
    if not handle or kernel.WaitForSingleObject(handle, 0) not in (0, 0x80):
        raise SystemExit('La liaison Kyocera → DocPilot est déjà active.')
    return handle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--disable', action='store_true')
    args = parser.parse_args()
    config = read_config(args.config)
    if args.disable:
        config['enabled'] = False
        temporary = Path(args.config).with_suffix('.json.tmp')
        temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(args.config)
        return
    if not config.get('enabled', True):
        return
    root = Path(config['state_dir'])
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=root / 'bridge.log', encoding='utf-8', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    mutex = acquire_mutex()
    bridge = Bridge(config)
    if args.initialize:
        bridge.initialize()
        return
    logging.info('Liaison active, nouveaux PDF dans %s.', bridge.source)
    while True:
        latest = read_config(args.config)
        if not latest.get('enabled', True):
            logging.info('Liaison désactivée ; aucun nouveau PDF ne sera importé.')
            break
        try:
            bridge.poll()
        except Exception:
            logging.exception('Cycle interrompu ; les originaux restent conservés.')
        if args.once:
            break
        time.sleep(config.get('poll_seconds', 5))


if __name__ == '__main__':
    main()
