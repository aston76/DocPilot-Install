"""Isolated tests: invented PDFs, temporary folders, fake local DocPilot API."""
import email.parser
import email.policy
from contextlib import closing
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import pymupdf
from bridge import Bridge, read_config


def invented_pdf(label):
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'PDF FICTIF POUR TEST LOCAL - ' + label)
        return pdf.tobytes()


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='DocPilot-Kyocera-test-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'SCAN'
        self.source.mkdir()
        self.dbpath = self.root / 'docpilot.db'
        with closing(sqlite3.connect(self.dbpath)) as db:
            db.executescript('CREATE TABLE documents(id INTEGER PRIMARY KEY,sha256 TEXT,stored_sha256 TEXT,status TEXT);'
                             'CREATE TABLE document_sources(document_id INTEGER,source_sha256 TEXT);')
        self.documents = {}
        self.uploads = 0
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, data, status=200):
                payload = json.dumps(data).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                if self.path == '/api/v1/health':
                    return self.answer({'status': 'ok'})
                if self.path.startswith('/api/v1/documents/'):
                    return self.answer(parent.documents[int(self.path.rsplit('/', 1)[1])])
                self.answer({}, 404)

            def do_POST(self):
                if self.path != '/api/v1/documents/upload':
                    return self.answer({}, 404)
                body = self.rfile.read(int(self.headers['Content-Length']))
                message = email.parser.BytesParser(policy=email.policy.default).parsebytes(
                    ('Content-Type: ' + self.headers['Content-Type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + body)
                parts = list(message.iter_parts())
                assert len(parts) == 1 and parts[0].get_param('name', header='content-disposition') == 'file'
                payload = parts[0].get_payload(decode=True)
                parent.uploads += 1
                identifier = parent.uploads
                final = parent.root / 'archive' / ('facture-fictive-' + str(identifier) + '.pdf')
                final.parent.mkdir(exist_ok=True)
                final.write_bytes(payload)
                digest = hashlib.sha256(payload).hexdigest()
                with closing(sqlite3.connect(parent.dbpath)) as db:
                    db.execute('INSERT INTO documents VALUES(?,?,?,?)', (identifier, digest, digest, 'FILED_AUTO'))
                    db.commit()
                result = {'id': identifier, 'status': 'FILED_AUTO', 'final_path': str(final),
                          'dry_run': False, 'integrity_verified': True, 'error_message': None}
                parent.documents[identifier] = result
                self.answer(result, 201)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.bridge = Bridge({'source_dir': str(self.source), 'state_dir': str(self.root / 'state'),
                              'docpilot_db': str(self.dbpath), 'stable_seconds': 15,
                              'api_url': 'http://127.0.0.1:' + str(self.server.server_port)})

    def tearDown(self):
        self.bridge.db.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def state(self, path):
        return self.bridge.db.execute('SELECT * FROM files WHERE source=?', (str(path),)).fetchone()

    def mature(self, path):
        self.bridge.db.execute('UPDATE files SET stable_since=? WHERE source=?', (time.time() - 20, str(path)))
        self.bridge.db.commit()

    def test_existing_excluded_and_new_imported_once_original_retained(self):
        old = self.source / 'ancien.pdf'
        old.write_bytes(invented_pdf('ANCIEN'))
        self.bridge.initialize()
        self.bridge.poll()
        self.assertEqual(self.uploads, 0)
        self.assertEqual(self.state(old)['state'], 'excluded_existing')
        new = self.source / 'nouveau.pdf'
        content = invented_pdf('NOUVEAU')
        new.write_bytes(content)
        self.bridge.poll()
        self.bridge.poll()
        self.assertEqual(self.uploads, 0, 'Le fichier doit attendre la stabilité.')
        self.mature(new)
        self.bridge.poll()
        self.assertEqual(self.uploads, 1)
        self.assertEqual(self.state(new)['state'], 'filed_verified')
        self.assertEqual(new.read_bytes(), content)
        copy = self.source / 'copie.pdf'
        copy.write_bytes(content)
        self.bridge.poll()
        self.mature(copy)
        self.bridge.poll()
        self.assertEqual(self.uploads, 1, 'Une copie identique ne doit pas être réimportée.')
        self.assertEqual(self.state(copy)['state'], 'duplicate')
        self.assertIn(self.state(new)['final_path'], (self.root / 'state' / 'status.html').read_text(encoding='utf8'))

    def test_incomplete_pdf_not_submitted(self):
        path = self.source / 'incomplet.pdf'
        path.write_bytes(b'%PDF-1.7\nINCOMPLET')
        self.bridge.poll()
        self.mature(path)
        self.bridge.poll()
        self.assertEqual(self.uploads, 0)
        self.assertEqual(self.state(path)['state'], 'waiting')

    def test_timeout_never_blindly_resubmitted(self):
        path = self.source / 'interruption.pdf'
        path.write_bytes(invented_pdf('INTERRUPTION'))
        self.bridge.poll()
        self.mature(path)
        with patch.object(self.bridge, 'upload', side_effect=TimeoutError('Réponse perdue')) as upload:
            self.bridge.poll()
            self.bridge.poll()
            self.assertEqual(upload.call_count, 1)
        self.bridge.db.execute('UPDATE submissions SET started=?', (time.time() - 700,))
        self.bridge.db.commit()
        self.bridge.poll()
        self.assertEqual(self.state(path)['state'], 'needs_check')

    def test_uncertain_and_dry_run_not_claimed_as_filed(self):
        path = self.source / 'verification.pdf'
        path.write_bytes(invented_pdf('VERIFICATION'))
        self.bridge.poll()
        self.bridge.receipt(path, {'id': 7, 'status': 'TO_VALIDATE', 'final_path': None})
        self.assertEqual(self.state(path)['state'], 'pending_review')
        self.bridge.receipt(path, {'id': 7, 'status': 'FILED_AUTO', 'dry_run': True, 'final_path': str(self.root / 'absent.pdf')})
        self.assertEqual(self.state(path)['state'], 'simulation')

    def test_wrong_file_not_verified(self):
        path = self.source / 'integrite.pdf'
        path.write_bytes(invented_pdf('INTEGRITE'))
        self.bridge.poll()
        self.mature(path)
        self.bridge.poll()
        target = Path(self.state(path)['final_path'])
        target.write_bytes(invented_pdf('AUTRE FICHIER'))
        self.bridge.receipt(path, self.documents[1])
        self.assertEqual(self.state(path)['state'], 'filed_reported')

    def test_generic_config_expands_environment_without_editing_file(self):
        config = self.root / 'config.json'
        original = json.dumps({'state_dir': '${DOCPILOT_TEST_HOME}/state'})
        config.write_text(original, encoding='utf8')
        with patch.dict(os.environ, {'DOCPILOT_TEST_HOME': str(self.root)}):
            self.assertEqual(Path(read_config(config)['state_dir']), self.root / 'state')
        self.assertEqual(config.read_text(encoding='utf8'), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
