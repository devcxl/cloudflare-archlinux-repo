import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / '.github' / 'download-r2-action' / 'download_r2.py'


class FakeConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def load_module(module_name: str):
    fake_boto3 = types.SimpleNamespace(client=MagicMock())
    fake_botocore = types.ModuleType('botocore')
    fake_botocore_config = types.ModuleType('botocore.config')
    fake_botocore_config.Config = FakeConfig

    with patch.dict(
        sys.modules,
        {
            'boto3': fake_boto3,
            'botocore': fake_botocore,
            'botocore.config': fake_botocore_config,
        },
    ):
        spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return module, fake_boto3


class DownloadR2Tests(unittest.TestCase):
    def setUp(self):
        self.module, self.fake_boto3 = load_module('download_r2_under_test')
        self.client = MagicMock()
        self.paginator = MagicMock()
        self.client.get_paginator.return_value = self.paginator
        self.fake_boto3.client.return_value = self.client

        self.environ = {
            'AWS_S3_BUCKET': 'bucket',
            'AWS_ACCESS_KEY_ID': 'key',
            'AWS_SECRET_ACCESS_KEY': 'secret',
            'AWS_S3_ENDPOINT': 'https://example.invalid',
            'DESTINATION': 'repo',
            'SKIP_PACKAGE': 'localsend-bin',
        }

    def test_main_should_download_package_files_from_packages_prefix(self):
        self.paginator.paginate.return_value = [
            {
                'Contents': [
                    {'Key': 'packages/visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst'},
                    {'Key': 'packages/visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst.sig'},
                    {'Key': 'packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst'},
                ]
            }
        ]

        with patch.dict(os.environ, self.environ, clear=True), patch.object(self.module.os, 'makedirs'):
            self.module.main()

        self.paginator.paginate.assert_called_once_with(Bucket='bucket', Prefix='packages/')

        downloaded_keys = [call.args[1] for call in self.client.download_file.call_args_list]
        self.assertIn('packages/visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst', downloaded_keys)
        self.assertNotIn('packages/localsend-bin-1.0-1-x86_64.pkg.tar.zst', downloaded_keys)

        downloaded_destinations = [call.args[2] for call in self.client.download_file.call_args_list]
        self.assertIn('repo/visual-studio-code-bin-1.0-1-x86_64.pkg.tar.zst', downloaded_destinations)


if __name__ == '__main__':
    unittest.main()
