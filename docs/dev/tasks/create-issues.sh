#!/bin/bash
# 创建 Security Scan Workflow 的 Parent Issue 和 Sub Issues
# 用法: bash docs/dev/tasks/create-issues.sh
#
# 前提条件:
#   - gh CLI 已安装并认证
#   - 当前在 cloudflare-archlinux-repo 仓库目录下

set -e

REPO="devcxl/cloudflare-archlinux-repo"
TASKS_DIR="docs/dev/tasks"
HEAD_BRANCH="master"
BRANCH="chore/plan-security-scan-tasks"

echo "=== 0. 创建缺失的 Labels ==="
for label in "security" "task" "backend" "phase-1" "phase-2" "phase-3"; do
  if gh label list --repo "$REPO" | grep -q "^$label\b"; then
    echo "  Label '$label' 已存在，跳过"
  else
    gh label create "$label" --repo "$REPO" --color "0052cc" 2>/dev/null || echo "  Label '$label' 创建"
  fi
done

echo ""
echo "=== 1. 创建 Parent Issue ==="
PARENT_BODY=$(cat <<'PARENT_EOF'
## 背景

为 `cloudflare-archlinux-repo` 项目添加独立的构建前安全扫描 workflow，在 AUR 包构建之前对其进行多层安全检查，全部通过后才自动触发 `build.yml` 执行实际的包构建和发布。

## 分阶段实施

| 阶段 | 内容 | 预计时间 |
|------|------|---------|
| Phase 1 | Layer 1: Gitleaks + Semgrep 快速门禁 + trigger-build 串联逻辑 | 第 1 周 |
| Phase 2 | Layer 3: Trivy 文件系统漏洞扫描 + SARIF 上传 | 第 2 周 |
| Phase 3 | Layer 2: OpenCode AI 深度审查（PKGBUILD 安全） | 第 3 周 |

## 相关文档

- 技术方案: [docs/dev/specs/security-scan-workflow.md](docs/dev/specs/security-scan-workflow.md)
- ADR: [docs/adr/2026-07-27-security-scan-workflow.md](docs/adr/2026-07-27-security-scan-workflow.md)
- 任务定义: `docs/dev/tasks/`

## 架构概览

```
security-scan.yml (workflow_dispatch)
  ├── quick-gate     (Layer 1: Gitleaks + Semgrep) ──┐
  ├── ai-review      (Layer 2: OpenCode AI)        ──┤
  ├── dependency-scan (Layer 3: Trivy)              ──┤
  └── trigger-build  (needs all 3, 全部 PASS 后触发 build.yml)
```
PARENT_EOF
)

PARENT_ISSUE_URL=$(gh issue create \
  --repo "$REPO" \
  --title "添加构建前安全检查 Workflow" \
  --label "enhancement,security" \
  --body "$PARENT_BODY")
PARENT_NUM=$(echo "$PARENT_ISSUE_URL" | grep -oP '\d+$')
echo "Parent Issue: $PARENT_ISSUE_URL (编号: $PARENT_NUM)"

echo ""
echo "=== 2. 创建 Sub Issues ==="

# T1: security-scan-workflow-skeleton
T1_BODY=$(cat <<'EOF'
## 依赖
无（所有 task 的基础）

## 关联文档
[docs/dev/tasks/security-scan-workflow-skeleton.md](docs/dev/tasks/security-scan-workflow-skeleton.md)

## 任务摘要
创建 `.github/workflows/security-scan.yml` 骨架：
- `workflow_dispatch` 入口（`package-name`、`source-url` 参数）
- 权限配置
- 4 个 job 占位（quick-gate, ai-review, dependency-scan, trigger-build）
- `trigger-build` job 完整实现（needs + gh workflow run）

## Branch
`feat/security-scan-workflow-skeleton`

## Phase
Phase 1
EOF
)

T1_URL=$(gh issue create \
  --repo "$REPO" \
  --title "[Task] security-scan.yml 骨架 — workflow 入口 + job 占位 + trigger-build" \
  --label "task,backend,phase-1" \
  --body "$T1_BODY")
echo "T1: $T1_URL"

# T2: quick-gate-job
T2_BODY=$(cat <<'EOF'
## 依赖
- T1: security-scan.yml 骨架

## 关联文档
[docs/dev/tasks/quick-gate-job.md](docs/dev/tasks/quick-gate-job.md)

## 任务摘要
在 `quick-gate` job 中实现 Layer 1 快速门禁：
- Gitleaks 密钥泄露扫描（gitleaks/gitleaks-action@v2）
- Semgrep SAST 静态分析（semgrep/semgrep-action@v1）
- `continue-on-error: false` 确保失败即终止

## Branch
`feat/quick-gate-job`

## Phase
Phase 1
EOF
)

T2_URL=$(gh issue create \
  --repo "$REPO" \
  --title "[Task] quick-gate job — Gitleaks + Semgrep 快速门禁扫描" \
  --label "task,backend,phase-1" \
  --body "$T2_BODY")
echo "T2: $T2_URL"

# T3: gitleaks-config
T3_BODY=$(cat <<'EOF'
## 依赖
- T1: security-scan.yml 骨架

## 关联文档
[docs/dev/tasks/gitleaks-config.md](docs/dev/tasks/gitleaks-config.md)

## 任务摘要
创建 `.gitleaks.toml` 配置文件：
- 初始使用默认规则 + 注释说明
- 后续根据扫描结果评估是否需要自定义规则
- 排除 PKGBUILD 变量的误报

## Branch
`feat/gitleaks-config`

## Phase
Phase 1
EOF
)

