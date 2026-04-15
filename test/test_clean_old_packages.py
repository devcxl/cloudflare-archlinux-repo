import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / '.github' / 'clean-old-packages-action' / 'clean_old_packages.py'


def load_module(module_name: str):
    fake_boto3 = types.SimpleNamespace(client=MagicMock())

    with patch.dict(sys.modules, {'boto3': fake_boto3}):
        spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return module, fake_boto3


class CleanOldPackagesTests(unittest.TestCase):
    def setUp(self):
        self.module, self.fake_boto3 = load_module('clean_old_packages_under_test')
        self.client = MagicMock()
        self.paginator = MagicMock()
        self.client.get_paginator.return_value = self.paginator
        self.client.delete_objects.return_value = {'Deleted': [], 'Errors': []}
        self.fake_boto3.client.return_value = self.client

        self.environ = {
            'AWS_S3_BUCKET': 'bucket',
            'AWS_ACCESS_KEY_ID': 'key',
            'AWS_SECRET_ACCESS_KEY': 'secret',
            'AWS_S3_ENDPOINT': 'https://example.invalid',
        }

    def test_get_latest_versions_should_scan_bucket_root(self):
        self.paginator.paginate.return_value = [
            {
                'Contents': [
                    {'Key': 'visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst'},
                    {'Key': 'visual-studio-code-bin-1.1-1-x86_64.pkg.tar.zst'},
                ]
            }
        ]

        latest_versions, all_packages = self.module.get_latest_versions(self.client, 'bucket')

        self.paginator.paginate.assert_called_once_with(Bucket='bucket', Prefix='')
        self.assertEqual(latest_versions[('visual-studio-code-bin', 'x86_64')]['version'], '1.1-1')
        self.assertEqual(len(all_packages), 2)

    def test_delete_old_versions_should_only_delete_old_package_and_signature(self):
        latest_versions = {
            ('visual-studio-code-bin', 'x86_64'): {
                'name': 'visual-studio-code-bin',
                'version': '1.1-1',
                'arch': 'x86_64',
                'key': 'visual-studio-code-bin-1.1-1-x86_64.pkg.tar.zst',
            }
        }
        all_packages = [
            {
                'name': 'visual-studio-code-bin',
                'version': '1.0-1',
                'arch': 'x86_64',
                'key': 'visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst',
            },
            {
                'name': 'visual-studio-code-bin',
                'version': '1.1-1',
                'arch': 'x86_64',
                'key': 'visual-studio-code-bin-1.1-1-x86_64.pkg.tar.zst',
            },
        ]

        deleted_keys = self.module.delete_old_versions(
            self.client,
            'bucket',
            latest_versions,
            all_packages,
            dry_run=False,
            max_deletions=10,
        )

        self.assertEqual(
            deleted_keys,
            [
                'visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst',
                'visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst.sig',
            ],
        )
        self.client.delete_objects.assert_called_once()

    def test_main_should_not_touch_database_files(self):
        latest_versions = {
            ('visual-studio-code-bin', 'x86_64'): {
                'name': 'visual-studio-code-bin',
                'version': '1.1-1',
                'arch': 'x86_64',
                'key': 'visual-studio-code-bin-1.1-1-x86_64.pkg.tar.zst',
            }
        }
        all_packages = [
            {
                'name': 'visual-studio-code-bin',
                'version': '1.0-1',
                'arch': 'x86_64',
                'key': 'visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst',
            },
            {
                'name': 'visual-studio-code-bin',
                'version': '1.1-1',
                'arch': 'x86_64',
                'key': 'visual-studio-code-bin-1.1-1-x86_64.pkg.tar.zst',
            },
        ]

        with (
            patch.dict(os.environ, self.environ, clear=True),
            patch.object(self.module, 'get_latest_versions', return_value=(latest_versions, all_packages)),
            patch.object(self.module, 'delete_old_versions', return_value=['visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst']),
        ):
            self.module.main()

        self.client.download_file.assert_not_called()
        self.client.upload_file.assert_not_called()


if __name__ == '__main__':
    unittest.main()
