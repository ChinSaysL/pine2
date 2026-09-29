# EA execution test - 2026-09-28 (before going live)

Ran the deployed experts and the deployed presets through the MetaTrader 5 Strategy Tester
**on the server**, in a private copy of the Wine prefix, to prove the EAs really execute
(place, modify, close) orders. The live deployment was not modified - see "Isolation proof".

| | |
|---|---|
| When | 2026-09-28 10:00-10:03 UTC |
| Where | Japan VPS, Wine 11.0, MT5 build 6230, `5.104.81.124` |
| Command | `bash 09_test_ea_execution.sh` (step 9, adds nothing to the live setup) |
| Period | 2026.06.01 - 2026.09.26, model 1 (1 minute OHLC), deposit 10 000 USD, leverage 1:100 |
| Inputs | the **deployed** `MQL5/Presets/gtb_live.set` (35 inputs) and `nq_live.set` (29 inputs) |
| Experts | the **deployed** `GoldTrendBreakout.ex5`, `NasdaqORB.ex5` |
| Data | FTMO's own XAUUSD H1 / US100.cash M15 history + real ticks |

## Result: both EAs execute cleanly

| | Gold (XAUUSD H1) | Nasdaq (US100.cash M15) |
|---|---|---|
| Test result | `successfully finished`, exit code 0 | `successfully finished`, exit code 0 |
| Market data | 461 700 ticks, 1 945 bars | 461 340 ticks, 7 772 bars |
| Trades (exported by the EA) | **37** | **104** (66 opening-range + 38 noise engine) |
| `CTrade::OrderSend` calls | 799 | 172 |
| ... returned `[done]` | **799 (100%)** | **172 (100%)** |
| ... errors (invalid stops / volume / filling / no money / rejected) | **0** | **0** |
| Deals actually executed | 74 | 208 |
| Final balance | **11 050.42 USD (+10.5%)** | 10 063.92 USD (+0.6%) |
| Files | `gold_tester_trades.csv`, `gold_tester_paper.csv` | `nq_tester_trades.csv` |

### What the journals prove (Gold)

```
10:00:47  Tester      automatic testing started
          [REGIME] BAD regime - all sessions at 50% risk  ->  risk halved as designed
          [ENTRY] SELL 0.05 lots at 4040.92, stop 4064.70 (GTB Add)
          CTrade::OrderSend: sell stop 0.05 XAUUSD at 4040.92 sl: 4064.70 [done]
          order [#698 sell stop 0.05 XAUUSD at 4040.92] triggered
          deal #73 sell 0.05 XAUUSD at 4040.92 done (based on order #698)
          [ADD] added to short at +1.0R
          position modified [#696 sell 0.05 XAUUSD 4064.70 sl: 4064.70]      <- stop to breakeven
          CTrade::OrderSend: modify position #696 XAUUSD (sl: 4064.70, tp: 0.00) [done]
          [TARGET] Profit target 10.0% reached (10.51%) - trading stopped
          [CLOSE] 0.05 lots at 4029.86, P/L 174.06 USD (Target reached)
          final balance 11050.42 USD
```

So in one run: regime filter, breakout stop order, fill, add-on at +1R, breakeven stop move,
per-trade risk sizing, news/close flats, the 2.5%/8% guards and the challenge target with the
"stop trading once passed" logic all fired and all order calls were accepted by the server.

### What the journals prove (Nasdaq)

```
[ENTRY] NQ ORB BUY 0.78 lots US100 at 30599.43, stop 30480.37 (0.93% risk, cash ATR 396.9)
FILL: BUY 0.78 lots at 30599.43                 <- stop attached to the entry order
stop loss triggered #208 buy 0.78 US100.cash 30599.43 sl: 30480.37
CLOSE: 0.78 lots at 30480.37, P/L -92.87 USD (Stop)          <- exactly -1.000R
CLOSE: 0.77 lots at 30488.33, P/L 151.57 USD (Session exit)   <- 15:55 NY flat
```
Risk per trade starts at 0.93% (0.75 x 1.25% max) and shrinks to ~0.35% after losses - the
scaled-risk model and the shared account guards work as documented.

### Statistics of the exported trades (this window only - not a strategy verdict)

| | Gold (37 trades) | Nasdaq (104 trades) |
|---|---|---|
| Sum / PF / win rate | +10.5R, PF 1.98, 62% | +6.7R, PF 1.15, 40% |
| Best / worst trade | +2.13R / -1.00R | +4.76R / -1.00R |
| Risk per trade | 85-119 USD (0.85-1.19%) | 36-94 USD (0.36-0.94%) |
| Balance path | 9 945 -> peak 11 050 (+10.50%) | 9 990 -> peak 10 600 (+6.00%) -> 9 394 (-6.06%) -> 10 064 |
| Worst day | -1.17% | -1.86% |
| Trades per week | 5.2 | 6.3 |

Every losing stop is exactly -1.00R (no slippage surprises in the fixture) and the deepest point
stays inside the 8% total / 2.5% daily guards for both EAs. Gold's window ends on 2026-07-27
because the challenge target (+10.51%) was reached and the EA then stopped trading, exactly as
designed; the paper CSV keeps going through August/September, which confirms the regime engine
keeps running after the target.

## Isolation proof (the live deployment was untouched)

* live `md5sum` identical before and after the test (`md5sum -c` in the log):
  `GoldTrendBreakout.mq5 dd9c8af9...`, `GoldTrendBreakout.ex5 d81582fb...`,
  `gtb_live.set 95d300a6...`, `nq_live.set e8030a94...`, `NasdaqORB.ex5 cc88d051...`
* `Common/Files/GoldBreakout/events.log` unchanged (mtime 09:36, same size); `heartbeat.txt`
  keeps updating every minute; no `halt.flag`, 0 positions
* the live terminal journal shows **no** disconnect/re-login during the test, so the rig's
  broker login did not disturb the live EA's session
* all five services active afterwards; disk returned to the pre-test 17 G used

How: the rig is a copy of the prefix in `/home/mt5/.wine-test` (`cp -a`, source only read) plus
private portable installs `MetaTrader 5 TEST` / `MetaTrader 5 TEST NQ` inside it - so it has its
own registry, its own `Common\Files`, its own MQL5 folder and its own terminal global variables.
The live EA's `.ex5`/`.mq5`/`.set` were only read to build the tester config.

## Open points found while checking (see the hand-over notes in the chat)

1. **The Nasdaq terminal was frozen since 09:12 UTC** - `nasdaq_heartbeat.txt` stale, its
   `logs/20260928.log` silent since 09:01 ("scanning network"), so that EA was not trading.
   Fix: `systemctl restart gtb-mt5-nq`.
2. `gtb-mt5.service` runs `ExecStopPost=... wineserver -k`, which kills **the whole shared Wine
   prefix** - i.e. it also hits the Nasdaq terminal, because both terminals live in `/home/mt5/.wine`.
3. After some restarts the EA came up on **XAUUSD M1** instead of H1 (`[START] XAUUSD PERIOD_M1`
   at 09:17/09:20/09:24) even though `gtb_start.ini` asks for H1: MT5 restores the saved profile.
   The heartbeat has `period=`, but `notifier.py` does not alert on it.
4. Both terminals install an `llm-agent` MCP bridge that wants port 22346; only the first
   instance gets it (the others log `bind error`). Harmless for trading, but it means the port is
   taken by whichever terminal starts first.
