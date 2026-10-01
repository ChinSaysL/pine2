#!/bin/bash
# Gold Trend Breakout bot - step 2: virtual display service + MetaTrader 5 under Wine (user mt5).
set -euo pipefail

cat > /etc/systemd/system/gtb-xvfb.service <<'EOF'
[Unit]
Description=Gold Trend Breakout - virtual display :99 for MetaTrader 5
After=network.target

[Service]
User=mt5
ExecStart=/usr/bin/Xvfb :99 -screen 0 1366x768x24 -nolisten tcp
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now gtb-xvfb.service
sleep 2

sudo -u mt5 -H bash <<'EOS'
set -euo pipefail
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all WINEARCH=win64
cd /home/mt5
if [ ! -f "$WINEPREFIX/system.reg" ]; then
  wineboot --init >/dev/null 2>&1 || true
  wineserver -w || true
fi
if [ ! -f "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe" ]; then
  curl -fsSL -o mt5setup.exe "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
  timeout 900 wine mt5setup.exe /auto >/dev/null 2>&1 || true
  wineserver -w || true
fi
ls -la "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/" | head -20
EOS
