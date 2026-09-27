# Gold Trend Breakout bot - server runbook

MT5 runs under Wine on the Japan server (`5.104.81.124`) as the user `mt5`, with the
`GoldTrendBreakout` EA on XAUUSD H1. Everything lives in its own services and does not touch
the other projects on the server.

| Service | What it does |
|---|---|
| `gtb-xvfb` | virtual screen `:99` for MT5 |
| `gtb-mt5` | MetaTrader 5 + the EA, restarts on crash, starts at boot |
| `gtb-vnc` | view/control of the MT5 screen, **localhost only** (use an SSH tunnel) |
| `gtb-notifier` | Telegram messages + watchdog (heartbeat, connection, Algo Trading, service) |

## Everyday commands (on the server, as root)

```bash
gtb-status        # services, MT5/EA logs, heartbeat
gtb-halt          # EMERGENCY: close everything, open nothing until resumed
gtb-resume        # trade again from the next bar
systemctl restart gtb-mt5      # restart MT5 (after changing settings)
journalctl -u gtb-notifier -f  # what the notifier is sending
```

## See the MT5 screen

```bash
ssh -L 5900:localhost:5900 root@5.104.81.124     # keep this open
ssh root@5.104.81.124 cat /root/gtb_vnc_password.txt
```
Then open a VNC viewer (e.g. RealVNC Viewer, TigerVNC) on `localhost:5900` with that password.
The port is never exposed to the internet; without the SSH tunnel nobody can reach it.

## Connect the FTMO account

Either log in through the VNC screen (File -> Login to Trade Account, tick "Save password"),
or create `/home/mt5/gtb/account.env` (owner `mt5`, mode 600):

```bash
LOGIN=12345678
PASSWORD='your-master-password'
SERVER=FTMO-Demo
```
then `systemctl restart gtb-mt5`. The symbol must be called `XAUUSD` (FTMO's name). If the
broker uses another name, set `Environment=GTB_SYMBOL=...` on the `gtb-mt5` service.

## Settings

`/home/mt5/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Presets/gtb_live.set` is generated from
`gtb_live.set` in this folder by `03_setup_services.sh`. Before a challenge set at least:

- `InpInitialBalance` = the account's starting balance (e.g. `100000`)
- `InpChallengeMode=true`, `InpChallengeStart` = the challenge's first day (server time, `YYYY.MM.DD 00:00`)

Re-run `03_setup_services.sh` (or edit the preset as UTF-16) and `systemctl restart gtb-mt5`.
The EA remembers trading days, the day's start equity and whether the target was reached across
restarts (MT5 global variables). For a **new** account, delete them first:
`systemctl stop gtb-mt5; rm -f "/home/mt5/.wine/drive_c/Program Files/MetaTrader 5/MQL5/Files/"*gvariables* 2>/dev/null` (or remove the `GTB_*` globals in MT5, F3).

## Telegram

`/etc/gtb/telegram.env` (mode 640, group mt5):
```
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```
then `systemctl restart gtb-notifier`.

## Regime filter

The EA runs every signal on paper as well (all sessions, no risk limits). When those paper trades
lost money over the last 60 days (`InpRegimeDays`), it is in a **bad regime** and only takes new
entries during the New York session (08:00-17:00 New York); otherwise it trades every session.
Telegram announces each switch (`REGIME ...`), and `gtb-status` shows `regime=`, `regime_paper_r=`
and `history_ready=`. On a fresh MT5 the EA first downloads enough history (daily bars for the
200-day EMA, hourly bars for the replay); if that is still missing after 10 minutes you get a warning.
4 years of FTMO data: same profit, worst drawdown 24R -> 13R, and a challenge started in a ranging
market got stuck at the loss limit 3% of the time instead of 22%.

## Nasdaq companion (US100.cash, added 2026-09-27)

A second portable MT5 (`/home/mt5/.wine/drive_c/Program Files/MetaTrader 5 NQ`, service `gtb-mt5-nq`, script
`/home/mt5/gtb/run_mt5_nq.sh`) runs `NasdaqORB` on US100.cash M15 with the same account (`account.env`).
Strategy: the 09:30-09:45 New York candle sets the direction; entry at 09:45, stop at the candle's other side
(at least 0.3 x cash-session ATR), exit 15:55 New York; no trade on US holidays / early-close days.
Since 2026-09-27 (v2) it trades **every day at 0.75x the gold EA's risk** (`InpGate=0`, `InpRiskMult=0.75`): its edge
does not depend on gold's regime (weekly correlation with gold -0.06), and always-on at 0.75x gave the best challenge
odds (30/60/90 days 31.8/50.2/61.8% vs 28.3/46.8/59.8% gated). **No trade on Fed decision days** (`InpSkipFomc`,
FTMO news rule; those days lost -17R in research) - update `FOMC_DAYS` in the EA each year. `InpGate=1` restores the
old mode (only while the gold EA's heartbeat says BAD). Before an entry it counts the open risk of every position on the account;
the gold EA does the same, so both stay inside the shared 3.5% daily / 7% total guards.
Settings: `nq_live.set` (edit, then `bash 08_deploy_nasdaq.sh` or `systemctl restart gtb-mt5-nq`).
For a paid account set `InpInitialBalance` in BOTH presets (the two terminals do not share global variables).
`gtb-halt` stops both EAs. Its heartbeat: `Common/Files/GoldBreakout/nasdaq_heartbeat.txt` (shown by `gtb-status`).
Research (FTMO data 2021-09..2026-09, MT5 tester, fixed 1%): +126R, PF 1.19, every year positive; challenge sim
2022-23: pass 30/60/90 days 30/51/61% with Nasdaq during gold-BAD vs 14/30/37% gold alone.

## News rule (2026-09-27)

No position from 30 minutes before to 30 minutes after a listed high-impact US release (`InpNewsBeforeMin=30`,
`InpNewsAfterMin=30` in `gtb_live.set`). Tested on FTMO gold data 2021-10..2026-09 with the official BLS/Fed dates
(CPI, jobs report, FOMC): 30/30 gave +122.8R, PF 1.40, max drawdown 27.8% vs +117.6R / 1.38 / 31.3% for the old 75/15.
The Nasdaq EA skips Fed decision days entirely: even flat at 13:30 its Fed-day trades lost (-5R over 41 days; the
full day -18R), and CPI / jobs releases at 08:30 come before its 09:45 entry.

## News list

The EA's built-in list covers 2026 US jobs, CPI and FOMC events. For later dates put one
`YYYY-MM-DD HH:MM` (New York time) per line in
`/home/mt5/.wine/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/GoldBreakout/news.txt`.
The EA warns (Telegram) when every listed event is in the past.

## Files in this folder

| File | Purpose |
|---|---|
| `01_install_packages.sh` | Xvfb, x11vnc, user `mt5` (Wine is replaced by step 4) |
| `02_install_mt5.sh` | virtual display service + MT5 install |
| `03_setup_services.sh` | EA, preset, VNC password, the services |
| `04_upgrade_wine.sh` | WineHQ stable (MT5 refuses to support Wine 9) |
| `05_restart_mt5.sh` | finish the Wine prefix update without Mono/Gecko, restart |
| `06_deploy_ea.sh` | update the EA + `gtb-halt` / `gtb-resume` / `gtb-status` |
| `run_mt5.sh`, `notifier.py`, `gtb_live.set`, `check_status.sh` | runtime files |
