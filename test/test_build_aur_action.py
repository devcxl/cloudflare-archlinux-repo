import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT_PATH = ROOT / '.github' / 'build-aur-action' / 'entrypoint.sh'


class BuildAurActionTests(unittest.TestCase):
    def test_source_clone_is_safe_bounded_and_retried(self):
        script = ENTRYPOINT_PATH.read_text()

        self.assertIn('PACKAGE_NAME" =~', script)
        self.assertIn('for ((attempt = 1; attempt <= 3; attempt++))', script)
        self.assertIn('timeout 60 git clone --depth 1', script)


if __name__ == '__main__':
    unittest.main()
