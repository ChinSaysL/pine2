"""Pull the last bars of XAUUSD (H1 + M15) from the local FTMO terminal and reconstruct
the 2026-10-01 00:16 UTC gold trade (the suspected liquidity sweep)."""
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone

OUT = r"c:\Users\Abdo\Downloads\pine2\research\data"
if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
    raise SystemExit(f"init failed {mt5.last_error()}")
a = mt5.account_info()
print(f"account {a.login} {a.server} balance {a.balance}")
mt5.symbol_select("XAUUSD", True)

frames = {}
for name, tf, n in [("H1", mt5.TIMEFRAME_H1, 3000), ("M15", mt5.TIMEFRAME_M15, 3000)]:
    r = mt5.copy_rates_from_pos("XAUUSD", tf, 0, n)
    if r is None or not len(r):
        print(name, "no data", mt5.last_error()); continue
    df = pd.DataFrame(r)
    srv = pd.to_datetime(df.time, unit="s")
    ny = (srv - pd.Timedelta(hours=7)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    df["utc"] = ny.dt.tz_convert("UTC")
    df = df.dropna(subset=["utc"])[["utc", "open", "high", "low", "close", "tick_volume", "spread"]]
    df.to_csv(f"{OUT}\\FT_XAUUSD_{name}_recent.csv", index=False)
    frames[name] = df
    print(name, len(df), df.utc.iloc[0], "->", df.utc.iloc[-1])
mt5.shutdown()

# ---- reconstruct the trade: entry 2026-10-01 00:16:47 UTC, SELL 4146.67, stop 4173.14
H = frames["H1"].copy()
H["ny"] = H.utc.dt.tz_convert("America/New_York")
entry_t = pd.Timestamp("2026-10-01 00:16:47", tz="UTC")
entry = 4146.67
stop = 4173.14
R = stop - entry
k = H.index[H.utc <= entry_t][-1]
chan = H.iloc[max(0, k - 24):k]
lo24, hi24 = chan.low.min(), chan.high.max()
print(f"\nentry {entry_t} (NY {entry_t.tz_convert('America/New_York'):%Y-%m-%d %H:%M})  SELL {entry}  stop {stop}  R = {R:.2f} pts")
print(f"previous 24 H1 bars: low {lo24:.2f}  high {hi24:.2f}   -> trigger = low - 0.05 ATR")
print(f"bar in which the stop order filled: {H.utc[k]}  (NY {H.ny[k]:%H:%M})  o {H.open[k]:.2f} h {H.high[k]:.2f} l {H.low[k]:.2f} c {H.close[k]:.2f}")

walk = H.iloc[k:k + 12]
print("\nprice after the fill (R = risk multiples vs the short entry)")
for b in walk.itertuples():
    best = (entry - b.low) / R
    worst = (b.high - entry) / R
    print(f"  {b.utc:%m-%d %H:%M} UTC (NY {b.ny:%H:%M})  o {b.open:8.2f} h {b.high:8.2f} l {b.low:8.2f} c {b.close:8.2f}   "
          f"close {(b.close - entry) / R:+.2f}R   best +{best:.2f}R   adverse -{worst:.2f}R")

M = frames["M15"].copy()
M["ny"] = M.utc.dt.tz_convert("America/New_York")
w = M[(M.utc >= entry_t - pd.Timedelta(minutes=90)) & (M.utc <= entry_t + pd.Timedelta(hours=5))]
print("\nM15 bars around the entry (the sweep itself)")
for b in w.itertuples():
    tag = "SELL FILL" if (b.utc <= entry_t < b.utc + pd.Timedelta(minutes=15)) else ("STOP" if b.high >= stop and b.utc > entry_t else "")
    print(f"  {b.utc:%m-%d %H:%M} UTC (NY {b.ny:%H:%M})  o {b.open:8.2f} h {b.high:8.2f} l {b.low:8.2f} c {b.close:8.2f}  {tag}")
