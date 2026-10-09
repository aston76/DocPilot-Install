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
import subprocess
import threading
import base64
import xml.etree.ElementTree as ET

SCAN = 'http://schemas.hp.com/imaging/escl/2011/05/03'
PWG = 'http://www.pwg.org/schemas/2010/12/sm'
LIMIT = 50 * 1024 * 1024
_discovered = {}
_discover_until = 0
_challenges = {}
_configuration_lock = threading.RLock()
_DISCOVERY = r'''
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$items=@(Get-PnpDevice -PresentOnly | Where-Object {$_.InstanceId -like 'SWD\Escl\*'} | ForEach-Object {
 $d=$_; $urls=@(Get-PnpDeviceProperty -InstanceId $d.InstanceId | Where-Object {$_.Data -is [string] -and $_.Data -match '^https://.*/eSCL$'} | ForEach-Object {$_.Data})
 foreach($u in $urls){@{endpoint=$u;name=$d.FriendlyName}}
})
ConvertTo-Json -InputObject $items -Compress
'''
_CERTIFICATE = r'''
param([string]$Address,[int]$Port)
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
Add-Type -TypeDefinition @'
using System;using System.Net.Sockets;using System.Net.Security;using System.Security.Cryptography.X509Certificates;
public static class DocPilotInspectCertificate {
 public static string[] Inspect(string address,int port){string[] result=null;using(var client=new TcpClient()){if(!client.ConnectAsync(address,port).Wait(5000))throw new Exception("Connexion expirée");using(var tls=new SslStream(client.GetStream(),false,(sender,certificate,chain,errors)=>{var c=new X509Certificate2(certificate);result=new string[]{Convert.ToBase64String(c.Export(X509ContentType.Cert)),c.GetNameInfo(X509NameType.DnsName,false),c.Subject,c.NotBefore.ToUniversalTime().ToString("O"),c.NotAfter.ToUniversalTime().ToString("O")};return false;})){tls.ReadTimeout=5000;tls.WriteTimeout=5000;try{tls.AuthenticateAsClient(address);}catch{}}}if(result==null)throw new Exception("Certificat inaccessible");return result;}
}
'@
$r=[DocPilotInspectCertificate]::Inspect($Address,$Port)
ConvertTo-Json -InputObject @{der=$r[0];hostname=$r[1];subject=$r[2];valid_from=$r[3];valid_until=$r[4]} -Compress
'''
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
        # Release only the job created by this acquisition, after preserving its PDF.
        # Some devices keep the session reserved until a client closes the job.
        cleanup = None
        try:cleanup, _, _ = self.request('DELETE', location)
        except (OSError, ValueError):pass
        return {'output': str(destination.resolve()), 'bytes': len(data), 'format': 'A4', 'dpi': 200,
                'cleanup_status': cleanup}

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


