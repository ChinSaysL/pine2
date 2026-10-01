#!/bin/bash
# Gold Trend Breakout bot - install gtb_live.set as the EA preset (UTF-16LE, as MT5 expects).
set -euo pipefail
MT5="/home/mt5/.wine/drive_c/Program Files/MetaTrader 5"
iconv -f UTF-8 -t UTF-16LE /root/gtb_deploy/gtb_live.set | { printf '\xff\xfe'; cat; } > "$MT5/MQL5/Presets/gtb_live.set"
chown mt5:mt5 "$MT5/MQL5/Presets/gtb_live.set"
echo "preset installed: $(iconv -f UTF-16LE -t UTF-8 "$MT5/MQL5/Presets/gtb_live.set" | grep -cE '^Inp') inputs"
