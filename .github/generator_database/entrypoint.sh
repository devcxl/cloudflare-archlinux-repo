#!/bin/bash

# 杀掉可能冲突的 GPG 代理
gpgconf --kill gpg-agent 2>/dev/null || true

# 导入私钥（如果设置了密码，必须提供）
if [ -n "$GPG_PRIVATE_KEY" ]; then
    echo "$GPG_PRIVATE_KEY" | gpg --batch --pinentry-mode loopback --passphrase "$GPG_PASSPHRASE" --import 2>&1 || true
fi

# 进入包目录
cd "$PACKAGE_PATH" || {
    echo "Error: Failed to change to package directory"
    exit 1
}

# 检查是否有包文件
if compgen -G "*.pkg.tar.zst" > /dev/null; then
    # 对所有 .pkg.tar.zst 文件签名
    for name in *.pkg.tar.zst; do
        gpg --batch --pinentry-mode loopback --passphrase "$GPG_PASSPHRASE" --detach-sig --yes "$name" 2>&1 || true
    done

    # 重新生成完整的仓库数据库并签名
    # 不使用 -n 选项，这样会包含所有当前存在的包，确保与实际存在的包一致
    # -R: 更新后删除旧版本的包
    repo-add --verify --sign -R "$DATABASE.db.tar.gz" *.pkg.tar.zst 2>&1 || {
        echo "Error: Failed to generate repository database"
        # 尝试创建空数据库（如果没有包文件）
        repo-add --verify --sign "$DATABASE.db.tar.gz" 2>&1 || true
    }
else
    echo "Warning: No .pkg.tar.zst files found in $PACKAGE_PATH"
    # 创建空数据库（如果没有包文件）
    repo-add --verify --sign "$DATABASE.db.tar.gz" 2>&1 || true
fi