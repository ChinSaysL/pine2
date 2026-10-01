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
the gold EA does the same, so both stay inside the shared 2.5% daily / 8% total guards (see Account guards).
Settings: `nq_live.set` (edit, then `bash 08_deploy_nasdaq.sh` or `systemctl restart gtb-mt5-nq`).
For a paid account set `InpInitialBalance` in BOTH presets (the two terminals do not share global variables).
`gtb-halt` stops both EAs. Its heartbeat: `Common/Files/GoldBreakout/nasdaq_heartbeat.txt` (shown by `gtb-status`).
Research (FTMO data 2021-09..2026-09, MT5 tester, fixed 1%): +126R, PF 1.19, every year positive; challenge sim
2022-23: pass 30/60/90 days 30/51/61% with Nasdaq during gold-BAD vs 14/30/37% gold alone.

Since 2026-09-27 (v3) the Nasdaq EA also runs a **noise-area engine** (`InpNoiseEngine`, `InpNoiseRiskMult=0.75`;
Zarattini, Barbon & Aziz 2024): every half hour from 10:00 to 15:00 NY, a close outside the day's noise band (09:30
open / previous close +- the average move at that time over the last 14 sessions) opens one trade that day, hard stop
at the band or VWAP (>= 0.3 x cash ATR), closed when price is back inside the band / across the VWAP, or at 15:55.
FTMO tester 2021-09..2026-09 (fixed 1%): opening trade 1211 trades +143.3R, noise engine 697 trades +49.2R PF 1.23
(positive 2021-2025, -3.2R in 2026). Stop-and-reverse is built in but off (`InpReverseOnce=false`; it lost in 2026).
The opening trade skips indecisive openings (`InpMinBodyFrac=0.2`: 09:30-09:45 candle body < 20% of its range) -
the weakest trades in every period (-17.8R in 2026 alone). FTMO tester: 967 opening trades +155.4R PF 1.33 (2026 +13.3R,
was +5.2R); skipped days show on Telegram as SKIP.

## Afternoon break-even (2026-10-01, Nasdaq EA only)

`InpBeAfterHour=13`, `InpBeAfterMinR=0.5`, `InpBeBufferR=0.015`: from 13:00 New York time, any of our
positions still in profit by at least +0.5R gets its stop moved to the entry (+ a 0.015R buffer for costs).
It came out of the real challenge trades of 2026-09-29/30, where the opening-range trade was +1.13R
(+108 USD) at 11:50 NY and closed at 15:55 at -48 USD. Measured on FTMO US100.cash M5 2021-09..2026-09
(both engines, same cost model as the research):

| exit | opening range | noise | both together |
|---|---|---|---|
| session exit 15:55 (old) | +105.1R, PF 1.16 | +31.3R | +136.3R, PF 1.15 |
| **afternoon break-even** | **+114.3R, PF 1.18** | **+33.0R** | **+147.4R, PF 1.18** |
| break-even at +0.5R (any time) | +59.2R | +25.9R | +85.2R |
| trail 0.5R after +1R | +54.7R | +35.4R | +90.1R |
| take profit +1R | -35.2R | -5.2R | -40.3R |

It touches 136 of 1245 opening-range trades (10.9%): 80 better, 56 worse, positive in 2021-2025 and
-1.3R in 2026. Everything else that protects winners unconditionally costs 20-90R over the years - that
is why the EA still lets the big days run. `InpBeAfterHour=0` restores the old behaviour exactly.
Code: `mt5/NasdaqORB.mq5` (`BeAfterHours()`, called from OnTick and OnTimer), preset `nq_live.set`.

## Account guards (2026-09-27, both EAs - keep them equal)

`InpTotalLimitPct=8.0`, `InpDailyLimitPct=2.5` in `gtb_live.set` and `nq_live.set` (FTMO: 10% / 5%). With three engines
able to stop out on the same day, the old 7% / 3.5% breached FTMO's daily limit in 1.9% of simulated challenges under an
extreme stress (+1R extra slippage on every stop); 8% / 2.5% never breached, passed about as often
(31.7/51.6/63.1% in 30/60/90 days vs 32.9/50.8/61.7%) and got stuck at the guard less often (3.7% vs 6.3%).

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

## Testing the EAs before going live

