---
id: T5
title: "ai-review job — OpenCode AI 深度审查 + 源码摘要 + Artifact 上传"
phase: 3
status: pending
dependencies: ["T1"]
assigned_to: backend
pr: ""
branch: "feat/ai-review-job"
---

# T5: ai-review job — OpenCode AI 深度审查

## 任务目标

在 `security-scan.yml` 的 `ai-review` job 中实现 Layer 2 AI 深度审查逻辑：
- 生成 AUR 源码摘要（文件列表 + 核心文件行数）
- 使用 OpenCode AI（Claude Sonnet 4）对 PKGBUILD 及相关脚本进行 6 维度安全检查
- 将审查报告以 Artifact 形式上传保存

用实际审查步骤替换 T1 中的 stub。

## 验收标准

1. `ai-review` job 包含源码摘要生成步骤（输出到 `$GITHUB_STEP_SUMMARY`）
2. 源码摘要包含：文件列表 + 核心文件（PKGBUILD, *.install, *.patch, *.sh, *.service, *.conf, *.cfg）的行数
3. `ai-review` job 包含 OpenCode AI 审查步骤，使用 `anomalyco/opencode/github@latest`
4. AI 审查使用模型 `anthropic/claude-sonnet-4-20250514`
5. AI 审查 prompt 覆盖 6 个安全维度（源码完整性、构建脚本安全、依赖安全、敏感信息泄露、已知漏洞模式、供应链风险）
6. AI 审查使用 `agent: architect`
7. AI 审查步骤配置 `ANTHROPIC_API_KEY` 环境变量（来自 `secrets.ANTHROPIC_API_KEY`）
8. 审查报告 Artifact 上传步骤设置 `if: always()`
9. Artifact 命名包含包名：`ai-review-report-${{ inputs.package-name }}`
10. `ai-review` job 输出 `status: ${{ job.status }}`

## 实现步骤

1. 打开 `.github/workflows/security-scan.yml`
2. 定位 `ai-review` job，移除 stub echo 步骤
3. 确保保留 Checkout 步骤（`actions/checkout@v4`）
4. 确保保留 Clone AUR source 步骤
5. 添加源码摘要生成步骤（`id: source-summary`）：
   - 用 `find` 列出所有文件（限制 100 个）
   - 用 `find` 筛选核心文件类型，输出每个文件的行数
   - 输出到 `$GITHUB_STEP_SUMMARY`
6. 添加 OpenCode AI 审查步骤：
   - `uses: anomalyco/opencode/github@latest`
   - 配置 `model`、`prompt`、`agent` 参数
   - 设置 `ANTHROPIC_API_KEY` 环境变量
   - Prompt 内容参考技术方案第 3 节 `ai-review` job 中的完整 prompt
7. 添加 Artifact 上传步骤：
   ```yaml
   - name: Upload AI review report
     if: always()
     uses: actions/upload-artifact@v4
     with:
       name: ai-review-report-${{ inputs.package-name }}
       path: ${{ env.SOURCE_DIR }}-sec-report.md
   ```
8. 确认 job 的 `outputs` 包含 `status: ${{ job.status }}`

## 注意事项

- **假设 A1**（技术方案第 10 节）：`anomalyco/opencode/github@latest` 的 `prompt` 和 `agent` 参数需在实施前验证。如果 Action 接口不同，需调整参数名
- AI 审查失败不应阻塞构建（当前设计中，AI 审查失败会阻止 trigger-build；后续 Phase 3 测试后可考虑增加 "allow-failure" 选项）
- `ANTHROPIC_API_KEY` secret 需提前在 GitHub Repository Settings → Secrets 中配置

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `.github/workflows/security-scan.yml` | 修改 | 填充 ai-review job 审查步骤 |

## 测试方法

1. 确保 `ANTHROPIC_API_KEY` secret 已配置
2. 手动触发 Security Scan workflow，使用测试参数：
   - `package-name`: `yay`
   - `source-url`: `https://aur.archlinux.org/yay.git`
3. 验证源码摘要生成步骤正确输出文件列表
4. 验证 AI 审查步骤成功运行（不超时）
5. 下载 Artifact `ai-review-report-yay`，检查报告内容包含 6 个维度的判定
6. 验证报告格式符合 prompt 中指定的 Markdown 模板
7. 对已知安全的包，验证 AI 判定为 PASS，job 成功

## 参考

- 技术方案第 3 节 `ai-review` job 完整定义：`docs/dev/specs/security-scan-workflow.md`
- 技术方案第 4 节 Prompt 设计说明：`docs/dev/specs/security-scan-workflow.md`
- 技术方案第 5 节 Secrets 配置：`docs/dev/specs/security-scan-workflow.md`
- 技术方案第 10 节假设 A1：`docs/dev/specs/security-scan-workflow.md`
