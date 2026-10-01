#!/bin/bash
# Ship the afternoon break-even Nasdaq EA to the live VPS setup:
#   backup -> install the new .mq5 + preset -> compile in the live NQ install -> restart gtb-mt5-nq -> verify.
# Rollback: cp the files from $RES/rollback_nq_* back and restart gtb-mt5-nq.
set -uo pipefail
LIVE=/home/mt5/.wine
M2="$LIVE/drive_c/Program Files/MetaTrader 5 NQ"
F="$LIVE/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"
RES=/root/gtb_test_results
D=$(date -u +%Y%m%d)
LOG="$RES/deploy_be.log"
mkdir -p "$RES"; exec >> "$LOG" 2>&1

echo
echo "######## DEPLOY afternoon break-even $(date -u '+%F %T') ########"
echo "--- live account / state before"
grep -E "balance=|equity=|positions=" "$F/heartbeat.txt"
grep -E "time_gmt|positions=" "$F/nasdaq_heartbeat.txt" 2>/dev/null

echo "=== 1) backups (for rollback)"
cp -f "$M2/MQL5/Experts/NasdaqORB/NasdaqORB.mq5" "$RES/rollback_nq_Ea.mq5"
cp -f "$M2/MQL5/Experts/NasdaqORB/NasdaqORB.ex5" "$RES/rollback_nq_Ea.ex5"
cp -f "$M2/MQL5/Presets/nq_live.set"             "$RES/rollback_nq_live.set"
ls -la "$RES"/rollback_nq_*

echo "=== 2) installing the new EA + preset"
install -o mt5 -g mt5 -m 644 /root/NasdaqORB.mq5 "$M2/MQL5/Experts/NasdaqORB/NasdaqORB.mq5"
install -o mt5 -g mt5 -m 644 /root/NasdaqORB.mq5 /root/gtb_deploy/NasdaqORB.mq5
install -o mt5 -g mt5 -m 644 /root/nq_be.set /root/gtb_deploy/nq_live.set
iconv -f UTF-8 -t UTF-16LE /root/nq_be.set | { printf '\xff\xfe'; cat; } > "$M2/MQL5/Presets/nq_live.set"
chown mt5:mt5 "$M2/MQL5/Presets/nq_live.set"
echo "    preset inputs: $(iconv -f UTF-16LE -t UTF-8 "$M2/MQL5/Presets/nq_live.set" | tr -d '\r' | grep -cE '^[A-Za-z_][A-Za-z0-9_]*=')"
grep -aE 'InpBe' "$M2/MQL5/Presets/nq_live.set" | tr -d '\r' | sed 's/^/    /'

echo "=== 3) compiling in the live NQ install"
rm -f "$M2/MQL5/Experts/NasdaqORB/NasdaqORB.ex5"
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX="$LIVE" WINEDEBUG=-all WINEDLLOVERRIDES="mscoree=;mshtml=" \
  bash -c "cd '$M2' && timeout 240 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\NasdaqORB\\NasdaqORB.mq5'" 2>/dev/null
for i in $(seq 1 45); do [ -f "$M2/MQL5/Experts/NasdaqORB/NasdaqORB.ex5" ] && break; sleep 2; done
ls -la "$M2/MQL5/Experts/NasdaqORB/"
if [ ! -f "$M2/MQL5/Experts/NasdaqORB/NasdaqORB.ex5" ]; then
  echo "COMPILE FAILED - rolling the EA file back"
  cp -f "$RES/rollback_nq_Ea.mq5" "$M2/MQL5/Experts/NasdaqORB/NasdaqORB.mq5"
  cp -f "$RES/rollback_nq_Ea.ex5" "$M2/MQL5/Experts/NasdaqORB/NasdaqORB.ex5"
  cp -f "$RES/rollback_nq_live.set" "$M2/MQL5/Presets/nq_live.set"
  tail -c 700 "$M2/logs/metaeditor.log" | iconv -f UTF-16LE -t UTF-8
  exit 1
fi

echo "=== 4) restarting gtb-mt5-nq"
systemctl restart gtb-mt5-nq
sleep 60

echo "=== 5) verification"
echo "--- NQ terminal journal (authorization + inputs)"
iconv -f UTF-16LE -t UTF-8 "$M2/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -14
echo "--- NQ EA journal (START line with the new setting)"
iconv -f UTF-16LE -t UTF-8 "$M2/MQL5/logs/$D.log" 2>/dev/null | tr -d '\r' | tail -6
echo "--- NQ heartbeat"
cat "$F/nasdaq_heartbeat.txt" 2>/dev/null
echo "--- gold EA still alive? (the two share a Wine prefix)"
grep -E "time_gmt|connected|positions=" "$F/heartbeat.txt"
if ! systemctl is-active --quiet gtb-mt5; then echo "gold service down - restarting"; systemctl restart gtb-mt5; fi
echo "--- services"; systemctl is-active gtb-mt5 gtb-mt5-nq gtb-notifier
echo "--- order errors so far"
iconv -f UTF-16LE -t UTF-8 "$M2/MQL5/logs/$D.log" 2>/dev/null | tr -d '\r' | grep -icE "error|failed|invalid"
echo "### DEPLOY DONE $(date -u '+%F %T')"
