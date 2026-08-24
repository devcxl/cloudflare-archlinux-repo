import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))

from lib.version import (  # noqa: E402
    compare_versions,
    parse_arch_version,
    parse_package_filename,
)

HAS_VERCMP = shutil.which('vercmp') is not None


def vercmp_sign(a, b):
    # 注意：test_audit_pkgbuild 会泄漏性地 mock 掉 subprocess.run，
    # 因此这里用 Popen 直接调用真实的 vercmp 二进制。
    proc = subprocess.Popen(
        ['vercmp', a, b],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, _ = proc.communicate()
    return int(out.decode().strip())


class LibVersionTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(compare_versions('1.0-1', '1.0-1'), 0)
        self.assertEqual(compare_versions('1.0-2', '1.0-1'), 1)
        self.assertEqual(compare_versions('1.0-1', '1.0-2'), -1)
        self.assertEqual(compare_versions('2.0-1', '1.0-1'), 1)
        self.assertEqual(compare_versions('1:1.0-1', '1.0-1'), 1)

    def test_parse_arch_version(self):
        self.assertEqual(parse_arch_version('1.0-1'), (0, '1.0', 1))
        self.assertEqual(parse_arch_version('1:1.0-1'), (1, '1.0', 1))
        self.assertEqual(parse_arch_version('1.0'), (0, '1.0', 0))

    def test_separator_equivalence(self):
        # 报告关键用例：分隔符（. _ +）应被忽略，与 pacman vercmp 对齐
        self.assertEqual(compare_versions('1.0.1', '1.0_1'), 0)
        self.assertEqual(compare_versions('1.0_1', '1.0.1'), 0)
        self.assertEqual(compare_versions('1.0+1', '1.0.1'), 0)

    def test_parse_package_filename(self):
        self.assertEqual(
            parse_package_filename('localsend-bin-1.0-1-x86_64.pkg.tar.zst'),
            ('localsend-bin', '1.0-1', 'x86_64'),
        )
        self.assertIsNone(parse_package_filename('not-a-package.txt'))
        self.assertIsNone(parse_package_filename('foo-1.0-x64.pkg.tar.zst'))
        self.assertIsNone(parse_package_filename('foo-1.0-x86_64.pkg.tar.zst.sig'))

    @unittest.skipUnless(HAS_VERCMP, 'system vercmp not available')
    def test_matches_system_vercmp(self):
        pairs = [
            ('1.0', '1.0'), ('1.0', '2.0'),
            ('1.0', '1.0.1'), ('1.0.1', '1.0'),
            ('1.0', '1.0_1'), ('1.0.1', '1.0_1'),
            ('1.0a', '1.0'), ('1.0', '1.0a'),
            ('1.0a', '1.0b'), ('1.0A', '1.0a'),
            ('1.0.1', '1.0a'), ('1.0a', '1.0.1'),
            ('1.0a1', '1.0'), ('1.0', '1.0a1'),
            ('1.0', '1.0.0'), ('1.0-1', '1.0-2'),
            ('1:1.0', '1.0'), ('0.1', '0.0.1'),
            ('1.2.3', '1.2.3'), ('1.2.3-1', '1.2.3-2'),
            ('20240101', '20240102'), ('1.0.r1.g1234abc', '1.0.r1.g1234abd'),
            ('2.0.0', '2.0.0rc1'), ('2.0.0rc1', '2.0.0'),
            ('1.0beta', '1.0'), ('1.0', '1.0beta'),
            ('1.0a', '1.0.0'), ('a', '1'), ('1', 'a'),
            ('1a', '1'), ('1', '1a'),
        ]
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                expected = vercmp_sign(a, b)
                got = compare_versions(a, b)
                self.assertEqual(
                    got, expected,
                    f'compare_versions({a!r}, {b!r}) = {got} but vercmp = {expected}',
                )


if __name__ == '__main__':
    unittest.main()
