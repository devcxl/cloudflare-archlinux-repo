# AUR 安全审查报告

**包名**: visual-studio-code-bin
**源码**: https://aur.archlinux.org/visual-studio-code-bin.git
**审查时间**: 2026-07-28T08:07:56Z

## 审查结论

**最终判定**: PASS

## 详细结果

| 维度 | 判定 | 说明 |
|------|------|------|
| 源码完整性校验 | PASS | 所有 source URL 指向 Microsoft 官方 CDN（`update.code.visualstudio.com`），sha256sums 完整覆盖所有架构的 source 条目，无 SKIP 跳过项，无动态下载行为。 |
| 构建脚本安全 | PASS | `package()` 仅执行标准解包、安装、符号链接和 sed 修补操作；`chrome-sandbox` 的 setuid 移除为安全加固措施；`.install` 脚本仅打印提示信息；无 curl\|bash、eval、chmod 777 等危险模式。 |
| 依赖安全 | PASS | 所有 depends/optdepends 均为 Arch Linux 官方仓库提供的标准合法包，无废弃或可疑依赖。optdepends 中的 `icu69` 版本较旧但已明确标注用途且为可选。 |
| 敏感信息泄露 | PASS | 所有文件（PKGBUILD、.install、.sh 启动脚本、.SRCINFO）中未发现硬编码的 API Key、Token、密码或私钥。 |
| 已知漏洞模式 | PASS | 无 `.patch` 或 `.service` 文件。`.sh` 启动脚本逻辑简单，无已知漏洞模式。 |
| 供应链风险 | PASS | 所有 source URL 指向 Microsoft 官方 CDN 域名 `update.code.visualstudio.com`，来源可信。此为 `-bin` 类型包，直接使用 Microsoft 官方预编译 `.deb`，无 `validpgpkeys` 属正常情况，完整性由 sha256sums 保证。 |

## 发现的问题

无 FAIL 或 WARN 项。所有六个安全维度均通过审查。

### 备注

1. **启动脚本变量展开**（`visual-studio-code-bin.sh:11`）：`$CODE_USER_FLAGS` 在 exec 命令行中未加引号，可能导致含空格的多词 flag 被错误拆分。此为轻微功能缺陷而非安全漏洞，攻击者需具备本地文件写入权限才能利用。

2. **optdepends icu69**（`PKGBUILD:24`）：`icu69` 为特定旧版 ICU 库版本，用于 Live Share 功能。该包可能不在 Arch 官方仓库中，用户需额外安装。已明确标记为可选依赖，不影响整体安全性。

3. **setuid 移除**（`PKGBUILD:53`）：`chmod u-s` 移除 `chrome-sandbox` 的 setuid 位，是一项安全加固措施。对于使用 `linux-hardened` 等禁用 user namespaces 的内核的用户，可能需要注释此行以维持沙箱功能。
