"""Deployment proxy limits stay aligned with the CSV import endpoint."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parent.parent
SPEC=importlib.util.spec_from_file_location('gotc_deploy_install',ROOT/'deploy'/'install.py')
install=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install)


class DeployConfigTests(unittest.TestCase):
    def test_import_preview_has_a_dedicated_two_mib_proxy_limit(self):
        config=install.LOCATIONS
        exact=re.search(r'location = /gotc/api/admin/data/import/preview \{(?P<body>.*?)\n    \}',config,re.S)
        self.assertIsNotNone(exact)
        self.assertIn('proxy_pass http://127.0.0.1:5274;',exact.group('body'))
        self.assertIn('client_max_body_size 2m;',exact.group('body'))
        general=re.search(r'location \^~ /gotc/ \{(?P<body>.*?)\n    \}',config,re.S)
        self.assertIsNotNone(general)
        self.assertIn('client_max_body_size 32k;',general.group('body'))
        self.assertLess(config.index('location = /gotc/api/admin/data/import/preview'),
                        config.index('location ^~ /gotc/'))

    def test_existing_managed_block_is_upgraded_and_idempotent(self):
        original=('server {\n'
                  '    listen 443 ssl;\n'
                  '    server_name 8.141.114.201;\n'
                  '    location /other { proxy_pass http://127.0.0.1:9000; }\n'
                  +install.BEGIN+
                  '    location = /gotc { return 308 /gotc/; }\n'
                  '    location ^~ /gotc/ { client_max_body_size 32k; }\n'+
                  install.END+'}\n')
        upgraded=install.nginx_candidate(original)
        self.assertIn('location /other',upgraded)
        self.assertEqual(upgraded.count('location = /gotc/api/admin/data/import/preview'),1)
        self.assertIn('client_max_body_size 2m;',upgraded)
        self.assertIn('client_max_body_size 32k;',upgraded)
        self.assertEqual(install.nginx_candidate(upgraded),upgraded)


if __name__=='__main__':
    unittest.main()
