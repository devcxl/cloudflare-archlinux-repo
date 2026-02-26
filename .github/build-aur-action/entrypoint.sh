#!/bin/bash
PACKAGER=$2
git clone "https://aur.archlinux.org/$1.git"
cd "$1"
makepkg -sf --noconfirm