"""Explicit local eSCL PDF acquisition; no import, OCR or document filing."""
import argparse
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import time
from urllib.parse import urlsplit
import uuid
import xml.etree.ElementTree as ET

SCAN = 'http://schemas.hp.com/imaging/escl/2011/05/03'
PWG = 'http://www.pwg.org/schemas/2010/12/sm'
LIMIT = 50 * 1024 * 1024
ET.register_namespace('scan', SCAN)
ET.register_namespace('pwg', PWG)


def settings_a4():
    root = ET.Element(f'{{{SCAN}}}ScanSettings')
    def add(parent, ns, key, value):
        ET.SubElement(parent, f'{{{ns}}}{key}').text = str(value)
    add(root, PWG, 'Version', '2.9')
    add(root, SCAN, 'Intent', 'Document')
    regions = ET.SubElement(root, f'{{{PWG}}}ScanRegions')
    region = ET.SubElement(regions, f'{{{PWG}}}ScanRegion')
    for key, value in [('ContentRegionUnits', 'escl:ThreeHundredthsOfInches'),
                       ('Height', 3508), ('Width', 2480), ('XOffset', 0), ('YOffset', 0)]:
        add(region, PWG, key, value)
    for ns, key, value in [(PWG, 'InputSource', 'Platen'), (SCAN, 'ColorMode', 'RGB24'),
                           (PWG, 'DocumentFormat', 'application/pdf'),
                           (SCAN, 'XResolution', 200), (SCAN, 'YResolution', 200)]:
        add(root, ns, key, value)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def job_path(location, endpoint):
    target, base = urlsplit(location), urlsplit(endpoint)
    if target.scheme and target.scheme != 'https':
        raise ValueError('Le travail impose une connexion non chiffrée.')
    if target.netloc and (target.hostname, target.port or 443) != (base.hostname, base.port or 443):
        raise ValueError('Le travail indique une autre destination.')
    prefix = base.path.rstrip('/') + '/ScanJobs/'
    if (not target.path.startswith(prefix) or not target.path[len(prefix):]
            or target.query or target.fragment or target.username or target.password
            or '%' in target.path or '\\' in target.path
            or any(part in ('.', '..') for part in target.path.split('/'))):
        raise ValueError('Chemin du travail inattendu.')
    return target.path.rstrip('/')


