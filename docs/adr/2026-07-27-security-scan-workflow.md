# ADR: 采用 gh-aw (Pi Agent) + 传统 SAST 分层架构实现构建前安全扫描

- **日期**: 2026-07-27 (更新于 2026-08-29)
- **状态**: Proposed
- **决策者**: Felix（项目所有者）
- **影响范围**: CI/CD 流水线、AUR 包构建流程

---

## 背景

### 现状

`cloudflare-archlinux-repo` 是一个基于 Cloudflare Workers 的 Arch Linux 私有软件仓库。当前通过 GitHub Actions 定时检查 AUR 包更新，检测到更新后直接触发 `build.yml` 执行 `makepkg` 构建并上传至 R2 分发。

整个流程中**不存在任何安全检查**。PKGBUILD 及其构建脚本来自社区维护的 AUR，理论上任何人都可以提交包含恶意代码的 PKGBUILD。当前流程直接将第三方源码引入构建环境并执行，存在以下安全隐患：

1. **恶意 PKGBUILD**：`build()`/`package()` 中可嵌入 `curl | bash`、挖矿程序、后门等
2. **供应链攻击**：`.install` 脚本的 `post_install` hook 可执行任意命令
3. **密钥泄露**：PKGBUILD 或配置文件中可能意外包含 Token/密码
4. **已知漏洞**：构建产物的依赖可能存在 CVE

### 目标

在构建之前增加一个独立的、可配置的安全门禁 workflow，确保只有通过安全检查的包才会进入构建环节。

---

## 备选方案分析

### 方案 A：扩展 build.yml，在构建前添加扫描步骤

**做法**：不创建新 workflow，直接在现有 `build.yml` 的构建步骤前插入安全检查。

**优点**：
- 实现简单，只需在一个 YAML 中修改
- 无需处理 workflow 间串联和参数传递

**缺点**：
- 违反单一职责原则：`build.yml` 负责构建，加上安全扫描后职责混杂
- 无法独立测试/调试扫描环节
- 无法手动跳过扫描直接构建（紧急情况需要）
- 扫描步骤在同一个 job 内，无法并行，总耗时线性叠加
- 未来若需调整扫描策略，需修改构建流程本身，耦合度高

**结论**：不采用。职责不清晰，灵活性差。

---

### 方案 B：独立 workflow + 分层并行扫描 → 串联构建（采纳）

**做法**：创建独立的 `security-scan.yml`，包含三个并行扫描 job（Gitleaks+Semgrep、Pi Agent AI (gh-aw)、Trivy），全部通过后自动调用 `gh workflow run build.yml`。

**优点**：
- 职责分离：安全扫描与构建解耦
- 三层扫描并行执行，总耗时取决于最慢的一层
- 可独立手动触发安全扫描，无需构建
- 紧急情况下可跳过安全扫描直接触发 `build.yml`
- 各层可独立迭代（如更换扫描工具、调整规则），不影响构建流程
- 安全报告（AI 审查、SARIF）可独立归档和查看

**缺点**：
- 需要额外配置一个 workflow 文件
- 需要处理 workflow 间串联（`gh workflow run`）
- 三层 clone 同一份源码，略有资源浪费（可接受，总 clone 时间 < 30s）

**结论**：采纳。符合单一职责原则，扩展性好，且不影响现有构建流程。

---

### 方案 C：在 check-aur-updates.yml 中嵌入扫描逻辑

**做法**：在 `check-aur-updates.yml` 的定时任务中，检测到更新后不直接触发构建，而是在当前 workflow 中执行扫描。

**优点**：
- 减少一个 workflow 文件
- 扫描与检查更新在同一个上下文中

**缺点**：
- `check-aur-updates.yml` 检测多个包，若同时有多个包更新，扫描逻辑复杂
- 定时触发的扫描与手动触发需要不同的入口逻辑
- 无法独立对单个包执行安全扫描
- 违反单一职责：更新检查与安全检查混合

**结论**：不采用。与方案 B 相比，代码复杂度更高，灵活性更差。

---

## 决策

**采用方案 B**：独立的 `security-scan.yml` workflow，使用三层分层架构（快速门禁 → AI 深度审查 → 漏洞扫描），全部通过后串联触发 `build.yml`。

### 分层设计理由

| 层级 | 工具 | 定位 | 耗时预期 | 作用 |
|------|------|------|---------|------|
| Layer 1 | Gitleaks + Semgrep | 快速门禁 | < 2min | 拦截已知模式（密钥泄露、SQL 注入、命令注入等） |
| Layer 2 | GitHub Agentic Workflows + Pi Agent | AI 深度审查 | < 5min | 拦截传统工具无法检测的逻辑安全问题（供应链风险、隐蔽恶意代码） |
| Layer 3 | Trivy | 文件/依赖漏洞扫描 | < 3min | 拦截已知 CVE 和相关文件风险 |

