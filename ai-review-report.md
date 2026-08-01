# AUR 安全审查报告

**包名**: opencode-bin
**源码**: https://aur.archlinux.org/opencode-bin.git
**审查时间**: 2026-08-01

## 审查结论

**最终判定**: PASS

## 详细结果

| 维度 | 判定 | 说明 |
|------|------|------|
| 源码完整性校验 | PASS | 所有 source 条目均指向 github.com（GitHub Releases，可信域名）；每个架构的 source 条目均有对应的 sha256sums 校验值；无 SKIP 跳过的条目；无 curl/wget 动态下载行为。 |
| 构建脚本安全 | PASS | `package()` 仅包含一条 `install -Dm755` 命令，无 `curl \| bash`、`eval`、`chmod 777`、修改系统文件等危险模式。 |
| 依赖安全 | PASS | 唯一运行时依赖 `ripgrep` 是 Arch Linux 官方仓库（extra）中的合法包，无废弃或可疑依赖。无 makedepends。 |
| 敏感信息泄露 | PASS | PKGBUILD 中无任何硬编码的 API Key、Token、密码、私钥或凭据。 |
| 已知漏洞模式 | PASS | 源码仓库仅包含 PKGBUILD 和 .SRCINFO 两个文件，无 .patch、.service、.install 等可能引入漏洞的附属文件。 |
| 供应链风险 | WARN | Source URL 指向 github.com（可信任）；SHA256 校验值完整；但未设置 `validpgpkeys`，缺少对上游发布制品的 GPG 签名验证。 |

## 发现的问题

### 问题 1：缺少 validpgpkeys（供应链风险）

- **位置**: `PKGBUILD` 全局定义区域
- **风险等级**: 低
- **描述**: PKGBUILD 未声明 `validpgpkeys` 数组，无法对 GitHub Releases 下载的 tarball 进行 GPG 签名验证。当前仅依赖 SHA256 校验值确保文件完整性，但无法验证发布者身份。
- **建议修复**: 联系上游项目 (anomalyco/opencode) 确认是否对 release tarball 提供 GPG 签名。若有，在 PKGBUILD 中添加 `validpgpkeys=('<上游维护者 GPG 指纹>')`；若无，当前仅依赖 SHA256 校验的做法可接受，但应持续关注上游是否引入签名机制。
