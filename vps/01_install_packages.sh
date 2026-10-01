#!/bin/bash
# Gold Trend Breakout bot - step 1: system packages (Wine, virtual display, VNC) and the mt5 user.
# Safe to re-run. Does not touch other services on the server.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

if ! dpkg --print-foreign-architectures | grep -q i386; then
  dpkg --add-architecture i386
fi
apt-get update -q
apt-get install -y -q --no-install-recommends \
  wine wine64 wine32:i386 winbind cabextract \
  xvfb x11vnc xauth xdotool fonts-liberation \
  python3-venv curl ca-certificates

id mt5 >/dev/null 2>&1 || useradd --create-home --shell /bin/bash mt5
echo "wine: $(wine --version 2>/dev/null || echo missing)"
echo "Xvfb: $(command -v Xvfb)  x11vnc: $(command -v x11vnc)"
echo "user mt5: $(id mt5)"
