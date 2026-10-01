#!/bin/bash
# Starts MetaTrader 5 (portable) on the virtual display with the Gold Trend Breakout EA on XAUUSD H1.
# Account login is read from /home/mt5/gtb/account.env when present (LOGIN, PASSWORD, SERVER);
# otherwise MT5 uses the account last logged in through the remote screen.
set -euo pipefail
export DISPLAY=:99 WINEPREFIX=/home/mt5/.wine WINEDEBUG=-all
# MT5 needs neither Mono nor Gecko; without this Wine may stop on an "install Mono?" dialog nobody can click
export WINEDLLOVERRIDES="mscoree=;mshtml="
MT5="$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
CFG="$MT5/config/gtb_start.ini"
SYMBOL="${GTB_SYMBOL:-XAUUSD}"

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
  printf '[StartUp]\r\nExpert=GoldTrendBreakout\\GoldTrendBreakout\r\nExpertParameters=gtb_live.set\r\n'
  printf 'Symbol=%s\r\nPeriod=H1\r\n' "$SYMBOL"
} > "$CFG"
chmod 600 "$CFG"

cd "$MT5"
# Relative path without spaces: an absolute "C:\Program Files\..." path reached MT5 with broken quoting.
exec wine terminal64.exe /portable '/config:config\gtb_start.ini'
