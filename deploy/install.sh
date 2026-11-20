#!/usr/bin/env bash
# Install chirone on a pilot machine (Debian/Ubuntu/Mint). Run as root.
#   sudo deploy/install.sh <desktop-user> <model.gguf>
set -euo pipefail
USER_NAME=$1; MODEL=$2
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
SRC=$(cd "$(dirname "$0")/.." && pwd)

apt-get install -y python3-venv psmisc usbutils libglib2.0-bin
python3 -m venv /opt/chirone
# From the release package: install the wheel next to deploy/; from a checkout: the source.
WHEEL=$(ls "$SRC"/chirone-*.whl 2>/dev/null | head -n1 || true)
/opt/chirone/bin/pip install --quiet "${WHEEL:-$SRC}"
ln -sf /opt/chirone/bin/chirone /usr/local/bin/chirone

install -d -m 0755 /usr/local/libexec /opt/chirone/models
cat > /usr/local/libexec/chirone-root-helper <<'SH'
#!/bin/sh
exec /opt/chirone/bin/python -I -m chirone.roothelper "$@"
SH
chmod 0755 /usr/local/libexec/chirone-root-helper

groupadd -f chirone && usermod -aG chirone "$USER_NAME"
TMP=$(mktemp); /opt/chirone/bin/chirone sudoers | grep -v '^#' > "$TMP"
visudo -cf "$TMP" && install -m 0440 "$TMP" /etc/sudoers.d/chirone; rm -f "$TMP"

install -m 0644 "$MODEL" /opt/chirone/models/chirone.gguf
HOME_DIR=$(getent passwd "$USER_NAME" | cut -d: -f6)
install -d -o "$USER_NAME" "$HOME_DIR/.config/systemd/user"
install -m 0644 -o "$USER_NAME" "$SRC/deploy/chirone-llm.service" "$HOME_DIR/.config/systemd/user/"
echo "Now, as $USER_NAME: systemctl --user enable --now chirone-llm"
echo "llama-server must be at /usr/local/bin/llama-server (build it with eval/bench.sh on this machine)."