T3_URL=$(gh issue create \
  --repo "$REPO" \
  --title "[Task] .gitleaks.toml 规则配置" \
  --label "task,backend,phase-1" \
  --body "$T3_BODY")
echo "T3: $T3_URL"

# T4: dependency-scan-job
T4_BODY=$(cat <<'EOF'
## 依赖
- T1: security-scan.yml 骨架

## 关联文档
[docs/dev/tasks/dependency-scan-job.md](docs/dev/tasks/dependency-scan-job.md)

## 任务摘要
在 `dependency-scan` job 中实现 Layer 3 漏洞扫描：
- Trivy 文件系统漏洞扫描（aquasecurity/trivy-action@master）
- SARIF 结果上传到 GitHub Security 面板
- `severity: CRITICAL,HIGH`，`exit-code: "1"`

## Branch
`feat/dependency-scan-job`

## Phase
Phase 2
EOF
)

T4_URL=$(gh issue create \
  --repo "$REPO" \
  --title "[Task] dependency-scan job — Trivy 文件系统漏洞扫描 + SARIF 上传" \
  --label "task,backend,phase-2" \
  --body "$T4_BODY")
echo "T4: $T4_URL"

# T5: ai-review-job
T5_BODY=$(cat <<'EOF'
## 依赖
- T1: security-scan.yml 骨架

## 关联文档
[docs/dev/tasks/ai-review-job.md](docs/dev/tasks/ai-review-job.md)

## 任务摘要
在 `ai-review` job 中实现 Layer 2 AI 深度审查：
- 源码摘要生成（文件列表 + 核心文件行数）
- OpenCode AI 6 维度安全检查（Claude Sonnet 4）
- 审查报告 Artifact 上传
- 需配置 `ANTHROPIC_API_KEY` secret

## Branch
`feat/ai-review-job`

## Phase
Phase 3
EOF
)

T5_URL=$(gh issue create \
  --repo "$REPO" \
  --title "[Task] ai-review job — OpenCode AI 深度审查 + 源码摘要 + Artifact 上传" \
  --label "task,backend,phase-3" \
  --body "$T5_BODY")
echo "T5: $T5_URL"

# T6: ai-review-e2e
T6_BODY=$(cat <<'EOF'
## 依赖
- T5: ai-review job 实现

## 关联文档
[docs/dev/tasks/ai-review-e2e.md](docs/dev/tasks/ai-review-e2e.md)

## 任务摘要
使用已知恶意 PKGBUILD 样本进行端到端测试：
- 准备 ≥3 个测试样本（安全 + 恶意）
- 运行 ai-review job 验证检出率
- 基于结果优化 prompt
- 产出测试报告

## Branch
`feat/ai-review-e2e`

## Phase
Phase 3
EOF
)

T6_URL=$(gh issue create \
  --repo "$REPO" \
  --title "[Task] OpenCode prompt 优化与 E2E 验证 — 已知恶意 PKGBUILD 样本测试" \
  --label "task,backend,phase-3" \
  --body "$T6_BODY")
echo "T6: $T6_URL"

echo ""
echo "=== 3. 创建 Sub Issue 关联 ==="
# GitHub 不原生支持 parent/sub issue，使用 task list 在 parent issue body 中关联
gh issue edit "$PARENT_NUM" \
  --repo "$REPO" \
  --body "$(cat <<BODY
## 背景

为 cloudflare-archlinux-repo 项目添加独立的构建前安全扫描 workflow。

## 分阶段实施

| 阶段 | 内容 | 预计时间 |
|------|------|---------|
| Phase 1 | Layer 1: Gitleaks + Semgrep 快速门禁 + trigger-build 串联逻辑 | 第 1 周 |
| Phase 2 | Layer 3: Trivy 文件系统漏洞扫描 + SARIF 上传 | 第 2 周 |
| Phase 3 | Layer 2: OpenCode AI 深度审查（PKGBUILD 安全） | 第 3 周 |

## 相关文档

- 技术方案: [docs/dev/specs/security-scan-workflow.md](docs/dev/specs/security-scan-workflow.md)
- ADR: [docs/adr/2026-07-27-security-scan-workflow.md](docs/adr/2026-07-27-security-scan-workflow.md)
- 任务定义: [docs/dev/tasks/](docs/dev/tasks/)

## 任务列表

### Phase 1 — Layer 1 快速门禁
- [ ] T1: security-scan.yml 骨架 — workflow 入口 + job 占位 + trigger-build ($T1_URL)
- [ ] T2: quick-gate job — Gitleaks + Semgrep 快速门禁 ($T2_URL)
- [ ] T3: .gitleaks.toml 规则配置 ($T3_URL)

### Phase 2 — Layer 3 Trivy 扫描
- [ ] T4: dependency-scan job — Trivy + SARIF 上传 ($T4_URL)

### Phase 3 — Layer 2 AI 审查
- [ ] T5: ai-review job — OpenCode AI 深度审查 ($T5_URL)
- [ ] T6: OpenCode prompt 优化与 E2E 验证 ($T6_URL)

## DAG 拓扑

```mermaid
graph TD
  T1["T1: 骨架<br/>(Phase 1)"] --> T2["T2: quick-gate<br/>(Phase 1)"]
  T1 --> T3["T3: gitleaks 配置<br/>(Phase 1)"]
  T1 --> T4["T4: dependency-scan<br/>(Phase 2)"]
  T1 --> T5["T5: ai-review<br/>(Phase 3)"]
  T5 --> T6["T6: E2E 验证<br/>(Phase 3)"]
```
BODY
)"

echo ""
echo "=== 完成 ==="
echo "Parent Issue: $PARENT_ISSUE_URL"
echo "运行以下命令查看所有 issue:"
echo "  gh issue list --repo $REPO --label task"
