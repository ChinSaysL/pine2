#!/bin/bash
# Gold Trend Breakout bot - step 6: deploy/update the EA and the halt/resume commands, restart MT5.
set -uo pipefail
SRC=/root/gtb_deploy
MT5="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
FILES="/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout"

install -o mt5 -g mt5 -m 644 "$SRC/GoldTrendBreakout.mq5" "$SRC/GoldTrendBreakout.ex5" "$MT5/MQL5/Experts/GoldTrendBreakout/"
sudo -u mt5 -H env DISPLAY=:99 WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all WINEDLLOVERRIDES="mscoree=;mshtml=" bash -c "
  cd \"$MT5\" && timeout 180 wine MetaEditor64.exe /portable /compile:'MQL5\\Experts\\GoldTrendBreakout\\GoldTrendBreakout.mq5' /log:'MQL5\\Experts\\GoldTrendBreakout\\compile.log' >/dev/null 2>&1"
iconv -f UTF-16LE -t UTF-8 "$MT5/MQL5/Experts/GoldTrendBreakout/compile.log" 2>/dev/null | grep -Ei 'result' | tail -1

install -d -o mt5 -g mt5 "$FILES"
cat > /usr/local/bin/gtb-halt <<EOF
#!/bin/bash
# Close every Gold Trend Breakout position and pending order and stop new trades.
sudo -u mt5 touch "$FILES/halt.flag" && echo "HALT on: the EA closes everything within seconds and opens nothing until gtb-resume"
EOF
cat > /usr/local/bin/gtb-resume <<EOF
#!/bin/bash
rm -f "$FILES/halt.flag" && echo "HALT off: the EA trades again from the next bar"
EOF
cat > /usr/local/bin/gtb-status <<'EOF'
#!/bin/bash
bash /root/gtb_deploy/check_status.sh
EOF
chmod 755 /usr/local/bin/gtb-halt /usr/local/bin/gtb-resume /usr/local/bin/gtb-status

systemctl restart gtb-mt5.service
sleep 40
L=$(ls -t "$MT5"/logs/*.log | head -1)
iconv -f UTF-16LE -t UTF-8 "$L" | grep -E 'Experts|Startup|Terminal.*started|authoriz|Network' | tail -6
