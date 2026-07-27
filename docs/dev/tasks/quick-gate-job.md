---
id: T2
title: "quick-gate job — Gitleaks + Semgrep 快速门禁扫描"
phase: 1
status: pending
dependencies: ["T1"]
assigned_to: backend
pr: ""
branch: "feat/quick-gate-job"
---

# T2: quick-gate job — Gitleaks + Semgrep 快速门禁

## 任务目标

在 `security-scan.yml` 的 `quick-gate` job 中实现 Layer 1 快速门禁扫描逻辑：
- Gitleaks 密钥泄露扫描
- Semgrep SAST 静态分析

用实际扫描步骤替换 T1 中的 stub。

## 验收标准

1. `quick-gate` job 包含 Gitleaks 扫描步骤，使用 `gitleaks/gitleaks-action@v2`
2. Gitleaks 步骤配置 `GITLEAKS_CONFIG` 环境变量指向仓库根目录的 `.gitleaks.toml`
3. `quick-gate` job 包含 Semgrep 扫描步骤，使用 `semgrep/semgrep-action@v1`
4. Semgrep 使用 `config: auto` 模式
5. 两个扫描步骤均设置 `continue-on-error: false`（失败即终止 job）
6. `quick-gate` job 输出 `status: ${{ job.status }}` 供 `trigger-build` 的 `needs` 检查
7. Clone AUR source 步骤使用 `git clone --depth 1` 到 `$SOURCE_DIR`

## 实现步骤

1. 打开 `.github/workflows/security-scan.yml`
2. 定位 `quick-gate` job，移除 stub echo 步骤
3. 确保保留 Checkout 步骤（`actions/checkout@v4`）
4. 确保保留 Clone AUR source 步骤
5. 添加 Gitleaks 扫描步骤：
   ```yaml
   - name: Gitleaks — secret scan
     uses: gitleaks/gitleaks-action@v2
     env:
       GITLEAKS_CONFIG: ${{ github.workspace }}/.gitleaks.toml
     with:
       source: ${{ env.SOURCE_DIR }}
     continue-on-error: false
   ```
6. 添加 Semgrep 扫描步骤：
   ```yaml
   - name: Semgrep — SAST scan
     uses: semgrep/semgrep-action@v1
     with:
       config: auto
       target: ${{ env.SOURCE_DIR }}
     continue-on-error: false
   ```
7. 确认 job 的 `outputs` 包含 `status: ${{ job.status }}`

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `.github/workflows/security-scan.yml` | 修改 | 填充 quick-gate job 扫描步骤 |

## 测试方法

1. 手动触发 Security Scan workflow，使用测试参数：
   - `package-name`: `yay`（知名 AUR helper，源码干净）
   - `source-url`: `https://aur.archlinux.org/yay.git`
2. 验证 `quick-gate` job 通过（Gitleaks 无发现，Semgrep 无高危）
3. 再使用含已知密钥的测试仓库测试（如包含 `AWS_ACCESS_KEY_ID=AKIA...` 的文件），验证 Gitleaks 正确检测并失败
4. 检查 workflow log 确认两个扫描步骤实际运行（输出扫描结果）

## 参考

- 技术方案第 3 节 `quick-gate` job 定义：`docs/dev/specs/security-scan-workflow.md`
- Gitleaks Action: https://github.com/gitleaks/gitleaks-action
- Semgrep Action: https://github.com/semgrep/semgrep-action
