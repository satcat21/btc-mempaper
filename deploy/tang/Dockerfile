FROM debian:trixie-slim

# Debian 13 (trixie) matches what most Proxmox LXC hosts run today and
# serves keys from /var/lib/tang; Debian 12 used /var/db/tang. The path is
# passed explicitly below so this does not depend on the distro default.
# tang provides tangd and tangd-keygen; socat turns the inetd-style tangd
# into a TCP listener, which is what the upstream systemd unit does with
# socket activation. jose computes the thumbprint printed at startup, and
# curl is what tang-show-keys uses if you run it inside the container.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tang socat jose curl \
 && rm -rf /var/lib/apt/lists/*

VOLUME /var/lib/tang
EXPOSE 7500

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
