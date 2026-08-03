import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / '.github' / 'workflows' / 'security-scan.yml'
RETRY_SCRIPT_PATH = ROOT / '.github' / 'clone-source-with-retry.sh'
GITIGNORE_PATH = ROOT / '.gitignore'


class SecurityScanWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load(WORKFLOW_PATH.read_text())

    def _review_step(self):
        steps = self.workflow['jobs']['ai-review']['steps']
        return next(
            step for step in steps if step.get('name') == 'OpenCode AI security review'
        )

    def test_ai_review_uses_github_action_with_token(self):
        review_step = self._review_step()

        self.assertEqual(review_step['uses'], 'anomalyco/opencode/github@latest')
        self.assertIs(review_step['with']['use_github_token'], True)
        self.assertEqual(
            review_step['env']['GITHUB_TOKEN'], '${{ secrets.GITHUB_TOKEN }}'
        )
        self.assertNotIn('continue-on-error', review_step)

    def test_security_scan_does_not_grant_pr_creation_permissions(self):
        permissions = self.workflow['permissions']
        job_permissions = self.workflow['jobs']['ai-review'].get('permissions', {})

        self.assertNotIn('pull-requests', permissions)
        self.assertNotIn('id-token', permissions)
        self.assertNotIn('pull-requests', job_permissions)

    def test_quick_gate_audits_the_cloned_pkgbuild(self):
        steps = self.workflow['jobs']['quick-gate']['steps']
        audit_step = next(
            step for step in steps if step.get('name') == 'Security audit PKGBUILD'
        )

        self.assertEqual(audit_step['uses'], './.github/pkgbuild-audit-action')
        self.assertEqual(audit_step['with']['source-dir'], '${{ env.SOURCE_DIR }}')
        self.assertEqual(audit_step['with']['package-name'], '${{ inputs.package-name }}')

    def test_all_source_clones_use_retry_helper(self):
        for job_name in ('quick-gate', 'ai-review', 'dependency-scan'):
            steps = self.workflow['jobs'][job_name]['steps']
            clone_step = next(
                step for step in steps if step.get('name') == 'Clone AUR source'
            )
            self.assertIn('.github/clone-source-with-retry.sh', clone_step['run'])

    def test_cloned_source_does_not_dirty_the_workspace(self):
        ignored_paths = GITIGNORE_PATH.read_text().splitlines()

        self.assertIn('aur-source/', ignored_paths)

    def test_retry_helper_limits_each_clone_attempt(self):
        script = RETRY_SCRIPT_PATH.read_text()

        self.assertIn('timeout 60 git clone', script)

    def test_ai_review_job_can_create_issues(self):
        permissions = self.workflow['jobs']['ai-review'].get('permissions', {})

        self.assertEqual(permissions.get('issues'), 'write')

    def test_prompt_contains_readonly_constraints(self):
        prompt = self._review_step()['with']['prompt']
        self.assertIn('不修改仓库', prompt)
        self.assertIn('不创建分支', prompt)

    def test_prompt_requires_final_verdict(self):
        prompt = self._review_step()['with']['prompt']
        self.assertIn('FINAL_VERDICT', prompt)
        self.assertIn('FINAL_VERDICT: FAIL', prompt)

    def test_report_written_to_runner_temp(self):
        prompt = self._review_step()['with']['prompt']
        self.assertIn('runner.temp', prompt)
        self.assertIn('ai-review-report.md', prompt)

    def test_ai_review_allows_only_runner_temp_as_external_directory(self):
        config = json.loads(
            self._review_step()['env']['OPENCODE_CONFIG_CONTENT']
        )
        permissions = config['permission']['external_directory']

        self.assertEqual(
            list(permissions), ['*', '${{ runner.temp }}/*']
        )
        self.assertEqual(permissions['${{ runner.temp }}/*'], 'allow')
        self.assertEqual(permissions['*'], 'deny')

    def test_ai_review_creates_issue_and_blocks_on_fail(self):
        steps = self.workflow['jobs']['ai-review']['steps']
        report_step = next(
            step for step in steps if step.get('name') == 'Report AI review result'
        )
        run = report_step.get('run', '')

        self.assertIn('gh issue create', run)
        self.assertIn('--body-file', run)
        self.assertIn('exit 1', run)
        self.assertIn('gh issue list', run)
        self.assertIn('$RUNNER_TEMP/ai-review-report.md', run)

    def test_ai_review_blocks_when_report_is_missing_or_unknown(self):
        steps = self.workflow['jobs']['ai-review']['steps']
        report_step = next(
            step for step in steps if step.get('name') == 'Report AI review result'
        )
        run = report_step.get('run', '')

        self.assertIn('AI 审查报告缺失，阻断构建', run)
        self.assertIn('"$VERDICT" = "UNKNOWN"', run)


if __name__ == '__main__':
    unittest.main()
