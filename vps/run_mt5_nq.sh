#!/bin/bash
# Second MetaTrader 5 instance (portable, own folder) with the Nasdaq ORB EA on US100.cash M15.
# Same account as the gold instance (/home/mt5/gtb/account.env); both write to the shared Common\Files\GoldBreakout.
set -euo pipefail
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree=;mshtml="
MT5="$WINEPREFIX/drive_c/Program Files/MetaTrader 5 NQ"
CFG="$MT5/config/nq_start.ini"
LOGIN=""; PASSWORD=""; SERVER=""
if [ -f /home/mt5/gtb/account.env ]; then
  # shellcheck disable=SC1091
  . /home/mt5/gtb/account.env
fi
mkdir -p "$MT5/config"
{
  printf '[Common]\r\n'
  if [ -n "$LOGIN" ]; then
    printf 'Login=%s\r\nPassword=%s\r\nServer=%s\r\n' "$LOGIN" "$PASSWORD" "$SERVER"
  fi
  printf 'KeepPrivate=1\r\nNewsEnable=0\r\n'
  printf '[Experts]\r\nAllowLiveTrading=1\r\nAllowDllImport=0\r\nEnabled=1\r\nAccount=0\r\nProfile=0\r\n'
  printf '[StartUp]\r\nExpert=NasdaqORB\NasdaqORB\r\nExpertParameters=nq_live.set\r\n'
  printf 'Symbol=US100.cash\r\nPeriod=M15\r\n'
} > "$CFG"
chmod 600 "$CFG"
cd "$MT5"
exec wine terminal64.exe /portable '/config:config\nq_start.ini'