def connections(folder):
    """Only explicitly provisioned scanner certificates are trusted."""
    try:
        records = json.loads((Path(folder)/'escl-connections.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    result = {}
    if not isinstance(records, list):
        return result
    for record in records[:32]:
        if not isinstance(record, dict):
            continue
        try:
            endpoint, address, fingerprint = (record[k] for k in ('endpoint', 'address', 'sha256'))
            if not all(isinstance(v, str) for v in (endpoint, address, fingerprint)):
                continue
            fingerprint = fingerprint.replace(':', '').lower()
            if len(fingerprint) != 64 or any(c not in '0123456789abcdef' for c in fingerprint):
                continue
            certificate = Path(folder)/'certificates'/(fingerprint+'.der')
            scanner = Scanner(endpoint, address, certificate, fingerprint)
            device = connection_id(endpoint, address)
            result[device] = {'scanner': scanner, 'name': str(record.get('name', 'Scanner réseau'))[:100]}
        except (OSError, ValueError):
            continue
    return result


def devices(folder):
    trusted = connections(folder)
    found = discover()
    records = dict(found)
    for device, record in trusted.items():
        records[device] = {'name': record['name']}
    return [dict(id=device, name=record['name'], backend='escl', approved=device in trusted,
                 label=record['name']+' · API directe · PDF A4 · vitre'+(' · à approuver' if device not in trusted else ''),
                 connection='HTTPS eSCL', windows_default=False) for device, record in records.items()]


def connection_id(endpoint, address):
    url = urlsplit(endpoint)
    identity = address+':'+str(url.port or 443)+url.path.rstrip('/')
    return 'escl-api:'+hashlib.sha256(identity.encode()).hexdigest()[:24]


def powershell(script, arguments=()):
    import os
    env=dict(os.environ)
    env['PSModulePath']=str(Path(env.get('SystemRoot', r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/Modules')
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script,*arguments],
                          env=env,capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise ValueError('Détection réseau ou certificat indisponible.')
    return json.loads(result.stdout.decode('utf-8-sig').strip())


def discover():
    global _discover_until, _discovered
    with _configuration_lock:
        if time.monotonic() < _discover_until:
            return dict(_discovered)
        found={}
        try:
            records=powershell(_DISCOVERY)
            if isinstance(records, dict):records=[records]
            for record in records[:32]:
                parsed=urlsplit(record['endpoint'])
                address=str(ipaddress.ip_address(parsed.hostname))
                ip=ipaddress.ip_address(address)
                if not ip.is_private or ip.is_loopback or ip.is_unspecified:continue
                if parsed.scheme!='https' or parsed.path!='/eSCL' or parsed.username or parsed.query:continue
                device=connection_id(record['endpoint'],address)
                found[device]={'endpoint':record['endpoint'],'address':address,'name':str(record['name'])[:100]}
        except (OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired):pass
        _discovered=found;_discover_until=time.monotonic()+60
        return dict(found)


def certificate_challenge(device):
    record=discover().get(device)
    if record is None:raise ValueError('Scanner API non détecté par Windows.')
    port=urlsplit(record['endpoint']).port or 443
    # This callback rejects the handshake; no HTTP data is sent before approval.
    script=_CERTIFICATE.replace('param([string]$Address,[int]$Port)',
                                 "$Address='"+record['address']+"';$Port="+str(port))
    info=powershell(script)
    der=base64.b64decode(info['der'],validate=True)
    fingerprint=hashlib.sha256(der).hexdigest()
    hostname=info['hostname']
    if not isinstance(hostname,str) or not hostname or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-' for c in hostname):
        raise ValueError('Nom de certificat invalide.')
    endpoint='https://'+hostname+':'+str(port)+'/eSCL'
    token=uuid.uuid4().hex
    with _configuration_lock:
        expired=[key for key,value in _challenges.items() if value['expires']<time.monotonic()]
        for key in expired:del _challenges[key]
        if len(_challenges)>=32:raise ValueError('Trop de demandes de certificat en attente.')
        _challenges[token]=dict(record,endpoint=endpoint,der=der,sha256=fingerprint,expires=time.monotonic()+300)
    return dict(token=token,hostname=hostname,subject=info['subject'],sha256=fingerprint,
                valid_from=info['valid_from'],valid_until=info['valid_until'])


def approve_certificate(folder, token):
    with _configuration_lock:
        record=_challenges.pop(token,None)
        if not record or record['expires']<time.monotonic():raise ValueError('Approbation expirée ; recommencez.')
        folder=Path(folder);certificates=folder/'certificates';certificates.mkdir(parents=True,exist_ok=True)
        cert=certificates/(record['sha256']+'.der')
        staged=cert.with_suffix('.tmp');staged.write_bytes(record['der']);staged.replace(cert)
        # A trusted context still validates hostname and expiry at scan time.
        Scanner(record['endpoint'],record['address'],cert,record['sha256'])
        try:records=json.loads((folder/'escl-connections.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):records=[]
        if not isinstance(records,list):records=[]
        device=connection_id(record['endpoint'],record['address'])
        records=[r for r in records if isinstance(r,dict) and connection_id(r.get('endpoint',''),r.get('address',''))!=device]
        records.append({key:record[key] for key in ('name','endpoint','address','sha256')})
        staged=folder/'escl-connections.tmp';staged.write_text(json.dumps(records),encoding='utf-8');staged.replace(folder/'escl-connections.json')
        return {'approved':True,'device':device}


def acquire(action, folder, device, settings_folder):
    record = connections(settings_folder).get(device)
    if record is None:
        raise ValueError('Connexion API absente ou certificat non approuvé sur ce poste.')
    scanner = record['scanner']
    if action == 'probe':
        info = scanner.probe()
        return {'available': info['state'] == 'Idle' and info['pdf'],
                'message': 'API eSCL accessible · PDF A4 couleur 200 dpi sur vitre.'
                           if info['state'] == 'Idle' and info['pdf'] else 'Scanner occupé ou PDF non disponible.'}
    result = scanner.scan(folder)
    Path(result['output']).replace(Path(folder)/'page.pdf')
    return {'pdf': True}


