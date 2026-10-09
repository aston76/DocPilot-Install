import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
from escl_scan import PWG, SCAN, Scanner, job_path, settings_a4

ENDPOINT = 'https://scanner.example:9096/eSCL'
CAPS = f'''<scan:PlatenInputCaps xmlns:scan="{SCAN}" xmlns:pwg="{PWG}">
<scan:MaxWidth>2551</scan:MaxWidth><scan:MaxHeight>4205</scan:MaxHeight>
<scan:SettingProfiles><scan:SettingProfile>
<scan:ColorModes><scan:ColorMode>RGB24</scan:ColorMode></scan:ColorModes>
<scan:DocumentFormats><pwg:DocumentFormat>application/pdf</pwg:DocumentFormat></scan:DocumentFormats>
<scan:SupportedResolutions><scan:DiscreteResolutions><scan:DiscreteResolution>
<scan:XResolution>200</scan:XResolution><scan:YResolution>200</scan:YResolution>
</scan:DiscreteResolution></scan:DiscreteResolutions></scan:SupportedResolutions>
</scan:SettingProfile></scan:SettingProfiles></scan:PlatenInputCaps>'''


class Tests(unittest.TestCase):
    def test_job_stays_on_scanner(self):
        self.assertEqual(job_path(ENDPOINT+'/ScanJobs/id', ENDPOINT), '/eSCL/ScanJobs/id')
        for location in ('https://other.example:9096/eSCL/ScanJobs/id',
                         'http://scanner.example:9096/eSCL/ScanJobs/id',
                         '/eSCL/ScanJobs/../other', '/eSCL/ScanJobs/%2e%2e',
                         '/eSCL/ScanJobs/', '/eSCL/ScanJobs/id?x=1',
                         'https://user@scanner.example:9096/eSCL/ScanJobs/id'):
            with self.subTest(location=location), self.assertRaises(ValueError):
                job_path(location, ENDPOINT)

    def test_unsupported_profile_refused(self):
        self.assertTrue(Scanner.supports_a4_pdf(ET.fromstring(CAPS)))
        for before, after in [('application/pdf', 'image/jpeg'), ('RGB24', 'Grayscale8'),
                              ('>200<', '>300<'), ('>2551<', '>1000<')]:
            with self.subTest(before=before):
                self.assertFalse(Scanner.supports_a4_pdf(ET.fromstring(CAPS.replace(before, after))))

    def test_wrong_certificate_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as folder:
            cert = Path(folder)/'certificate.der'
            cert.write_bytes(b'not the approved certificate')
            with patch('socket.create_connection') as network, self.assertRaises(ValueError):
                Scanner(ENDPOINT, '192.0.2.10', cert, '0'*64)
            network.assert_not_called()

    def test_explicit_flatbed_pdf_settings(self):
        root = ET.fromstring(settings_a4())
        self.assertEqual(root.findtext(f'{{{PWG}}}InputSource'), 'Platen')
        self.assertEqual(root.findtext(f'{{{PWG}}}DocumentFormat'), 'application/pdf')
        self.assertEqual(root.findtext(f'.//{{{PWG}}}Width'), '2480')
        self.assertEqual(root.findtext(f'.//{{{PWG}}}Height'), '3508')

    def test_busy_does_not_launch_job(self):
        scanner = Scanner.__new__(Scanner)
        scanner.path = '/eSCL'
        caps = ET.fromstring(f'<scan:ScannerCapabilities xmlns:scan="{SCAN}"><scan:Platen>{CAPS}</scan:Platen></scan:ScannerCapabilities>')
        busy = ET.fromstring(f'<Status xmlns:pwg="{PWG}"><pwg:State>Processing</pwg:State></Status>')
        with tempfile.TemporaryDirectory() as folder, patch.object(scanner, 'read_xml', side_effect=[caps, busy]), patch.object(scanner, 'request') as network:
            with self.assertRaises(RuntimeError):
                scanner.scan(folder)
            network.assert_not_called()

    def test_invalid_pdf_not_published(self):
        scanner = Scanner.__new__(Scanner)
        scanner.path, scanner.endpoint = '/eSCL', ENDPOINT
        caps = ET.fromstring(f'<scan:ScannerCapabilities xmlns:scan="{SCAN}"><scan:Platen>{CAPS}</scan:Platen></scan:ScannerCapabilities>')
        idle = ET.fromstring(f'<Status xmlns:pwg="{PWG}"><pwg:State>Idle</pwg:State></Status>')
        responses = [(201, {'location': '/eSCL/ScanJobs/test'}, b''),
                     (200, {'content-type': 'application/pdf'}, b'%PDF-incomplete')]
        with tempfile.TemporaryDirectory() as folder, patch.object(scanner, 'read_xml', side_effect=[caps, idle]), patch.object(scanner, 'request', side_effect=responses):
            with self.assertRaises(RuntimeError):
                scanner.scan(folder)
            self.assertEqual(list(Path(folder).glob('*.pdf')), [])


if __name__ == '__main__':
    unittest.main()
