#!/bin/bash
set -euo pipefail

# 杀掉可能冲突的 GPG 代理（清理步骤，失败可忽略）
gpgconf --kill gpg-agent 2>/dev/null || true

# 将敏感凭据写入受权限保护的临时文件，并从环境变量中移除，缩短暴露窗口
# （避免私钥/口令出现在 /proc/<pid>/environ 之外的进程环境中）
tmpdir="$(mktemp -d)"
keyfile="$tmpdir/key.asc"
pwfile="$tmpdir/passphrase"
chmod 700 "$tmpdir"
printf '%s' "${GPG_PRIVATE_KEY:-}" > "$keyfile"
printf '%s' "${GPG_PASSPHRASE:-}" > "$pwfile"
chmod 600 "$keyfile" "$pwfile"
unset GPG_PRIVATE_KEY GPG_PASSPHRASE

cleanup() {
    gpgconf --kill gpg-agent 2>/dev/null || true
    rm -rf "$tmpdir"
    rm -rf "${GNUPGHOME:-$HOME/.gnupg}"
}
trap cleanup EXIT

# 进入包目录（失败则直接中断，不发布任何内容）
cd "$PACKAGE_PATH"

# 收集包文件；无包文件时拒绝生成空数据库，避免清空仓库索引
shopt -s nullglob
pkg_files=(*.pkg.tar.zst)
shopt -u nullglob

if [ ${#pkg_files[@]} -eq 0 ]; then
    echo "Error: 未在 $PACKAGE_PATH 发现任何 .pkg.tar.zst，拒绝发布空仓库数据库" >&2
    exit 1
fi

# 导入私钥（口令经文件描述符传入，不进入进程命令行）
if [ -s "$keyfile" ]; then
    if ! gpg --batch --pinentry-mode loopback --passphrase-file "$pwfile" --import "$keyfile" 2>&1; then
        echo "Error: GPG 私钥导入失败" >&2
        exit 1
    fi
fi

# 对所有 .pkg.tar.zst 文件签名（口令经文件描述符传入）
for name in "${pkg_files[@]}"; do
    if ! gpg --batch --pinentry-mode loopback --passphrase-file "$pwfile" --detach-sig --yes "$name" 2>&1; then
        echo "Error: 包签名失败: $name" >&2
        exit 1
    fi
done

# 重新生成完整仓库数据库（任何失败都立即中断，阻断后续上传）
# 注意：不再在 repo-add 失败时回退生成“空数据库”，否则会清空整个仓库索引
if ! repo-add --verify -R "$DATABASE.db.tar.gz" "${pkg_files[@]}" 2>&1; then
    echo "Error: 仓库数据库生成失败" >&2
    exit 1
fi

# 用私钥签名数据库（等价于 repo-add --sign，但口令可控）
if ! gpg --batch --pinentry-mode loopback --passphrase-file "$pwfile" --detach-sig --yes "$DATABASE.db.tar.gz" 2>&1; then
    echo "Error: 仓库数据库签名失败" >&2
    exit 1
fi

# 同步签名 .files 数据库（repo-add --sign 原本会一并签名，不能遗漏）
if ! gpg --batch --pinentry-mode loopback --passphrase-file "$pwfile" --detach-sig --yes "$DATABASE.files.tar.gz" 2>&1; then
    echo "Error: 文件数据库签名失败" >&2
    exit 1
fi

# 补齐客户端请求的短名符号链接：pacman 按 <仓库名>.db / .db.sig 请求，
# 上传动作会跟随符号链接取真实内容展开为独立的 R2 对象。
# 若缺少 *.sig 链接，桶内根目录的 <db>.sig 将停止更新，
# 导致客户端拿到旧签名验新数据库而报“签名损坏”（2026-08 事故根因）。
ln -sf "$DATABASE.db.tar.gz.sig" "$DATABASE.db.sig"
ln -sf "$DATABASE.files.tar.gz.sig" "$DATABASE.files.sig"

# 上传前校验：数据库文件存在且签名可验证，避免发布损坏/未签名的产物
if [ ! -f "$DATABASE.db.tar.gz" ]; then
    echo "Error: 仓库数据库未生成" >&2
    exit 1
fi
if ! gpg --verify "$DATABASE.db.tar.gz.sig" "$DATABASE.db.tar.gz" >/dev/null 2>&1; then
    echo "Error: 仓库数据库签名校验失败" >&2
    exit 1
fi

# 按客户端视角校验短名路径（gpg 自动跟随符号链接）
if ! gpg --verify "$DATABASE.db.sig" "$DATABASE.db" >/dev/null 2>&1; then
    echo "Error: 短名数据库签名校验失败" >&2
    exit 1
fi
if ! gpg --verify "$DATABASE.files.sig" "$DATABASE.files" >/dev/null 2>&1; then
    echo "Error: 短名文件库签名校验失败" >&2
    exit 1
fi

echo "✅ 仓库数据库已生成并通过签名校验: $DATABASE.db.tar.gz (.db/.files 短名符号链接已同步)"
