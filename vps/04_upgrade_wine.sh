#!/bin/bash
# Gold Trend Breakout bot - step 4: replace Ubuntu's Wine 9.0 with WineHQ stable (MT5 asks for Wine 10+).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
systemctl stop gtb-mt5.service || true
sudo -u mt5 env WINEPREFIX=/home/mt5/.wine wineserver -k 2>/dev/null || true

install -d -m 755 /etc/apt/keyrings
curl -fsSL https://dl.winehq.org/wine-builds/winehq.key -o /etc/apt/keyrings/winehq-archive.key
curl -fsSL https://dl.winehq.org/wine-builds/ubuntu/dists/noble/winehq-noble.sources -o /etc/apt/sources.list.d/winehq-noble.sources
apt-get update -q
apt-get remove -y -q wine wine64 wine32:i386 libwine libwine:i386 fonts-wine 2>/dev/null || true
apt-get install -y -q --install-recommends winehq-stable
echo "wine now: $(wine --version)"

# update the existing prefix to the new Wine
sudo -u mt5 -H env WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all DISPLAY=:99 bash -c 'wineboot -u >/dev/null 2>&1 || true; wineserver -w || true'