`bash 09_test_ea_execution.sh` runs the deployed EAs + presets through the MT5 Strategy Tester in
a **private copy of the Wine prefix** (`/home/mt5/.wine-test`), so the live terminal, its
`Common\Files` (events.log, heartbeat, halt.flag, tester CSVs) and its global variables are never
touched - verified with `md5sum -c` at the end of every run. The MT5 tester needs an account
selected, so the rig terminal logs into the same demo account for a few minutes; the live session
is not disturbed (checked in the live terminal journal).

```bash
bash 09_test_ea_execution.sh                        # 2026.05.01 .. today, model 1
bash 09_test_ea_execution.sh 2026.08.01 2026.09.26 1
bash 09_test_ea_execution.sh --cleanup              # drop an old rig first
bash rig_cleanup.sh                                 # remove the rig (~3.5 GB), keep the results
```
Report: `/root/gtb_test_results/execution_test.log` plus one `tester_trades.csv` per EA
(entry/exit in New York time, direction, lots, P/L, risk in USD and R, exit reason).
The 2026-09-28 run is written up in `test_results/README.md`.

## Gold: was the 2026-10-01 entry avoidable? (entry-filter experiment)

The 2026-10-01 trade (live `events.log`) was a textbook **liquidity sweep**: at 20:00-20:16 New
York (00:00-00:16 UTC, the thin Asian session) the H1 bar wicked from 4155.81 down to **4139.11**,
i.e. 8.3 points (0.63 x ATR) *below* the 24h low 4147.40, then closed back at 4145.09. The sell stop
(24h low - 0.05 ATR = 4146.67) filled, the trade was never better than **+0.29R**, and price then
reversed through the 2-ATR stop (4173.14, -$53 = -0.53% at half risk) and on to 4192.71 (+1.74R).

Every candidate filter was priced on the EA's own 2010-2026 trade history (2,489 trades, +265R):

| Candidate | Skips this trade? | Long-run evidence | Verdict |
|---|---|---|---|
| No entries in the Asian window 19:00-01:00 NY (or `InpBadMode=0`) | yes | that window made **+91R of +265R** at PF 1.30 vs 1.25 elsewhere (674 trades, every hour 19-01 net positive) | reject - costs a third of the profit |
| `InpAdxMin=20` (daily ADX was 19.77) | yes | the 601 trades below ADX 20 made **+14R** net; bands are not monotonic (20-22 +16R, 22-25 -9R) | reject - curve fit |
| Bigger `InpBufAtr` | only >= 0.63 ATR (12.6x the live 0.05) | 5-year tester sweep of 0.15/0.30/0.60 in `gold_filters.log` | reject - 0.60 still takes the trade |
| `InpEmaSepPct=1.0` | no (already -3.16% from the 200-EMA) | - | no effect |
| Wait for the H1 close beyond the level | no (it closed 2.3 pts beyond) | - | does not fix sweeps |
| Wider stop `InpStopAtr=3` | no (adverse excursion 1.74R) | - | only a bigger loss |
| BE / trail / TP exits | no (peak was +0.29R) | unconditional winner protection costs 20-90R (Nasdaq study) | nothing to protect |