**三层互补关系**：
- Layer 1 覆盖确定性规则（已知模式），Layer 2 覆盖推理判断（未知模式），Layer 3 覆盖依赖链（第三方风险）
- 任何一层都无法单独覆盖所有攻击面，三者合在一起形成纵深防御

### Pi Agent (gh-aw) 选型理由

在 AI 审查工具的选择上，GitHub Agentic Workflows (gh-aw) + Pi Agent 优于其他备选：

| 备选 | 排除/对比理由 |
|------|---------|
| GitHub Copilot Code Review | 面向代码审查而非安全审查，无定制 prompt 能力 |
| 自行调用 API + 简单脚本 | 缺乏智能体多步探索能力（如逐个读取复杂补丁与辅助文件） |
| OpenCode Action | 绑定特定商业服务生态，自定义 BaseURL 及 Provider 扩展性受限 |
| GitHub Agentic Workflows (gh-aw) + Pi Agent (采纳) | 具备强大的代码与脚本分析能力，支持自定义 baseURL、多 Provider（OpenAI/DeepSeek/Claude 等兼容接口）、沙箱权限控制与标准化 workflow frontmatter |

gh-aw 的声明式规范配合 Pi Agent 的执行能力，可灵活切换底层模型并支持任意私有/自定义 BaseURL。

### 串联方式

选择 `gh workflow run`（GitHub CLI）而非 `workflow_call`：

| 方式 | 适用场景 | 本项目选择 |
|------|---------|-----------|
| `workflow_call` | 同仓库内同步调用，返回结果立即可用 | ❌ 不采用：security-scan.yml 完成后可能 30s 后才触发 build，但 build.yml 本身是异步流程 |
| `gh workflow run` | 跨 workflow 异步触发，解耦程度高 | ✅ 采用：build.yml 本身就是 `workflow_dispatch`，天然支持异步触发；且保留手动独立触发能力 |

---

## 影响分析

### 正面影响

1. **安全水位大幅提升**：从零检查到三层纵深防御
2. **流程解耦**：扫描与构建独立，可分别迭代和维护
3. **可观测性**：SARIF 报告集成 GitHub Security 面板，AI 审查报告以 Artifact 存档
4. **回退路径清晰**：紧急情况可跳过扫描直接触发 `build.yml`
5. **模型接入自由度**：支持自定义 baseURL，可无缝对接各类兼容 OpenAI/DeepSeek 接口的模型服务

### 负面影响

1. **构建延迟增加**：总耗时增加约 5-8 分钟（三层并行中最慢的一层 + 串联触发延迟）
2. **维护成本**：需维护安全审查 prompt 以应对新型攻击模式

### 风险缓解

| 风险 | 缓解 |
|------|------|
| API 调用失败阻塞构建 | 紧急时可绕过 security-scan.yml 直接触发 build.yml |
| AI 误判 | WARN 级别不阻断；AI 不作为唯一判定依据 |
| 扫描超时 | 各 job 设置 timeout-minutes，超时即失败 |

---

## 实施路线

| 阶段 | 内容 | 预计时间 |
|------|------|---------|
| Phase 1 | Layer 1 (Gitleaks + Semgrep) + 串联触发逻辑 | 第 1 周 |
| Phase 2 | Layer 3 (Trivy) | 第 2 周 |
| Phase 3 | Layer 2 (Pi Agent / gh-aw) | 第 3 周 |
| Phase 4+ | 回写结果到 Issue、白名单机制、Dashboard | 后续迭代 |

---

## 相关参考

- [GitHub Agentic Workflows (gh-aw)](https://github.github.com/gh-aw/)
- [Arch Linux Wiki — PKGBUILD](https://wiki.archlinux.org/title/PKGBUILD)
- [Arch Linux Wiki — .install 文件](https://wiki.archlinux.org/title/PKGBUILD#install)
- [Gitleaks GitHub Action](https://github.com/gitleaks/gitleaks-action)
- [Semgrep GitHub Action](https://github.com/semgrep/semgrep-action)
- [Trivy GitHub Action](https://github.com/aquasecurity/trivy-action)
- [AUR 安全公告 — TU Bylaws § Security](https://wiki.archlinux.org/title/AUR_Trusted_User_guidelines)
- 项目技术方案：`docs/dev/specs/security-scan-workflow.md`
