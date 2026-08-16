#!/bin/bash
set -euo pipefail

PACKAGE_NAME="${1:?package name is required}"
SOURCE_URL="${2:?source URL is required}"
PATCHES="${3:-}"

if [[ ! "$PACKAGE_NAME" =~ ^[a-zA-Z0-9@_+][a-zA-Z0-9@._+-]*$ ]]; then
  echo "Invalid package name: $PACKAGE_NAME" >&2
  exit 1
fi

for ((attempt = 1; attempt <= 3; attempt++)); do
  rm -rf -- "$PACKAGE_NAME"
  if timeout 60 git clone --depth 1 "$SOURCE_URL" "$PACKAGE_NAME"; then
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

makepkg -sf --noconfirm
