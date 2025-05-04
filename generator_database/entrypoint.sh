#!/bin/bash
cd $2
repo-add $1.db.tar.zst *.pkg.tar.zst
ls -lh