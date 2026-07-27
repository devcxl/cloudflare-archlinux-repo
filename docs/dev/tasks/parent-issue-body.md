## 背景

为 `cloudflare-archlinux-repo` 项目添加独立的构建前安全扫描 workflow。

## 架构概览

```
security-scan.yml (workflow_dispatch)
  ├── quick-gate     (Layer 1: Gitleaks + Semgrep) ──┐
  ├── ai-review      (Layer 2: OpenCode AI)        ──┤
  ├── dependency-scan (Layer 3: Trivy)              ──┤
  └── trigger-build  (needs all 3, 全部 PASS 后触发 build.yml)
```

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
- [ ] T1: [security-scan.yml 骨架](https://github.com/devcxl/cloudflare-archlinux-repo/issues/2) — workflow 入口 + job 占位 + trigger-build
- [ ] T2: [quick-gate job](https://github.com/devcxl/cloudflare-archlinux-repo/issues/3) — Gitleaks + Semgrep 快速门禁
- [ ] T3: [.gitleaks.toml 规则配置](https://github.com/devcxl/cloudflare-archlinux-repo/issues/4)

### Phase 2 — Layer 3 Trivy 扫描
- [ ] T4: [dependency-scan job](https://github.com/devcxl/cloudflare-archlinux-repo/issues/5) — Trivy + SARIF 上传

### Phase 3 — Layer 2 AI 审查
- [ ] T5: [ai-review job](https://github.com/devcxl/cloudflare-archlinux-repo/issues/6) — OpenCode AI 深度审查
- [ ] T6: [E2E 验证](https://github.com/devcxl/cloudflare-archlinux-repo/issues/7) — prompt 优化与恶意样本测试

## DAG 拓扑

```
                    ┌──────────┐
                    │ T1 骨架   │  (Phase 1)
                    └────┬─────┘
         ┌───────────────┼───────────────────┐
         ▼               ▼                    ▼
    ┌─────────┐    ┌──────────┐    ┌────────────────┐
    │ T2 门禁 │    │ T3 规则   │    │ T4 依赖扫描     │
    │(Phase 1)│    │(Phase 1)  │    │(Phase 2)        │
    └─────────┘    └──────────┘    └────────────────┘
                                   
         ┌───────────────┴───────────────────┐
         ▼                                   ▼
    ┌──────────┐                      (T2, T3, T4, T5
    │ T5 AI    │                       均可并行)
    │(Phase 3) │
    └────┬─────┘
         │
         ▼
    ┌──────────┐
    │ T6 E2E   │
    │(Phase 3) │
    └──────────┘
```
