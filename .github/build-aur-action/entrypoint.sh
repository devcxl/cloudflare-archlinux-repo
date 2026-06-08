#!/bin/bash
set -euo pipefail

PACKAGE_NAME=$1
SOURCE_URL=$2

git clone "$SOURCE_URL" "$PACKAGE_NAME"
cd "$PACKAGE_NAME"
makepkg -sf --noconfirm
