import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / '.github' / 'upload-r2-action' / 'upload_r2.py'


def load_module(module_name: str):
    fake_boto3 = types.SimpleNamespace(client=MagicMock())

    with patch.dict(sys.modules, {'boto3': fake_boto3}):
        spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return module, fake_boto3


class UploadR2Tests(unittest.TestCase):
    def setUp(self):
        self.module, self.fake_boto3 = load_module('upload_r2_under_test')
        self.client = MagicMock()
        self.fake_boto3.client.return_value = self.client

    def test_iter_upload_files_should_follow_symlink_and_keep_key_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / 'devcxl.db.tar.gz'
            target_path.write_text('db')
            link_path = Path(temp_dir) / 'devcxl.db'
            link_path.symlink_to(target_path.name)

            files = list(self.module.iter_upload_files(temp_dir))

        self.assertIn((str(target_path), 'devcxl.db.tar.gz'), files)
        self.assertIn((str(target_path), 'devcxl.db'), files)

    def test_main_should_upload_to_bucket_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / 'devcxl.gpg'
            file_path.write_text('gpg')

            with patch.dict(
                os.environ,
                {
                    'AWS_S3_BUCKET': 'bucket',
                    'AWS_ACCESS_KEY_ID': 'key',
                    'AWS_SECRET_ACCESS_KEY': 'secret',
                    'AWS_S3_ENDPOINT': 'https://example.invalid',
                    'SOURCE_DIR': temp_dir,
                },
                clear=True,
            ):
                self.module.main()

        self.client.upload_file.assert_called_once()
        args, kwargs = self.client.upload_file.call_args
        self.assertEqual(args[1], 'bucket')
        self.assertEqual(args[2], 'devcxl.gpg')
        self.assertEqual(kwargs['ExtraArgs']['ContentType'], 'application/octet-stream')


if __name__ == '__main__':
    unittest.main()