**Decision: keep the gold entry logic unchanged.** The sweep was 0.63 ATR deep - smaller than the
2-ATR stop - so any filter that removes it also removes a large share of legitimate breakouts
(17% of the EA's trades never ran past +0.29R). Position sizing already halved the damage.

Tools: `research/gold_today.py` (reconstructs the trade from live bars), `research/gold_daily_ctx.py`
(ADX / EMA / 50-day context at the entry), `research/gold_hours.py` (R by entry hour, 2010-2026),
`research/gold_adx_filter.py` (R by daily-ADX band), `vps/12_gold_entry_filters.sh` (tester A/B of the
filter variants on the isolated rig), `vps/13_gold_day_check.sh` (single-day replay),
`vps/gold_wait.sh` (collects the Phase B table into `/root/gtb_test_results/gold_final.txt`).

## Gold: minimum close penetration rule (experiment)

Follow-up to the sweep question above: instead of *skipping* breakouts, require the bar that breaks
the 24h channel to also **close** beyond it before the breakout order is allowed to be armed.

Implementation (`research/ea/GTBClosePen.mq5`, generated from the deployed source by
`research/make_gtb_pen.py`; the deployed EA is untouched):

* new input `InpCloseMinAtr` (default `-1` = off = byte-identical live behaviour);
* in `OnBarClose()` (live path) and `PaperStep()` (paper/regime engine) each side is gated with
  `close(bar 1) >= channelHigh(bars 2..N) + InpCloseMinAtr x ATR` (long) /
  `close(bar 1) <= channelLow(bars 2..N) - InpCloseMinAtr x ATR` (short).
* the reference channel **excludes the bar that just closed** - including it makes the test
  degenerate, because that bar's own extreme *is* the channel edge, so its close can never be
  beyond it (measured: 128 -> 2 trades, i.e. the filter would switch the strategy off).

Runner: `research/run_cc_year.ps1` (one-year windows, local Strategy Tester) and
`research/cc_compare2.py` (pooling, per year, removed trades, and whether the 2026-09-30 sweep
trade is still taken). Test profile: fixed 1% risk, limits 50%/50%, fresh magic per run.

### Tester caveats found while running this (worth knowing)

* A **fresh test started at the initial balance trips the 2.5%/5% FTMO guards** in the first
  months and then stops for good (`g_limitStop` is persisted in a global variable), which
  truncates the run. Hence the fixed-1%/50%-50% research profile and one fresh magic per run.
* **Long tester runs go silent**: the deployed EA keeps trading normally, then stops opening
  positions after ~2.5-4 simulated years with no error in the journal (verified against MT5's own
  report, not just the EA's CSV export). It is a tester-side effect (the exports before that point
  are complete), so the A/B runs on one-year windows.
* The EA's tester export (`tester_trades.csv`) comes from an in-memory registry, so a run that is
  copied before the terminal really exits yields a short file - the runners now wait for the
  terminal to disappear and print the exported first/last trade date as a coverage check.

### Result: rejected (2026-10-01)

Local Strategy Tester, one-year windows, fixed 1% risk, limits 50/50, the deployed EA vs the same EA
with `InpCloseMinAtr` (gate = the bar that breaks the channel must also close beyond the level,
measured against the channel *without* that bar):

| year | live (rule off) | close >= +0.15 ATR | close >= +0.25 ATR |
|---|---|---|---|
| 2021 | -40.4R (128) | -17.6R (43) | -16.8R (40) |
| 2022 | -21.1R (212) | +3.2R (73) | +11.3R (66) |
| 2023 | +7.8R (151) | +1.3R (70) | +3.4R (64) |
| 2024 | +20.2R (159) | +3.0R (77) | +2.3R (71) |
| 2025 | +81.4R (224) | +40.6R (142) | +36.6R (131) |
| 2026 (to 09-18) | +34.5R (117) | +9.3R (63) | +7.9R (54) |
| **total** | **+82.6R, 991 trades, PF 1.21** | **+39.8R, 468 trades, PF 1.23** | **+44.8R, 426 trades, PF 1.27** |

The gate halves the number of trades (and, in the extreme, a plain "close beyond the level" leaves
~nothing to trade) while the total falls by about half. Profit factor and R per trade barely move
(1.21 -> 1.23/1.27, +0.083R -> +0.085/+0.105R per trade): it is roughly **the same strategy executed
half as often**, not a better strategy. It saves money in the two losing years and gives back much
more in the four winning ones, exactly like every other entry filter tested here.

Today's trade would have been skipped by it (at 20:00 New York the previous bar closed at 4152.60,
above the older channel low 4147.40, so no sell order would have been armed), but that is not worth
~40R of 6-year profit.

**Verdict: keep the gold entry logic as is.** Files: `research/ea/GTBClosePen.mq5`,
`research/make_gtb_pen.py`, `research/run_cc_year.ps1`, `research/cc_compare2.py`,
per-run exports `research/cc_y<year>_<variant>.csv`.

## Files in this folder

| File | Purpose |
|---|---|
| `01_install_packages.sh` | Xvfb, x11vnc, user `mt5` (Wine is replaced by step 4) |
| `02_install_mt5.sh` | virtual display service + MT5 install |
| `03_setup_services.sh` | EA, preset, VNC password, the services |
| `04_upgrade_wine.sh` | WineHQ stable (MT5 refuses to support Wine 9) |
| `05_restart_mt5.sh` | finish the Wine prefix update without Mono/Gecko, restart |
| `06_deploy_ea.sh` | update the EA + `gtb-halt` / `gtb-resume` / `gtb-status` |
| `09_test_ea_execution.sh` | run the deployed EAs through the MT5 tester in an isolated prefix copy |
| `rig_cleanup.sh` | remove that test rig again (keeps `/root/gtb_test_results`) |
| `test_results/` | the 2026-09-28 execution test: report + tester trade exports |
| `run_mt5.sh`, `notifier.py`, `gtb_live.set`, `check_status.sh` | runtime files |
