#!/bin/bash
set -euo pipefail

PACKAGE_NAME="${1:?package name is required}"
SOURCE_URL="${2:?source URL is required}"
PATCHES="${3:-}"

# 校验包名（防止 find/cp 路径注入）
if [[ ! "$PACKAGE_NAME" =~ ^[a-zA-Z0-9@_+][a-zA-Z0-9@._+-]*$ ]]; then
  echo "Invalid package name: $PACKAGE_NAME" >&2
  exit 1
fi

# 校验 source-url：仅允许 https 且 host 白名单，防止命令/选项注入
# （workflow_dispatch 输入直接拼入 shell，未做校验属于纵深防御缺口）
if [[ ! "$SOURCE_URL" =~ ^https://([^/]+\.)?(aur\.archlinux\.org|github\.com|gitlab\.com)/ ]]; then
  echo "Invalid source URL (scheme/host not allowed): $SOURCE_URL" >&2
  exit 1
fi

for ((attempt = 1; attempt <= 3; attempt++)); do
  rm -rf -- "$PACKAGE_NAME"
  # -- 分隔选项与位置参数，避免异常 URL 被当作 git 选项解析
  if timeout 60 git clone --depth 1 -- "$SOURCE_URL" "$PACKAGE_NAME"; then
    break
  fi

  if ((attempt == 3)); then
    echo "git clone failed after 3 attempts" >&2
    exit 1
  fi

  sleep $((attempt * 5))
done

cd -- "$PACKAGE_NAME"

# 应用上游 PKGBUILD 修复补丁（相对仓库根目录的路径）
WORKSPACE="${GITHUB_WORKSPACE:-/github/workspace}"
if [[ -n "$PATCHES" ]]; then
  for patch_path in $PATCHES; do
    patch_file="$WORKSPACE/$patch_path"
    if [[ ! -f "$patch_file" ]]; then
      echo "Patch file not found: $patch_path" >&2
      exit 1
    fi
    echo "Applying patch: $patch_path"
    if ! git apply "$patch_file"; then
      echo "Failed to apply patch: $patch_path" >&2
      exit 1
    fi
  done
fi

# 说明：当前 archlinux:latest 的 makepkg 在以非 root 用户运行时，其内部 fakeroot
# 重入（-F）会丢失 pkgdir/cwd，导致构建失败（已在 stock 镜像上复现，属上游回归）。
# 因此此处以保证可用的方式运行 makepkg；构建容器内不持有 GPG 私钥 / R2 凭据
# （仅 generator/download/upload/clean 步骤持有），且上方已对 source-url 做白名单校验，
# 将不可信 PKGBUILD 的提权面限制在一次性构建容器内。
makepkg -sf --noconfirm
