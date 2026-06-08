import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / '.github' / 'check-aur-updates-action' / 'check_aur_updates.py'


def load_module(module_name: str):
    fake_requests = types.SimpleNamespace(get=MagicMock(), post=MagicMock(), RequestException=Exception)
    fake_boto3 = types.SimpleNamespace(client=MagicMock())

    with patch.dict(sys.modules, {'boto3': fake_boto3, 'requests': fake_requests}):
        spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return module, fake_requests, fake_boto3


class ParseGithubRepoTests(unittest.TestCase):
    def setUp(self):
        self.module, _, _ = load_module('check_aur_updates_under_test')

    def test_https_url_with_git_suffix(self):
        result = self.module.parse_github_repo('https://github.com/user/repo.git')
        self.assertEqual(result, 'user/repo')

    def test_https_url_without_git_suffix(self):
        result = self.module.parse_github_repo('https://github.com/user/repo')
        self.assertEqual(result, 'user/repo')

    def test_ssh_url(self):
        result = self.module.parse_github_repo('git@github.com:user/repo.git')
        self.assertEqual(result, 'user/repo')

    def test_non_github_url(self):
        result = self.module.parse_github_repo('https://gitlab.com/user/repo.git')
        self.assertIsNone(result)


class CompareVersionsTests(unittest.TestCase):
    def setUp(self):
        self.module, _, _ = load_module('check_aur_updates_under_test')
        self.cmp = self.module.compare_versions

    def test_same_version(self):
        self.assertEqual(self.cmp('1.0-1', '1.0-1'), 0)

    def test_newer_pkgrel(self):
        self.assertEqual(self.cmp('1.0-2', '1.0-1'), 1)

    def test_older_pkgrel(self):
        self.assertEqual(self.cmp('1.0-1', '1.0-2'), -1)

    def test_newer_pkgver(self):
        self.assertEqual(self.cmp('2.0-1', '1.0-1'), 1)

    def test_version_with_epoch(self):
        self.assertEqual(self.cmp('1:1.0-1', '1.0-1'), 1)


class TriggerBuildTests(unittest.TestCase):
    def setUp(self):
        self.module, self.fake_requests, _ = load_module('check_aur_updates_under_test')

    def test_trigger_passes_source_url(self):
        self.module.trigger_build('token', 'user/repo', 'test-pkg',
                                  source_url='https://aur.archlinux.org/test-pkg.git')
        self.fake_requests.post.assert_called_once()
        call_args = self.fake_requests.post.call_args
        self.assertEqual(call_args[1]['json']['inputs']['package-name'], 'test-pkg')
        self.assertEqual(call_args[1]['json']['inputs']['source-url'],
                         'https://aur.archlinux.org/test-pkg.git')

    def test_trigger_with_github_url(self):
        self.module.trigger_build(
            'token', 'user/repo', 'my-pkg',
            source_url='https://github.com/u/r.git'
        )
        self.fake_requests.post.assert_called_once()
        call_args = self.fake_requests.post.call_args
        self.assertEqual(call_args[1]['json']['inputs']['source-url'],
                         'https://github.com/u/r.git')


class GetGitVersionsTests(unittest.TestCase):
    def setUp(self):
        self.module, self.fake_requests, _ = load_module('check_aur_updates_under_test')

    def test_empty_list_returns_empty_dict(self):
        versions = self.module.get_git_versions([])
        self.assertEqual(versions, {})

    def test_fetches_release_tag_and_strips_v_prefix(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'tag_name': 'v2.0.0'}
        self.fake_requests.get.return_value = mock_response

        versions = self.module.get_git_versions(
            [{'name': 'my-pkg', 'url': 'https://github.com/user/repo.git'}],
            gh_token='token'
        )
        self.assertEqual(versions, {'my-pkg': '2.0.0'})

    def test_unparseable_url_skips_entry(self):
        versions = self.module.get_git_versions(
            [{'name': 'bad', 'url': 'not-a-valid-url'}]
        )
        self.assertEqual(versions, {})


class GetGithubLatestReleaseTests(unittest.TestCase):
    def setUp(self):
        self.module, self.fake_requests, _ = load_module('check_aur_updates_under_test')

    def test_returns_stripped_tag(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'tag_name': 'v1.2.3'}
        self.fake_requests.get.return_value = mock_response

        result = self.module.get_github_latest_release('user/repo', gh_token='token')
        self.assertEqual(result, '1.2.3')

    def test_404_falls_back_to_tags(self):
        mock_404 = MagicMock()
        mock_404.status_code = 404
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = [{'name': 'v3.0.0'}]
        self.fake_requests.get.side_effect = [mock_404, mock_ok]

        result = self.module.get_github_latest_release('user/repo', gh_token='token')
        self.assertEqual(result, '3.0.0')


class ParseAurPkgnameTests(unittest.TestCase):
    def setUp(self):
        self.module, _, _ = load_module('check_aur_updates_under_test')

    def test_aur_url_with_git_suffix(self):
        result = self.module.parse_aur_pkgname(
            'https://aur.archlinux.org/visual-studio-code-bin.git')
        self.assertEqual(result, 'visual-studio-code-bin')

    def test_aur_url_without_git_suffix(self):
        result = self.module.parse_aur_pkgname(
            'https://aur.archlinux.org/pkgname')
        self.assertEqual(result, 'pkgname')

    def test_non_aur_url(self):
        result = self.module.parse_aur_pkgname(
            'https://github.com/user/repo.git')
        self.assertIsNone(result)


class IsAurUrlTests(unittest.TestCase):
    def setUp(self):
        self.module, _, _ = load_module('check_aur_updates_under_test')

    def test_aur_url_returns_true(self):
        self.assertTrue(self.module.is_aur_url(
            'https://aur.archlinux.org/pkg.git'))

    def test_github_url_returns_false(self):
        self.assertFalse(self.module.is_aur_url(
            'https://github.com/user/repo.git'))


class CheckAurUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.module, _, _ = load_module('check_aur_updates_under_test')
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
