#!/bin/bash
set -euo pipefail

PACKAGE_NAME="${1:?package name is required}"
SOURCE_URL="${2:?source URL is required}"

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
makepkg -sf --noconfirm
