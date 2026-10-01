#!/bin/bash
# Nasdaq ORB companion: second portable MT5 instance + EA + preset + systemd service. Run as root.
set -uo pipefail
SRC=/root/gtb_deploy
BASE="/home/mt5/.wine/drive_c/Program Files"
M1="$BASE/MetaTrader 5"; M2="$BASE/MetaTrader 5 NQ"
if [ ! -d "$M2" ]; then
  echo "creating $M2"
  mkdir -p "$M2"
  (cd "$M1" && tar --exclude='./Bases' --exclude='./logs' --exclude='./MQL5/Logs' --exclude='./config/gtb_start.ini' --exclude='./Tester' -cf - .) | (cd "$M2" && tar -xf -)
  chown -R mt5:mt5 "$M2"
fi
install -d -o mt5 -g mt5 "$M2/MQL5/Experts/NasdaqORB"
install -o mt5 -g mt5 -m 644 "$SRC/NasdaqORB.mq5" "$SRC/NasdaqORB.ex5" "$M2/MQL5/Experts/NasdaqORB/"
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all WINEDLLOVERRIDES="mscoree=;mshtml=" bash -c "
  cd \"$M2\" && timeout 180 wine MetaEditor64.exe /portable /compile:'MQL5\Experts\NasdaqORB\NasdaqORB.mq5' /log:'MQL5\Experts\NasdaqORB\compile.log' >/dev/null 2>&1"
iconv -f UTF-16LE -t UTF-8 "$M2/MQL5/Experts/NasdaqORB/compile.log" 2>/dev/null | grep -Ei 'result' | tail -1
iconv -f UTF-8 -t UTF-16LE "$SRC/nq_live.set" | { printf '\xff\xfe'; cat; } > "$M2/MQL5/Presets/nq_live.set"
chown mt5:mt5 "$M2/MQL5/Presets/nq_live.set"
install -o mt5 -g mt5 -m 750 "$SRC/run_mt5_nq.sh" /home/mt5/gtb/run_mt5_nq.sh
cat > /etc/systemd/system/gtb-mt5-nq.service <<'UNIT'
[Unit]
Description=MetaTrader 5 - Nasdaq ORB companion (US100.cash M15)
After=network-online.target gtb-xvfb.service gtb-mt5.service
Requires=gtb-xvfb.service

[Service]
User=mt5
ExecStart=/home/mt5/gtb/run_mt5_nq.sh
Restart=always
RestartSec=20

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable gtb-mt5-nq.service >/dev/null 2>&1
systemctl restart gtb-mt5-nq.service
sleep 45
L=$(ls -t "$M2"/logs/*.log 2>/dev/null | head -1)
[ -n "$L" ] && iconv -f UTF-16LE -t UTF-8 "$L" | grep -E 'authoriz|inputs read|Experts|synchroniz' | tail -6
