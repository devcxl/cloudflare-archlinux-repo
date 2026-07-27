---
id: T1
title: "security-scan.yml 骨架 — workflow 入口 + job 占位 + trigger-build"
phase: 1
status: pending
dependencies: []
assigned_to: backend
pr: ""
branch: "feat/security-scan-workflow-skeleton"
---

# T1: security-scan.yml 骨架

## 任务目标

创建 `.github/workflows/security-scan.yml` 的完整骨架，包括：
- `workflow_dispatch` 手动触发入口（`package-name`、`source-url` 输入参数）
- 权限配置（`contents: read`, `actions: write`, `security-events: write`）
- 4 个 job 占位：`quick-gate`、`ai-review`、`dependency-scan`、`trigger-build`
- `trigger-build` job 完整实现（`needs` 依赖 + `gh workflow run build.yml` 串联逻辑）
- 其余 3 个扫描 job 使用最小 stub（checkout + echo placeholder），后续 task 填充

## 验收标准

1. workflow 文件位于 `.github/workflows/security-scan.yml`
2. 可通过 GitHub Actions 页面手动触发，输入框显示 `package-name` 和 `source-url` 两个参数
3. `trigger-build` job 在 `quick-gate`、`ai-review`、`dependency-scan` 三个 job 全部成功后自动执行
4. `trigger-build` 使用 `gh workflow run build.yml` 命令，参数正确传递
5. 权限声明为最小必要权限（3 项）
6. `timeout-minutes` 设置：quick-gate 5min, ai-review 10min, dependency-scan 5min
7. 全局 `env.SOURCE_DIR` 设置为 `/tmp/aur-source`

## 实现步骤

1. 创建 `.github/workflows/security-scan.yml`
2. 定义 `name: Security Scan`
3. 配置 `on.workflow_dispatch.inputs`（`package-name` string required, `source-url` string required）
4. 配置 `permissions` 块
5. 定义 `env.SOURCE_DIR: /tmp/aur-source`
6. 创建 `quick-gate` job（stub: checkout + clone source + echo "TODO: add Gitleaks + Semgrep"）
7. 创建 `ai-review` job（stub: checkout + clone source + echo "TODO: add OpenCode AI review"）
8. 创建 `dependency-scan` job（stub: checkout + clone source + echo "TODO: add Trivy scan"）
9. 创建 `trigger-build` job（完整实现）：
   - `needs: [quick-gate, ai-review, dependency-scan]`
   - `if: success()`
   - `runs-on: ubuntu-latest`
   - 步骤：使用 `gh workflow run build.yml` 触发构建
   - 步骤：输出 Summary

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `.github/workflows/security-scan.yml` | 新增 | security scan workflow 骨架 |

## 测试方法

1. Push 分支后，在 GitHub Actions 页面找到 "Security Scan" workflow
2. 手动触发（`workflow_dispatch`），输入测试参数：
   - `package-name`: `test-pkg`
   - `source-url`: `https://github.com/example/test-pkg.git`
3. 验证 4 个 job 都出现在 workflow run 中
4. 验证 trigger-build job 等待前 3 个 job 完成（stub 会成功）
5. 验证 trigger-build 尝试触发 `build.yml`（预期：该 workflow 不存在或无 dispatch 事件，但命令本身正确）
6. 检查 workflow run 的 Summary 是否包含 ✅ Security Scan Passed 信息

## 参考

- 技术方案第 3 节完整 YAML：`docs/dev/specs/security-scan-workflow.md`
