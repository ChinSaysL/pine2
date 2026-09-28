#!/bin/bash
F="/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
M1="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"; M2="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5 NQ"
echo "=== now (UTC)"; date -u
echo "=== services"; for s in gtb-xvfb gtb-mt5 gtb-mt5-nq gtb-vnc gtb-notifier; do printf '%-13s %-8s since %s\n' "$s" "$(systemctl is-active $s)" "$(systemctl show -p ActiveEnterTimestamp --value $s)"; done
echo "=== restarts / stops of the MT5 services (last 24 h)"
journalctl -u gtb-mt5 -u gtb-mt5-nq --since "-24h" --no-pager -o short-iso | grep -Ei "start|stop|fail|exit|kill|main process" | tail -30
echo "=== notifier alerts (last 24 h)"
journalctl -u gtb-notifier --since "-24h" --no-pager -o short-iso | grep -vE "START|REGIME" | tail -25
echo "=== EA events (last 15)"; tail -15 "$F/events.log"
echo "=== gold heartbeat"; cat "$F/heartbeat.txt" | grep -E "time_gmt|connected|trade_allowed|balance|equity|positions|regime|history|halted|last_tick"
echo "=== nasdaq heartbeat"; cat "$F/nasdaq_heartbeat.txt"
echo "=== gold terminal log (last 12)"; L=$(ls -t "$M1"/logs/*.log | head -1); iconv -f UTF-16LE -t UTF-8 "$L" | tail -12
echo "=== nasdaq terminal log (last 12)"; L=$(ls -t "$M2"/logs/*.log | head -1); iconv -f UTF-16LE -t UTF-8 "$L" | tail -12
echo "=== memory / disk / load"; free -m | head -2; df -h / | tail -1; uptime
echo "=== OOM / crashes (last 24 h)"; journalctl -k --since "-24h" --no-pager | grep -iE "oom|killed process" | tail -5; echo "(none above = none)"
