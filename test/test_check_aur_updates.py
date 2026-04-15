import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / '.github' / 'check-aur-updates-action' / 'check_aur_updates.py'


def load_module(module_name: str):
    fake_boto3 = types.SimpleNamespace(client=MagicMock())
    fake_requests = types.SimpleNamespace(get=MagicMock(), post=MagicMock(), RequestException=Exception)

    with patch.dict(sys.modules, {'boto3': fake_boto3, 'requests': fake_requests}):
        spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return module


class CheckAurUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module('check_aur_updates_under_test')
        self.client = MagicMock()
        self.paginator = MagicMock()
        self.client.get_paginator.return_value = self.paginator

    def test_get_r2_versions_should_scan_packages_prefix(self):
        self.paginator.paginate.return_value = [
            {
                'Contents': [
                    {'Key': 'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst'},
                    {'Key': 'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst.sig'},
                    {'Key': 'packages/visual-studio-code-bin-1.2-1-x86_64.pkg.tar.zst'},
                ]
            }
        ]

        versions = self.module.get_r2_versions(self.client, 'bucket')

        self.paginator.paginate.assert_called_once_with(Bucket='bucket', Prefix='packages/')
        self.assertEqual(
            versions,
            {
                'localsend-bin': '1.0-1',
                'visual-studio-code-bin': '1.2-1',
            },
        )


if __name__ == '__main__':
    unittest.main()
