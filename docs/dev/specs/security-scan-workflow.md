# 构建前安全检查 Workflow 技术方案

## 1. 需求概述

为 `cloudflare-archlinux-repo` 项目添加独立的构建前安全扫描 workflow，在 AUR 包构建之前对其进行多层安全检查，全部通过后才自动触发 `build.yml` 执行实际的包构建和发布。

### 1.1 核心需求

| 需求 | 说明 |
|------|------|
| 独立 workflow | 不修改现有 `build.yml`，新增 `.github/workflows/security-scan.yml` |
| 分层检查 | Layer 1（快速门禁） → Layer 2（AI 深度审查） → Layer 3（依赖/文件漏洞扫描） |
| 串联构建 | 三层全部通过后，自动调用 `gh workflow run build.yml` 触发构建 |
| 手动触发 | 通过 `workflow_dispatch` 触发，输入 `package-name` 和 `source-url` |

### 1.2 触发方式

- **手动触发**：`workflow_dispatch`，接收与 `build.yml` 一致的输入参数
- **上下游关系**：`check-aur-updates.yml`（上游，定时检查更新） → `security-scan.yml`（本 workflow） → `build.yml`（下游，实际构建）

---

## 2. 架构设计

### 2.1 总体架构

```
security-scan.yml (workflow_dispatch)
  inputs: package-name, source-url
  │
  ├── Job 1: quick-gate（快速门禁，预期 < 2min）
  │   ├── Checkout 本仓库
  │   ├── Clone AUR 源码
  │   ├── Gitleaks 密钥泄露扫描
  │   └── Semgrep SAST 静态分析
  │
  ├── Job 2: ai-review（Pi AI 深度审查，预期 < 5min）── 与 Job 1 并行
  │   ├── Checkout 本仓库
  │   ├── Clone AUR 源码
  │   └── Pi Agent (gh-aw) 审查 PKGBUILD + 安装脚本安全
  │
  ├── Job 3: dependency-scan（Trivy 文件扫描，预期 < 3min）── 与 Job 1 并行
  │   ├── Checkout 本仓库
  │   ├── Clone AUR 源码
  │   └── Trivy filesystem 扫描 → SARIF 上传
  │
  └── Job 4: trigger-build（三层全部 PASS）── 依赖 Job 1,2,3
      └── gh workflow run build.yml -f package-name=... -f source-url=...
```

### 2.2 Job 间依赖关系

```
                    ┌─────────────┐
                    │ workflow_dispatch
                    │ (package-name,
                    │  source-url)
                    └──────┬──────┘
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌────────────┐  ┌────────────┐  ┌────────────────┐
   │ quick-gate │  │ ai-review  │  │dependency-scan │
   │  (Layer 1) │  │  (Layer 2) │  │   (Layer 3)    │
   └─────┬──────┘  └─────┬──────┘  └───────┬────────┘
         │               │                 │
         └───────────────┼─────────────────┘
                         │  (全部成功)
                         ▼
                  ┌──────────────┐
                  │trigger-build │
                  │  (Layer 4)   │
                  └──────┬───────┘
                         │  gh workflow run build.yml
                         ▼
                  ┌──────────────┐
                  │  build.yml   │
                  │ (已有 workflow)
                  └──────────────┘
```

### 2.3 数据流

```
AUR Git Repo (source-url)
    │
    ├── Clone ──► quick-gate       ──► Gitleaks report + Semgrep SARIF
    │
    ├── Clone ──► ai-review        ──► Pi Agent 审查结果（日志/issue/artifact）
    │
    ├── Clone ──► dependency-scan  ──► Trivy SARIF (upload to GitHub)
    │
    └── (源码不持久化，各 job 独立 clone)
```

各 job 独立执行 `git clone`，无文件共享——避免 job 间污染，且 GitHub Actions 的 job 隔离天然保证了互不干扰。

---

## 3. 完整 Workflow YAML

