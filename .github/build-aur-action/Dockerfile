FROM archlinux:latest
RUN pacman -Syu base-devel git --noconfirm --overwrite '*' \
    && sed -i 's/if (( EUID == 0 )); then/if false; then/' /usr/bin/makepkg \
    && sed -i 's/\(OPTIONS=.*\)\bdebug\b/\1/' /etc/makepkg.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
