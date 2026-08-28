---
name: "Security Scan (gh-aw Pi Agent)"
description: "AI-powered package security scan using Pi engine with custom baseURL support"
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
  issues: write
  actions: write
engine:
  id: pi
  model: opencode-go/deepseek-v4-flash
  env:
    AI_BASE_URL: ${{ secrets.AI_BASE_URL || vars.AI_BASE_URL || secrets.OPENAI_BASE_URL || 'https://new-api.devcxl.cn/v1' }}
    HALFCABBAGE_API_KEY: ${{ secrets.HALFCABBAGE_API_KEY || secrets.AI_API_KEY || secrets.OPENAI_API_KEY }}
tools:
  cli-proxy: true
  github:
    mode: gh-proxy
---

# Arch Linux Package Security Audit

Perform a deep security audit on the cloned AUR package repository:
- Package: ${{ inputs.package-name }}
- Source URL: ${{ inputs.source-url }}

## Audit Requirements

1. Strictly read-only: Do not modify repository files, create branches, or push commits.
2. Read all files in the package directory (`PKGBUILD`, `.SRCINFO`, `*.install`, `*.patch`, `*.sh`, `*.service`, `*.desktop`, `*.js`, `*.py`).
3. Evaluate 6 security dimensions:
   - Source integrity & checksums
   - Build script safety (`curl | bash`, dangerous commands)
   - Dependency validity
   - Secret leakage
   - Known vulnerability patterns
   - Supply chain risk
4. Generate a full audit report and save it to `${{ runner.temp }}/ai-review-report.md`.
5. Output final verdict on the last line: `FINAL_VERDICT: PASS` or `FINAL_VERDICT: FAIL`.
