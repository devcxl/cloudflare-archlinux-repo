#!/usr/bin/env bash

set -euo pipefail

source_url="${1:?source URL is required}"
destination="${2:?destination is required}"
attempts="${3:-3}"

for ((attempt = 1; attempt <= attempts; attempt++)); do
  rm -rf -- "$destination"
  if timeout 60 git clone --depth 1 "$source_url" "$destination"; then
    exit 0
  fi

  if ((attempt == attempts)); then
    echo "git clone failed after $attempts attempts" >&2
    exit 1
  fi

  sleep $((attempt * 5))
done