class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, context, address, fingerprint):
        super().__init__(host, port=port, context=context, timeout=60)
        self.address, self.fingerprint = address, fingerprint

    def connect(self):
        raw = socket.create_connection((self.address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
            actual = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
            if actual != self.fingerprint:
                self.sock.close()
                raise ssl.SSLError('Le certificat du scanner a changé.')
        except BaseException:
            raw.close()
            raise


class Scanner:
    def __init__(self, endpoint, address, certificate, fingerprint):
        self.endpoint = endpoint.rstrip('/')
        parsed = urlsplit(self.endpoint)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or not parsed.path.endswith('/eSCL')):
            raise ValueError('Adresse HTTPS eSCL invalide.')
        ipaddress.ip_address(address)
        self.address, self.host, self.port = address, parsed.hostname, parsed.port or 443
        self.path = parsed.path
        self.fingerprint = fingerprint.replace(':', '').lower()
        if len(self.fingerprint) != 64 or any(c not in '0123456789abcdef' for c in self.fingerprint):
            raise ValueError('Empreinte SHA256 invalide.')
        der = Path(certificate).read_bytes()
        if hashlib.sha256(der).hexdigest() != self.fingerprint:
            raise ValueError('Le certificat fourni ne correspond pas à l’empreinte approuvée.')
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(der))

    def request(self, method, path, body=None):
        conn = PinnedConnection(self.host, self.port, self.context, self.address, self.fingerprint)
        try:
            conn.request(method, path, body=body,
                         headers={'Content-Type': 'text/xml'} if body is not None else {})
            response = conn.getresponse()
            data = response.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise ValueError('Réponse trop volumineuse.')
            return response.status, {k.lower(): v for k, v in response.getheaders()}, data
        finally:
            conn.close()

    def read_xml(self, resource):
        code, _, data = self.request('GET', self.path + '/' + resource)
        if code != 200:
            raise RuntimeError(f'{resource} : HTTP {code}')
        if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
            raise ValueError('Déclarations XML non acceptées.')
        return ET.fromstring(data)

    def probe(self):
        caps, status = self.read_xml('ScannerCapabilities'), self.read_xml('ScannerStatus')
        return {'model': caps.findtext(f'{{{PWG}}}MakeAndModel'),
                'state': status.findtext(f'{{{PWG}}}State'),
                'pdf': any(e.text == 'application/pdf' for e in caps.findall(
                    f'.//{{{SCAN}}}PlatenInputCaps//{{{PWG}}}DocumentFormat'))}

    def scan(self, output_dir):
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        # Fail on a non-writable destination before acquiring a page.
        temporary = folder / ('escl-' + uuid.uuid4().hex + '.tmp')
        with temporary.open('xb') as output:
            caps = self.read_xml('ScannerCapabilities')
            platen = caps.find(f'{{{SCAN}}}Platen/{{{SCAN}}}PlatenInputCaps')
            if platen is None or not self.supports_a4_pdf(platen):
                raise ValueError('PDF A4 couleur 200 dpi sur vitre non annoncé par le scanner.')
            status = self.read_xml('ScannerStatus')
            if status.findtext(f'{{{PWG}}}State') != 'Idle':
                raise RuntimeError('Scanner occupé : aucun travail lancé.')
            code, headers, _ = self.request('POST', self.path + '/ScanJobs', settings_a4())
            if code != 201:
                raise RuntimeError(f'Création du travail : HTTP {code}')
            location = job_path(headers.get('location', ''), self.endpoint)
            code, headers, data = self.request('GET', location + '/NextDocument')
            if (code != 200 or headers.get('content-type', '').split(';')[0].strip() != 'application/pdf'
                    or not data.startswith(b'%PDF-') or b'%%EOF' not in data[-4096:]):
                raise RuntimeError(f'PDF complet non reçu : HTTP {code}. Travail : {location}')
            output.write(data)
        destination = temporary.with_suffix('.pdf')
        temporary.rename(destination)
        return {'output': str(destination.resolve()), 'bytes': len(data), 'format': 'A4', 'dpi': 200}

    @staticmethod
    def supports_a4_pdf(platen):
        if int(platen.findtext(f'{{{SCAN}}}MaxWidth', '0')) < 2480 or int(platen.findtext(f'{{{SCAN}}}MaxHeight', '0')) < 3508:
            return False
        for profile in platen.findall(f'.//{{{SCAN}}}SettingProfile'):
            formats = [e.text for e in profile.findall(f'.//{{{PWG}}}DocumentFormat')]
            colors = [e.text for e in profile.findall(f'.//{{{SCAN}}}ColorMode')]
            resolutions = profile.findall(f'.//{{{SCAN}}}DiscreteResolution')
            if ('application/pdf' in formats and 'RGB24' in colors and any(
                    r.findtext(f'{{{SCAN}}}XResolution') == '200' and
                    r.findtext(f'{{{SCAN}}}YResolution') == '200' for r in resolutions)):
                return True
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('probe', 'scan'))
    parser.add_argument('--endpoint', required=True, help='HTTPS eSCL URL using the certificate hostname')
    parser.add_argument('--address', required=True, help='Scanner IP from device discovery')
    parser.add_argument('--certificate', required=True, help='Previously approved DER certificate')
    parser.add_argument('--sha256', required=True, help='Previously approved certificate fingerprint')
    parser.add_argument('--output-dir', help='Local test directory; required for scan')
    args = parser.parse_args()
    if args.action == 'scan' and not args.output_dir:
        parser.error('--output-dir est obligatoire pour scan')
    started = time.monotonic()
    try:
        scanner = Scanner(args.endpoint, args.address, args.certificate, args.sha256)
        result = scanner.probe() if args.action == 'probe' else scanner.scan(args.output_dir)
        print(json.dumps(dict(result, success=True, seconds=round(time.monotonic()-started, 2))))
    except (ValueError, OSError, RuntimeError, ET.ParseError) as error:
        print(json.dumps({'success': False, 'error': str(error)}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
