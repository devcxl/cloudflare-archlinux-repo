#!/usr/bin/env bash
set -euo pipefail

source_url="${1:?source URL is required}"
destination="${2:?destination is required}"
attempts="${3:-3}"

# 校验 source-url：仅允许 https 且 host 在白名单内，防止命令/选项注入
# （workflow_dispatch 输入直接拼入 shell，未做校验属于纵深防御缺口）
if [[ ! "$source_url" =~ ^https://([^/]+\.)?(aur\.archlinux\.org|github\.com|gitlab\.com)/ ]]; then
  echo "Error: source URL 不被允许（仅支持 https 且 host 白名单）: $source_url" >&2
  exit 1
fi

for ((attempt = 1; attempt <= attempts; attempt++)); do
  rm -rf -- "$destination"
  # -- 分隔选项与位置参数，避免异常 URL 被当作 git 选项解析
  if timeout 60 git clone --depth 1 -- "$source_url" "$destination"; then
    exit 0
  fi

  if ((attempt == attempts)); then
    echo "git clone failed after $attempts attempts" >&2
    exit 1
  fi

  sleep $((attempt * 5))
done
