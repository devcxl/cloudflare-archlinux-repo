#!/bin/bash

echo "$GPG_PRIVATE_KEY" | gpg --import

cd $PACKAGE_PATH

packages=("*.pkg.tar.zst")
for name in $packages; do
    gpg --detach-sig --yes $name
done
repo-add --verify --sign "$DATABASE.db.tar.gz" *.pkg.tar.zst
