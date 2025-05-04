FROM archlinux:latest
RUN  pacman -Sy --noconfirm --needed devtools
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]