---
id: T3
title: ".gitleaks.toml 规则配置"
phase: 1
status: pending
dependencies: ["T1"]
assigned_to: backend
pr: ""
branch: "feat/gitleaks-config"
---

# T3: .gitleaks.toml 规则配置

## 任务目标

创建 `.gitleaks.toml` 配置文件，为 AUR 包源码扫描提供针对性的密钥泄露检测规则。

在不创建自定义规则的情况下（默认规则通常已足够），评估是否需要：
- 放宽某些误报率高的规则（如 PKGBUILD 中常见变量名被误判为密钥）
- 添加 AUR 特有的模式（如 Arch Linux 特定的密钥格式）

## 验收标准

1. `.gitleaks.toml` 文件存在于仓库根目录
2. 文件使用 Gitleaks 标准 TOML 格式
3. 如果使用默认规则，文件内容为注释说明使用默认规则的原因
4. 如果有自定义规则，规则经过测试不会对常见 AUR PKGBUILD 变量产生误报
5. 文件路径在 `security-scan.yml` 中被正确引用（`GITLEAKS_CONFIG`）

## 实现步骤

1. 审查技术方案第 10 节假设 A4："`.gitleaks.toml` 暂不需要自定义规则，使用默认规则即可"
2. 初始版本使用 Gitleaks 默认规则，配置文件仅包含元信息注释：
   ```toml
   # Gitleaks configuration for cloudflare-archlinux-repo
   # 
   # 当前使用 Gitleaks 默认规则集，未添加自定义规则。
   # 默认规则覆盖了常见的密钥格式（AWS, GCP, GitHub Token, SSH Key 等）。
   #
   # 如需自定义规则（例如放宽对 PKGBUILD 变量名的误报），可在此文件中添加：
   # [[rules]]
   # description = "Custom rule for ..."
   # ...
   #
   # 参考: https://github.com/gitleaks/gitleaks/blob/master/config/gitleaks.toml
   ```
3. 后续根据 Phase 1 首次扫描结果，评估是否需要调整规则
4. 如需自定义规则，典型的 AUR 场景：
   - `allowlist` 排除 PKGBUILD 中的 `$pkgname`、`$pkgver` 等变量
   - 添加 Arch Linux 特有的密钥格式检测

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `.gitleaks.toml` | 新增 | Gitleaks 规则配置（初始为默认规则 + 注释） |

## 测试方法

1. 手动触发 Security Scan workflow，测试 `quick-gate` job
2. 验证 Gitleaks 步骤正确读取此配置文件（workflow log 中无 "config file not found" 错误）
3. 使用包含已知密钥的测试仓库验证检测功能正常
4. 使用常见 AUR 包（如 `yay`）验证无误报（假阳性）

## 参考

- Gitleaks 配置文档: https://github.com/gitleaks/gitleaks#configuration
- 默认规则集: https://github.com/gitleaks/gitleaks/blob/master/config/gitleaks.toml
- 技术方案假设 A4: `docs/dev/specs/security-scan-workflow.md` 第 10 节
