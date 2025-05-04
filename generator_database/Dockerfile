FROM archlinux:latest
RUN  pacman -Sy --noconfirm --needed devtools
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]