import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / '.github' / 'workflows' / 'security-scan.yml'


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
        self.assertEqual(review_step.get('continue-on-error'), True)

    def test_security_scan_does_not_grant_pr_creation_permissions(self):
        permissions = self.workflow['permissions']
        job_permissions = self.workflow['jobs']['ai-review'].get('permissions', {})

        self.assertNotIn('pull-requests', permissions)
        self.assertNotIn('id-token', permissions)
        self.assertNotIn('pull-requests', job_permissions)

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


if __name__ == '__main__':
    unittest.main()
