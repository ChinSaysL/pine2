#!/bin/bash
# Gold Trend Breakout bot - health check. Run as root: bash check_status.sh
M="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
F="/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
echo "--- services"
for s in gtb-xvfb gtb-mt5 gtb-mt5-nq gtb-vnc gtb-notifier; do printf '%-14s %s\n' "$s" "$(systemctl is-active "$s")"; done
echo "--- MT5 process"
pgrep -u mt5 -af 'terminal64' | cut -c1-120 || echo "terminal64 not running"
echo "--- firewall"
ufw status | head -6
echo "--- terminal log (last lines)"
L=$(ls -t "$M"/logs/*.log 2>/dev/null | head -1)
[ -n "$L" ] && iconv -f UTF-16LE -t UTF-8 "$L" 2>/dev/null | tail -12
echo "--- EA log (last lines)"
L=$(ls -t "$M"/MQL5/Logs/*.log 2>/dev/null | head -1)
[ -n "$L" ] && iconv -f UTF-16LE -t UTF-8 "$L" 2>/dev/null | tail -12
echo "--- EA files"
ls -la "$F" 2>/dev/null || echo "no EA files yet (EA not started or no account)"
[ -f "$F/heartbeat.txt" ] && cat "$F/heartbeat.txt"
echo "--- Nasdaq companion"
[ -f "$F/nasdaq_heartbeat.txt" ] && cat "$F/nasdaq_heartbeat.txt" || echo "no Nasdaq heartbeat yet"
echo "--- notifier journal"
journalctl -u gtb-notifier --no-pager -n 5 -o cat
echo "--- other services untouched"
systemctl is-active arcetis-inbox.service fail2ban.service cron.service
