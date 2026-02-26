#!/bin/bash

# 杀掉可能冲突的 GPG 代理
gpgconf --kill gpg-agent

# 导入私钥（如果设置了密码，必须提供）
echo "$GPG_PRIVATE_KEY" | gpg --batch --pinentry-mode loopback --passphrase "$GPG_PASSPHRASE" --import

# 进入包目录
cd "$PACKAGE_PATH"

# 对所有 .pkg.tar.zst 文件签名
for name in *.pkg.tar.zst; do
    gpg --batch --pinentry-mode loopback --passphrase "$GPG_PASSPHRASE" --detach-sig --yes "$name"
done

# 重新生成完整的仓库数据库并签名
# 不使用 -n 选项，这样会包含所有当前存在的包，确保与实际存在的包一致
# -R: 更新后删除旧版本的包
repo-add --verify --sign -R "$DATABASE.db.tar.gz" *.pkg.tar.zst