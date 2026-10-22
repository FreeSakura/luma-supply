"""Standalone launcher checks: python -m unittest discover -s tests -p test_miniapp_start.py."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import start_miniapp as launcher


class MiniappStartTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.target = self.root / 'miniapps' / 'unified'
        self.target.mkdir(parents=True)
        self.config = self.target / 'config.js'
        self.config.write_text('module.exports = {"baseUrl":"https://old.example",'
                               '"demo":false,"version":"2.1.0","role":"auto","extra":42};\n')
        for filename in ('project.config.json', 'project.private.config.json'):
            (self.target / filename).write_text(json.dumps({
                'appid': 'keep-current-appid', 'setting': {'urlCheck': True, 'es6': True}}))
        self.root_patch = patch.object(launcher, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.stdout = redirect_stdout(StringIO())
        self.stderr = redirect_stderr(StringIO())
        self.stdout.__enter__()
        self.stderr.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.addCleanup(self.stderr.__exit__, None, None, None)

    def test_switch_network_preserves_appid_and_unrelated_settings(self):
        for address in ('10.249.116.139', '172.20.10.2'):
            result = launcher.main(['--ip', address, '--configure-only'])
            self.assertEqual(result, 0)
            config = json.loads(self.config.read_text().split('=', 1)[1])
            self.assertEqual(config['baseUrl'], f'http://{address}:8000')
            self.assertEqual(config['extra'], 42)
            self.assertTrue(config['demo'])
            for filename in ('project.config.json', 'project.private.config.json'):
                project = json.loads((self.target / filename).read_text())
                self.assertEqual(project['appid'], 'keep-current-appid')
                self.assertEqual(project['setting'], {'urlCheck': False, 'es6': True})

    def test_invalid_address_and_port_do_not_change_config(self):
        original = self.config.read_bytes()
        for args in (['--ip', '127.0.0.1'], ['--ip', '8.8.8.8'], ['--ip', '::1'],
                     ['--ip', 'invalid'], ['--port', '65536'], ['--port', '0']):
            self.assertEqual(launcher.main(args + ['--configure-only']), 1)
            self.assertEqual(self.config.read_bytes(), original)

    @patch.object(launcher.sys, 'platform', 'darwin')
    @patch.object(launcher.subprocess, 'check_output')
    def test_auto_detection_skips_vpn_and_inactive_interfaces(self, command):
        command.return_value = ('lo0: flags=UP\n\tinet 127.0.0.1\n'
                                'en1: flags=UP\n\tinet 192.168.1.2\n\tstatus: inactive\n'
                                'utun0: flags=UP\n\tinet 10.9.0.2\n\tstatus: active\n'
                                'en0: flags=UP\n\tinet 172.20.10.2 netmask 0xffffff00\n\tstatus: active\n')
        self.assertEqual(launcher.detect_ip(), '172.20.10.2')

    @patch.object(launcher.sys, 'platform', 'darwin')
    @patch.object(launcher.subprocess, 'check_output')
    def test_ambiguous_or_missing_network_requires_explicit_address(self, command):
        for output in ('lo0: flags=UP\n\tinet 127.0.0.1\n',
                       'en0: flags=UP\n\tinet 10.0.0.2\n\tstatus: active\n'
                       'en1: flags=UP\n\tinet 192.168.1.2\n\tstatus: active\n'):
            command.return_value = output
            with self.assertRaisesRegex(ValueError, '--ip'):
                launcher.detect_ip()

    @patch.object(launcher, 'check_backend', side_effect=ValueError('occupied'))
    @patch.object(launcher, 'port_in_use', return_value=True)
    def test_conflicting_service_does_not_rewrite_or_restart(self, port, health):
        original = self.config.read_bytes()
        with patch.object(launcher.os, 'execve') as execute:
            self.assertEqual(launcher.main(['--ip', '192.168.1.2']), 1)
            execute.assert_not_called()
        self.assertEqual(self.config.read_bytes(), original)

    @patch.object(launcher, 'check_backend')
    @patch.object(launcher, 'port_in_use', return_value=True)
    def test_healthy_existing_backend_reused_on_custom_port(self, port, health):
        with patch.object(launcher.os, 'execve') as execute:
            self.assertEqual(launcher.main(['--ip', '192.168.1.2', '--port', '8011']), 0)
            execute.assert_not_called()
        health.assert_called_once_with('http://192.168.1.2:8011')
        self.assertIn('http://192.168.1.2:8011', self.config.read_text())

    @patch.object(launcher, 'build_opener')
    def test_unrelated_or_production_health_response_is_rejected(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 200
        for data in ({'status': 'ok'}, [], {'status': 'ok', 'version': '2.1.0',
                                         'environment': 'production', 'integrations': {}}):
            response.read.return_value = json.dumps(data)
            with self.assertRaises(ValueError):
                launcher.check_backend('http://192.168.1.2:8000')

    def test_malformed_project_does_not_partially_change_config(self):
        original = self.config.read_bytes()
        (self.target / 'project.config.json').write_text('invalid JSON')
        self.assertEqual(launcher.main(['--ip', '192.168.1.2', '--configure-only']), 1)
        self.assertEqual(self.config.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