```yaml
name: Security Scan

on:
  workflow_dispatch:
    inputs:
      package-name:
        description: "包名"
        required: true
        type: string
      source-url:
        description: "Git 仓库 URL (AUR 或其他)"
        required: true
        type: string

permissions:
  contents: read
  actions: write
  security-events: write

env:
  SOURCE_DIR: /tmp/aur-source

jobs:
  # ============================================================
  # Layer 1: 快速门禁 — Gitleaks + Semgrep
  # ============================================================
  quick-gate:
    name: "Layer 1 — Quick Gate (Gitleaks + Semgrep)"
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      status: ${{ job.status }}
    steps:
      - name: Checkout repo (for shared config if needed)
        uses: actions/checkout@v4

      - name: Clone AUR source
        run: |
          git clone --depth 1 "${{ inputs.source-url }}" "${{ env.SOURCE_DIR }}"

      - name: Gitleaks — secret scan
        uses: gitleaks/gitleaks-action@v2
        env:
          GITLEAKS_CONFIG: ${{ github.workspace }}/.gitleaks.toml
        with:
          source: ${{ env.SOURCE_DIR }}
        continue-on-error: false

      - name: Semgrep — SAST scan
        uses: semgrep/semgrep-action@v1
        with:
          config: auto
          target: ${{ env.SOURCE_DIR }}
        continue-on-error: false

  # ============================================================
  # Layer 2: Pi Agent (gh-aw) AI 深度审查
  # ============================================================
  ai-review:
    name: "Layer 2 — AI Deep Review (Pi / gh-aw)"
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: read
      issues: write
    outputs:
      status: ${{ job.status }}
    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Clone AUR source
        run: |
          git clone --depth 1 "${{ inputs.source-url }}" "${{ env.SOURCE_DIR }}"

      - name: Prepare source summary for AI
        id: source-summary
        run: |
          echo "### 源码文件列表" >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
          find "${{ env.SOURCE_DIR }}" -type f | head -100 >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY

          FILES=$(find "${{ env.SOURCE_DIR }}" -type f \
            \( -name 'PKGBUILD' -o -name '.SRCINFO' \
               -o -name '*.install' -o -name '*.patch' -o -name '*.diff' \
               -o -name '*.sh' -o -name '*.bash' -o -name '*.zsh' \
               -o -name '*.service' -o -name '*.timer' -o -name '*.socket' \
               -o -name '*.desktop' -o -name '*.conf' -o -name '*.cfg' \
               -o -name '*.mjs' -o -name '*.js' -o -name '*.ts' -o -name '*.py' \) \
            | head -30)
          for f in $FILES; do
            echo "---" >> $GITHUB_STEP_SUMMARY
            echo "**$f**" >> $GITHUB_STEP_SUMMARY
            echo '```' >> $GITHUB_STEP_SUMMARY
            wc -l "$f" | awk '{print $1 " lines"}' >> $GITHUB_STEP_SUMMARY
            echo '```' >> $GITHUB_STEP_SUMMARY
          done

      - name: Set up Node.js for Pi Agent
        uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Install Pi Coding Agent
        run: npm install -g @earendil-works/pi-coding-agent

      - name: Pi AI security review
        env:
          OPENAI_BASE_URL: ${{ secrets.AI_BASE_URL || vars.AI_BASE_URL || secrets.OPENAI_BASE_URL }}
          OPENAI_API_KEY: ${{ secrets.AI_API_KEY || secrets.OPENAI_API_KEY }}
          AI_MODEL: ${{ vars.AI_MODEL || 'openai/deepseek-chat' }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PI_CONFIG_CONTENT: >-
            {"permission":{"external_directory":{"*":"deny","${{ runner.temp }}/*":"allow"}}}
          prompt: |
            你是一名 Arch Linux 安全审查专家。请对以下 AUR 包的源码进行深度安全检查。

            包名: ${{ inputs.package-name }}
            源码路径: ${{ env.SOURCE_DIR }}

            ## 审查要求

            请逐个检查以下安全维度，对每个维度给出 PASS / WARN / FAIL 判定：

            ### 1. 源码完整性校验（Source Integrity）
            - PKGBUILD 中 `source` 数组的所有 URL 是否指向可信域名？
            - `sha256sums` / `sha512sums` / `b2sums` 是否完整覆盖所有 source 条目？
            - 是否存在 `SKIP` 跳过校验的条目？如有，评估其风险。
            - 是否有通过 `curl`/`wget` 在 build()/prepare() 中动态下载文件且不校验哈希的行为？

            ### 2. 构建脚本安全（Build Script Safety）
            - PKGBUILD 中 `build()`, `prepare()`, `package()`, `install()` 等函数是否有以下危险模式：
              - `curl ... | bash` / `curl ... | sh`（管道执行远程脚本）
              - `eval` / `exec` 在不可信输入上使用
              - `rm -rf /` 或 `rm -rf $HOME`（高危路径删除）
              - `chmod 777` / `chmod -R 777`（过度宽松权限）
              - 向 `/usr/bin/`, `/usr/lib/` 等系统目录写入非标准文件
              - 修改 `/etc/passwd`, `/etc/shadow`, `/etc/sudoers`
              - 启动/启用 systemd 服务的 `systemctl enable`（应只放 service 文件，不自动启用）
            - `.install` 脚本的 `post_install`/`post_upgrade`/`pre_remove` 函数是否有危险操作？

            ### 3. 依赖安全（Dependency Security）
            - `depends` / `makedepends` / `optdepends` 中的包名是否都是已知合法的 Arch Linux 包？
            - 是否依赖了来源不明或已废弃的包？
            - `makedepends` 中是否包含不必要的构建工具（可能用于隐藏恶意行为，如包含 `netcat`, `nmap` 等非编译工具）？

            ### 4. 敏感信息泄露（Secret Leakage）
            - 源码中是否硬编码了 API Key, Token, 密码, 私钥等敏感信息？
            - PKGBUILD 变量中是否意外写入了密钥/凭证？

            ### 5. 已知漏洞模式（Known Vulnerability Patterns）
            - `.patch` 文件内容是否有引入安全漏洞的修改？
            - `.service` / `.timer` 等 systemd 单元文件是否以 `root` 运行但无安全加固（`ProtectSystem`, `NoNewPrivileges` 等）？
            - 是否包含 SUID 二进制或 `setcap` 操作？

            ### 6. 供应链风险（Supply Chain Risk）
            - source URL 中是否混合了多个不同域名的资源？
            - 是否有从私有仓库或短链接跳转下载的行为？
            - `validpgpkeys` 指纹是否明确？是否存在未知的 GPG 指纹？

            ## 输出格式

            请按以下格式输出审查报告，直接写入 ${{ env.SOURCE_DIR }}-sec-report.md：

            ```markdown
            # AUR 安全审查报告

            **包名**: ${{ inputs.package-name }}
            **源码**: ${{ inputs.source-url }}
            **审查时间**: (当前时间)
            **审查工具**: OpenCode + Claude Sonnet 4

            ## 审查结论

            **最终判定**: PASS / FAIL

            ## 详细结果

            | 维度 | 判定 | 说明 |
            |------|------|------|
            | 源码完整性校验 | PASS/WARN/FAIL | ... |
            | 构建脚本安全 | PASS/WARN/FAIL | ... |
            | 依赖安全 | PASS/WARN/FAIL | ... |
            | 敏感信息泄露 | PASS/WARN/FAIL | ... |
            | 已知漏洞模式 | PASS/WARN/FAIL | ... |
            | 供应链风险 | PASS/WARN/FAIL | ... |

            ## 发现的问题

            (如有 FAIL/WARN，逐条列出问题描述、位置、风险等级、建议修复方案)

            ## 建议

            (整体安全性评价和后续建议)

            ## 审查覆盖

            - 审查文件数: N
            - 审查行数: N
            ```

            注意：
            - 必须以 exit 0 退出（审查通过），以 exit 1 退出（审查不通过）。
            - 最终判定规则：任一维度 FAIL → 最终 FAIL；有 WARN 但无 FAIL → 最终 PASS（附带提醒）。
            - 仅审查源码的安全问题，不涉及代码风格或功能正确性。
          agent: architect
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Upload AI review report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ai-review-report-${{ inputs.package-name }}
          path: ${{ env.SOURCE_DIR }}-sec-report.md

  # ============================================================
  # Layer 3: Trivy 文件系统漏洞扫描
  # ============================================================
  dependency-scan:
    name: "Layer 3 — Dependency & File Scan (Trivy)"
    runs-on: ubuntu-latest
    timeout-minutes: 5
    outputs:
      status: ${{ job.status }}
    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Clone AUR source
        run: |
          git clone --depth 1 "${{ inputs.source-url }}" "${{ env.SOURCE_DIR }}"

      - name: Trivy — filesystem vulnerability scan
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: fs
          scan-ref: ${{ env.SOURCE_DIR }}
          format: sarif
          output: trivy-results.sarif
          severity: CRITICAL,HIGH
          exit-code: "1"
          ignore-unfixed: true

      - name: Upload Trivy SARIF results
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: trivy-results.sarif
          category: trivy-fs

  # ============================================================
  # Layer 4: 触发构建
  # ============================================================
  trigger-build:
    name: "Trigger Build (all scans passed)"
    runs-on: ubuntu-latest
    needs: [quick-gate, ai-review, dependency-scan]
    if: ${{ success() }}
    steps:
      - name: Trigger build workflow
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh workflow run build.yml \
            --repo "${{ github.repository }}" \
            --ref "${{ github.ref_name }}" \
            -f package-name="${{ inputs.package-name }}" \
            -f source-url="${{ inputs.source-url }}"

      - name: Summary
        run: |
          echo "## ✅ Security Scan Passed" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "- **包名**: ${{ inputs.package-name }}" >> $GITHUB_STEP_SUMMARY
          echo "- **源码**: ${{ inputs.source-url }}" >> $GITHUB_STEP_SUMMARY
          echo "- **Layer 1 (Quick Gate)**: PASS" >> $GITHUB_STEP_SUMMARY
          echo "- **Layer 2 (AI Review)**: PASS" >> $GITHUB_STEP_SUMMARY
          echo "- **Layer 3 (Trivy Scan)**: PASS" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "已触发构建: \`build.yml\`" >> $GITHUB_STEP_SUMMARY
```

### 3.1 YAML 设计要点

| 要素 | 决策 | 理由 |
|------|------|------|
| Job 并行 | quick-gate, ai-review, dependency-scan 并行 | 三类扫描互不依赖，并行可缩短总耗时 |
| timeout-minutes | quick-gate 5min, ai-review 10min, dependency-scan 5min | 防止无限等待，超时即失败 |
| `needs` | trigger-build 依赖所有三个扫描 job | 只要任一失败，就不会触发构建 |
| `if: success()` | trigger-build 仅在全部成功时执行 | 默认行为，显式声明增加可读性 |
| `continue-on-error: false` | 扫描步骤使用 | 任何扫描失败立即终止该 job |
| `if: always()` | SARIF/报告上传步骤 | 即使扫描失败也保留结果供审查 |
| 源码隔离 | 各 job 独立 clone 到 `/tmp/aur-source` | 避免 job 间污染，且符合 Actions 最佳实践 |

---

## 4. Pi Agent (gh-aw) Prompt 与 BaseURL 设计说明

### 4.1 设计原则

1. **角色设定明确**：`Arch Linux 安全审查专家`——限定审查范围，避免 AI 偏离主题
2. **检查清单化**：6 个维度的检查项均为 AUR 包常见安全风险的具体实例
3. **判定可执行**：每个维度 PASS/WARN/FAIL，最终有明确的合入规则
4. **输出结构化**：Markdown 报告格式，便于存档和人工复查
5. **模型与 BaseURL 自由定制**：通过 `AI_BASE_URL` / `OPENAI_BASE_URL` 与 `AI_MODEL` 支持 OpenAI / DeepSeek / 各种兼容 API

### 4.2 关键检查项覆盖的 AUR 典型攻击面

| 攻击面 | 检查项 | 历史案例 |
|--------|--------|----------|
| 恶意 source URL | 源码完整性校验 | 2024 年 AUR 曾出现 PKGBUILD 中替换 source URL 指向恶意 fork 的事件 |
| 管道执行 | `curl \| bash` 检测 | AUR 恶意包常见手法，通过管道执行隐藏脚本 |
| 系统篡改 | 修改 `/etc/sudoers` 等 | 提权攻击的常见路径 |
| 未校验哈希 | `SKIP` 摘要 | 允许攻击者中间人篡改下载内容 |
| GPG 未知指纹 | `validpgpkeys` 审查 | 供应链攻击可用伪造签名绕过验证 |

---

## 5. Secrets 配置清单

| Secret / Variable 名称 | 用途 | 存储位置 | 备注 |
|------------|------|---------|------|
| `AI_BASE_URL` / `OPENAI_BASE_URL` | 自定义 AI 接口 Base URL（如 `https://api.deepseek.com/v1`） | Repository Secrets / Vars | 可选，支持私有中转或兼容端点 |
| `AI_API_KEY` / `OPENAI_API_KEY` | Pi Agent AI 审查调用 API Key | GitHub Repository Secrets | 必需，调用模型推理 API |
| `GITHUB_TOKEN` | `trigger-build` job 中调用 `gh workflow run` | GitHub Actions 自动注入 | 无需手动配置，但需要 `actions: write` 权限 |

> **不需要新增的 Secrets**：本 workflow 不直接访问 R2 或 Cloudflare，因此不需要 `AWS_*`、`CLOUDFLARE_*`、`GPG_*` 等 secret。这些由下游 `build.yml` 使用。

---

## 6. 权限配置

```yaml
permissions:
  contents: read          # checkout 本仓库（读取共享配置）
  actions: write          # 触发下游 build.yml
  security-events: write  # 上传 Trivy SARIF 结果到 GitHub Security 面板
```

| 权限 | 最小化原则 | 说明 |
|------|-----------|------|
| `contents: read` | ✅ 只读 | 无需写仓库内容 |
| `actions: write` | ✅ 必要 | 仅用于触发下游 workflow |
| `security-events: write` | ✅ 必要 | 仅用于上传 SARIF 安全报告 |

---

## 7. 与现有 workflow 的串联

### 7.1 调用链

```
check-aur-updates.yml (cron 每 6h)
    │  检测到新版本
    ├──→ 调用 gh workflow run security-scan.yml
    │       -f package-name=xxx
    │       -f source-url=xxx
    │
    └──→ security-scan.yml 全部 PASS
           │
           └──→ 自动调用 gh workflow run build.yml
                   -f package-name=xxx
                   -f source-url=xxx
```

### 7.2 `check-aur-updates.yml` 改动（后续实施）

`check-aur-updates-action` 检测到新版本后，改为触发 `security-scan.yml` 而非直接触发 `build.yml`：

```yaml
# 在 check-aur-updates-action 中
gh workflow run security-scan.yml \
  -f package-name="$PACKAGE" \
  -f source-url="$URL"
```

### 7.3 向后兼容

- `build.yml` **不做任何修改**，仍可独立通过 `workflow_dispatch` 手动触发
- 如果用户确定某包安全无虞，可跳过扫描直接手动触发 `build.yml`
- `security-scan.yml` 作为新增的**可选门禁**，不破坏现有流程

---

## 8. 分阶段实施计划

### Phase 1: Layer 1 快速门禁（第一周）

**目标**：快速上线 Gitleaks + Semgrep，阻断最明显的安全问题。

| 任务 | 产出 | 预计耗时 |
|------|------|---------|
| 编写 `.gitleaks.toml` 规则配置 | `.gitleaks.toml` | 1h |
| 实现 `security-scan.yml` 中的 `quick-gate` job | workflow 可运行 | 2h |
| 实现 `trigger-build` job | 串联 build.yml | 1h |
| 测试完整流程 | 验证报告 | 2h |

### Phase 2: Layer 3 Trivy 扫描（第二周）

**目标**：添加已知漏洞扫描，覆盖依赖和文件层面的 CVE。

| 任务 | 产出 | 预计耗时 |
|------|------|---------|
| 实现 `dependency-scan` job | workflow 可运行 | 2h |
| 配置 SARIF 上传到 GitHub Security 面板 | Security 面板可查看 | 1h |
| 测试各种包类型（-bin, -git, 标准） | 验证报告 | 2h |

### Phase 3: Layer 2 Pi Agent AI 审查（第三周）

**目标**：上线 AI 深度审查，覆盖传统工具无法检测的逻辑安全问题。

| 任务 | 产出 | 预计耗时 |
|------|------|---------|
| 配置 `AI_API_KEY` / `AI_BASE_URL` secret | Secret 就绪 | 0.5h |
| 实现 `ai-review` job（Pi Agent + gh-aw 规范） | workflow 可运行 | 2h |
| 使用已知恶意 PKGBUILD 样本测试 | 验证 AI 检出率 | 3h |
| 调优 prompt（基于 Phase 3 测试结果） | 优化版 prompt | 2h |

### 后续优化（Phase 4+）

- **回写结果到 Issue/PR**：Pi Agent 审查结果作为 comment 自动回写到对应 Issue
- **白名单机制**：已知安全的包可跳过某些扫描层
- **增量扫描**：仅扫描 PKGBUILD diff 而非全量 clone
- **扫描结果 Dashboard**：汇总历史扫描数据，统计通过率

---

## 9. 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| AI API 调用超时 | AI 审查 job 失败，阻塞构建 | 中 | `timeout-minutes: 15` 兜底；可跳过 AI 层手动构建 |
| API 额度耗尽 | 同上 | 低 | 设置 API usage alert；备用模型降级策略 |
| AI 误判（假阳性/假阴性） | 合法包被阻断或恶意包漏过 | 中 | AI 判定不作为唯一依据，Layer 1/3 提供确定性扫描；WARN 不阻断 |
| Gitleaks/Semgrep 规则不覆盖 AUR 特有模式 | Layer 1 漏检 | 中 | 自定义 `.gitleaks.toml` 规则 + Semgrep 自定义规则 |
| Trivy SARIF 上传失败 | 安全面板无法查看结果 | 低 | `if: always()` 确保不阻断流程 |
| `gh workflow run` 触发失败 | 构建无法自动启动 | 低 | 手动触发 build.yml 作为回退 |
| AUR 仓库 clone 失败（网络问题） | 所有 job 失败 | 低 | 重试机制 (GHA 原生 retry)；可考虑 mirror 源 |

---

## 10. 假设与不确定项

| 编号 | 假设 | 待确认 |
|------|------|--------|
| A1 | `@earendil-works/pi-coding-agent` 支持自定义 BaseURL 和标准模型调用 | 需在 Phase 3 实施前验证参数与自定义 BaseURL 连接性 |
| A2 | `GITHUB_TOKEN` 默认权限足以触发同仓库的 `workflow_dispatch` | 已验证：需要 `actions: write` 权限 |
| A3 | Anthropic API 单次调用延迟在 1-3 分钟内可返回结果 | Phase 3 测试时验证并调整 timeout |
| A4 | `.gitleaks.toml` 暂不需要自定义规则，使用默认规则即可 | Phase 1 实施时根据首次扫描结果决定 |
| A5 | Semgrep `config: auto` 模式能覆盖 shell 脚本和 PKGBUILD | Phase 1 测试确认，否则配置额外规则集 |

---

## 11. 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `.github/workflows/security-scan.yml` | 新增 | 安全扫描 workflow 定义 |
| `.gitleaks.toml` | 新增（可选） | Gitleaks 自定义规则 |
| `.github/workflows/build.yml` | 不变 | 现有构建 workflow |
| `.github/workflows/check-aur-updates.yml` | 后续修改 | 将直接触发 build.yml 改为先触发 security-scan.yml |

---

## 12. 验收标准

1. ✅ `security-scan.yml` 可通过 `workflow_dispatch` 手动触发
2. ✅ 输入 `package-name` 和 `source-url` 后，三个扫描 job 并行执行
3. ✅ 任一扫描 job 失败，不触发 `build.yml`
4. ✅ 全部扫描通过，自动触发 `build.yml` 且参数正确传递
5. ✅ Trivy SARIF 结果可在 GitHub Security 面板查看
6. ✅ AI 审查报告以 Artifact 形式保存，可下载查看
7. ✅ 对已知恶意 PKGBUILD 样本（如含 `curl | bash` 模式的包），Layer 2 应给出 FAIL 判定
