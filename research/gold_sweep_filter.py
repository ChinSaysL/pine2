"""Cost of the natural 'sweep filter': require the break to extend further before entering.

For every real EA trade (2020-2026) we measure the trade's maximum favourable excursion (MFE, in R)
from the actual H1 path. Requiring the break to run >= X R before entry (equivalently a bigger
breakout buffer, ~2X ATR) removes every trade whose MFE never reached X - we price that trade-off.
"""
import pandas as pd
import numpy as np

H = pd.read_csv(r"c:\Users\Abdo\Downloads\pine2\research\data\XAUUSD_H1.csv", parse_dates=["utc"])
H = H.sort_values("utc").reset_index(drop=True)
print("H1 bars", len(H), H.utc.min(), "->", H.utc.max())

t = pd.read_csv(r"c:\Users\Abdo\Downloads\pine2\research\mt5_bm_halfrisk.csv", sep=";")
t["et"] = pd.to_datetime(t.entry_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
t["xt"] = pd.to_datetime(t.exit_time_ny, format="%Y.%m.%d %H:%M", errors="coerce")
t = t.dropna(subset=["et", "xt"])
t["et"] = t.et.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
t["xt"] = t.xt.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
t = t.dropna(subset=["et", "xt"])
t = t[(t.et >= H.utc.min()) & (t.xt <= H.utc.max())].reset_index(drop=True)
# the EA's R = entry to initial stop, recoverable from risk over lots (0.01 lot = 1 oz per 100 pts? -> use price)
t["dist"] = (t.risk_usd / (t.lots * 100)).abs()          # stop distance in dollars/oz (risk_usd = lots*100*dist)
t["atr"] = t.dist / 2.0                                   # InpStopAtr = 2
utc = H.utc.values
print(f"trades usable: {len(t)}  ({t.et.min():%Y-%m-%d} .. {t.et.max():%Y-%m-%d})")

mfe, mae = [], []
hi, lo = H.high.values, H.low.values
for r in t.itertuples():
    a = np.searchsorted(utc, np.datetime64(r.et.astimezone(tz=None).replace(tzinfo=None)))
    b = np.searchsorted(utc, np.datetime64(r.xt.astimezone(tz=None).replace(tzinfo=None)))
    a, b = max(a - 1, 0), min(b + 1, len(H) - 1)
    if b <= a:
        mfe.append(np.nan); mae.append(np.nan); continue
    hh, ll = hi[a:b].max(), lo[a:b].min()
    if r.dir == "sell":
        mfe.append((r.entry - ll) / r.dist); mae.append((hh - r.entry) / r.dist)
    else:
        mfe.append((hh - r.entry) / r.dist); mae.append((r.entry - ll) / r.dist)
t["mfe"] = mfe
t["mae"] = mae
t = t.dropna(subset=["mfe"])
t["mfe_atr"] = t.mfe * 2          # MFE expressed in ATR units (R = 2 ATR)
print(f"\nMFE (R) distribution of the {len(t)} trades:")
print(t.mfe.describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_string())
print(f"\nshare of trades whose best moment was under today's +0.29R: {(t.mfe < 0.29).mean():.0%}")
print("\ntrade-off of 'wait for the break to extend to X R before entering'")
print(f"{'X (R)':>6} {'~buffer ATR':>11} {'trades kept':>11} {'kept R':>8} {'removed':>8} {'removed R':>10} {'PF kept':>8}")
base = t.r.sum()
for x in (0.05, 0.10, 0.20, 0.29, 0.40, 0.60, 1.00):
    keep = t[t.mfe >= x]; drop = t[t.mfe < x]
    pf = keep.r[keep.r > 0].sum() / max(-keep.r[keep.r < 0].sum(), 1e-9)
    print(f"{x:6.2f} {0.05 + 2 * x:11.2f} {len(keep):11d} {keep.r.sum():+8.1f} {len(drop):8d} {drop.r.sum():+10.1f} {pf:8.2f}")
print(f"\nbaseline: {len(t)} trades  {base:+.1f}R")
t.to_csv(r"c:\Users\Abdo\Downloads\pine2\research\gold_mfe.csv", index=False)
