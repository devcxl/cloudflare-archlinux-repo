#!/bin/bash
cd $1
repo-add repo.db.tar.zst *.pkg.tar.zst
ls -lh