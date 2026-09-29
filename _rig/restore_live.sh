#!/bin/bash
# Restore: kill the stuck test terminal and bring the live gold EA back up.
set -uo pipefail
M="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
F="/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
exec >> /root/gtb_test_results/live_order_test.log 2>&1
echo
echo "######## RESTORE $(date -u '+%F %T') ########"
pkill -f "live_order_test.sh" 2>/dev/null; sleep 1
echo "killing test terminals"; pkill -u mt5 -f 'MetaTrader 5\\terminal64' 2>/dev/null; sleep 3
sudo -u mt5 -H env WINEPREFIX=/home/mt5/.wine wineserver -k 2>/dev/null; sleep 3
rm -f "$M/config/exec_test.ini"
echo "starting gtb-mt5"; systemctl start gtb-mt5
sleep 50
echo "--- gold journal"; iconv -f UTF-16LE -t UTF-8 "$M/logs/$(date -u +%Y%m%d).log" | tr -d '\r' | tail -8
echo "--- heartbeat"; grep -E "time_gmt|connected|period|positions=|balance=" "$F/heartbeat.txt"
echo "--- services"; systemctl is-active gtb-mt5 gtb-mt5-nq gtb-notifier
echo "--- live EA/preset md5"; md5sum -c /root/gtb_test_results/live_before_lot.md5 2>&1
