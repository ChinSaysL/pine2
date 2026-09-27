#!/bin/bash
# Gold Trend Breakout bot - step 3: EA, services (MT5, VNC, notifier). Run as root from the folder
# holding GoldTrendBreakout.mq5 / .ex5, run_mt5.sh, notifier.py and gtb_live.set. Safe to re-run.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
MT5="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all

install -d -o mt5 -g mt5 -m 700 /home/mt5/gtb
install -o mt5 -g mt5 -m 750 "$SRC/run_mt5.sh" /home/mt5/gtb/run_mt5.sh
install -o root -g root -m 755 "$SRC/notifier.py" /usr/local/bin/gtb-notifier.py
install -d -m 750 -o root -g mt5 /etc/gtb

# First portable start creates the MQL5 data folders inside the install directory.
if [ ! -d "$MT5/MQL5/Experts" ]; then
  sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all \
    bash -c "cd \"$MT5\" && timeout 90 wine terminal64.exe /portable >/dev/null 2>&1 || true; wineserver -k || true"
fi

install -d -o mt5 -g mt5 "$MT5/MQL5/Experts/GoldTrendBreakout" "$MT5/MQL5/Presets"
install -o mt5 -g mt5 -m 644 "$SRC/GoldTrendBreakout.mq5" "$SRC/GoldTrendBreakout.ex5" "$MT5/MQL5/Experts/GoldTrendBreakout/"
# MT5 reads .set files as UTF-16LE
iconv -f UTF-8 -t UTF-16LE "$SRC/gtb_live.set" | { printf '\xff\xfe'; cat; } > "$MT5/MQL5/Presets/gtb_live.set"
chown mt5:mt5 "$MT5/MQL5/Presets/gtb_live.set"

# Compile with the server's own MetaEditor (keeps the .ex5 in step with the installed terminal build).
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all bash -c "
  cd \"$MT5\" && timeout 180 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\GoldTrendBreakout\\GoldTrendBreakout.mq5' /log:'MQL5\\Experts\\GoldTrendBreakout\\compile.log' >/dev/null 2>&1 || true
  wineserver -k || true"
iconv -f UTF-16LE -t UTF-8 "$MT5/MQL5/Experts/GoldTrendBreakout/compile.log" 2>/dev/null | grep -Ei 'result|error' | tail -3 || true

# VNC password (random, stored for the mt5 user; VNC only listens on localhost)
if [ ! -f /home/mt5/.vnc/passwd ]; then
  install -d -o mt5 -g mt5 -m 700 /home/mt5/.vnc
  PW="$(python3 -c 'import secrets,string; print("".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10)))')"
  sudo -u mt5 x11vnc -storepasswd "$PW" /home/mt5/.vnc/passwd >/dev/null 2>&1
  echo "$PW" > /root/gtb_vnc_password.txt
  chmod 600 /root/gtb_vnc_password.txt
fi

cat > /etc/systemd/system/gtb-mt5.service <<'EOF'
[Unit]
Description=Gold Trend Breakout - MetaTrader 5 with the EA
After=network-online.target gtb-xvfb.service
Requires=gtb-xvfb.service
Wants=network-online.target

[Service]
User=mt5
ExecStart=/home/mt5/gtb/run_mt5.sh
ExecStopPost=/bin/bash -c 'WINEPREFIX=/home/mt5/.wine wineserver -k || true'
Restart=always
RestartSec=20
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/gtb-vnc.service <<'EOF'
[Unit]
Description=Gold Trend Breakout - VNC view of the MT5 screen (localhost only, use an SSH tunnel)
After=gtb-xvfb.service
Requires=gtb-xvfb.service

[Service]
User=mt5
ExecStart=/usr/bin/x11vnc -display :99 -localhost -rfbport 5900 -forever -shared -rfbauth /home/mt5/.vnc/passwd -quiet
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/gtb-notifier.service <<'EOF'
[Unit]
Description=Gold Trend Breakout - Telegram notifier and watchdog
After=network-online.target

[Service]
User=root
ExecStart=/usr/bin/python3 /usr/local/bin/gtb-notifier.py
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

touch /home/mt5/gtb/notifier_state.json && chown mt5:mt5 /home/mt5/gtb/notifier_state.json
systemctl daemon-reload
systemctl enable --now gtb-vnc.service gtb-mt5.service gtb-notifier.service
sleep 20
systemctl --no-pager --lines=0 status gtb-xvfb gtb-mt5 gtb-vnc gtb-notifier | grep -E '●|Active:'
ss -tlnp | grep 5900 || true
