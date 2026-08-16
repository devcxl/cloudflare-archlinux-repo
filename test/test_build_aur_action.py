import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT_PATH = ROOT / '.github' / 'build-aur-action' / 'entrypoint.sh'
BUILD_WORKFLOW_PATH = ROOT / '.github' / 'workflows' / 'build.yml'
PACKAGES_PATH = ROOT / '.github' / 'packages.yml'


class BuildAurActionTests(unittest.TestCase):
    def test_source_clone_is_safe_bounded_and_retried(self):
        script = ENTRYPOINT_PATH.read_text()

        self.assertIn('PACKAGE_NAME" =~', script)
        self.assertIn('for ((attempt = 1; attempt <= 3; attempt++))', script)
        self.assertIn('timeout 60 git clone --depth 1', script)

    def test_entrypoint_applies_patches_before_makepkg(self):
        script = ENTRYPOINT_PATH.read_text()

        self.assertIn('PATCHES="${3:-}"', script)
        self.assertIn('git apply', script)
        # 补丁应用必须发生在 makepkg 之前
        apply_idx = script.find('git apply')
        makepkg_idx = script.find('makepkg -sf')
        self.assertGreater(apply_idx, 0)
        self.assertGreater(makepkg_idx, apply_idx)

    def test_build_workflow_passes_patches_to_action(self):
        workflow = BUILD_WORKFLOW_PATH.read_text()

        self.assertIn('Resolve package patches', workflow)
        self.assertIn('patches: ${{ steps.resolve-patches.outputs.patches }}', workflow)

    def test_declared_patch_files_exist(self):
        with open(PACKAGES_PATH) as f:
            data = yaml.safe_load(f)
        for pkg in data.get('packages', []):
            for patch_path in pkg.get('patches') or []:
                self.assertTrue(
                    (ROOT / patch_path).is_file(),
                    f'补丁文件不存在: {patch_path}',
                )


if __name__ == '__main__':
    unittest.main()
