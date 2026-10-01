"""Why are gold's recent months flat? Every gold trade (Python replica of the live EA, H1 2010-2026), R by feature
bucket and era; plus what the neutral trend band costs (hypothetical trades while neutral). Only causes that also
hurt in earlier eras count as fixes."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pyramid import simulate_pyr
from regime import regime_flag
from oldgold import load_full

g = load_full("XAUUSD", "data/XAUUSD_H1.csv")
closes = g.groupby("tday").c.last()
sma = closes.rolling(50).mean(); ema = closes.ewm(span=200, adjust=False).mean()
dist = ((closes - sma) / sma * 100).shift(1)                        # yesterday's close vs its 50d SMA, %
raw = pd.Series(np.where(closes > sma * 1.01, 1, np.where(closes < sma * 0.99, -1, 0)), index=closes.index)
ok = np.where(raw == 1, closes > ema, np.where(raw == -1, closes < ema, False))
trend = pd.Series(np.where(ok & (np.arange(len(closes)) >= 100), raw, 0), index=closes.index).shift(1)
neutral_reason = pd.Series(np.where(raw == 0, "inside 1% band", np.where(~ok, "wrong side of EMA200", "trend")), index=closes.index).shift(1)
tr_arr = g.tday.map(trend).fillna(0).values

t = simulate_pyr(g, hours=24, stop_atr=2.0, trail_atr=3.0, trend=tr_arr, add_at=(1.0,), flat_ny=16 + 50 / 60)
bad = regime_flag(g, t)
ei = g.set_index("time").index.get_indexer(pd.DatetimeIndex(t.entry_time))
t["bad"] = bad[ei]
t["w"] = np.where(t.bad, 0.5, 1.0); t["wr"] = t.r * t.w                # live: BAD units at half risk
t["tday"] = g.tday.values[ei]
t["dist"] = t.tday.map(dist).abs()
t["ny_h"] = g.ny_h.values[ei]
t["session"] = np.select([(t.ny_h >= 8) & (t.ny_h < 17), (t.ny_h >= 3) & (t.ny_h < 8)], ["New York", "London"], "Asia")
hh = pd.Series(g.h.values).rolling(24).max().values; ll = pd.Series(g.l.values).rolling(24).min().values
t["chan_atr"] = (hh[ei - 1] - ll[ei - 1]) / g.atr.values[ei - 1]
d = g.groupby("tday").agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
datr = (np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))).ewm(alpha=1 / 14, adjust=False).mean()
volp = (datr / d.c * 100); vrank = volp.rolling(250, min_periods=60).apply(lambda s: (s.iloc[-1] >= s).mean(), raw=False).shift(1)
t["vol_rank"] = t.tday.map(vrank)
t["unit"] = np.where(t.unit == 0, "first", "add")
t["era"] = pd.cut(t.entry_time.dt.year, [2009, 2014, 2019, 2023, 2025, 2026], labels=["2010-14", "2015-19", "2020-23", "2024-25", "2026"])
t.to_pickle("gold_diag.pkl")
pd.set_option("display.width", 250)


def table(col, bins=None, labels=None):
    x = t.copy()
    if bins is not None: x[col] = pd.cut(x[col], bins, labels=labels)
    print(f"\n=== {col}: avg R per unit (live weighting)")
    print(x.groupby([col, "era"]).wr.mean().unstack("era").round(3).to_string())
    print("    total R:"); print(x.groupby([col, "era"]).wr.sum().unstack("era").round(1).to_string())


print("ERA totals (live weighting):", t.groupby("era").wr.agg(["mean", "count", "sum"]).round(2).to_dict("index"))
t26 = t[t.entry_time >= "2026-01-01"]
print("\n2026 by month (R):", t26.groupby(t26.entry_time.dt.month).wr.sum().round(1).to_dict(), "| units per month:", t26.groupby(t26.entry_time.dt.month).size().to_dict())
table("session")
table("unit")
table("dist", [0, 2, 4, 7, 100], ["1-2% from SMA50", "2-4%", "4-7%", ">7%"])
table("chan_atr", [0, 4, 6, 9, 100], ["24h range <4 ATR", "4-6", "6-9", ">9"])
table("vol_rank", [0, .25, .5, .75, 1.01], ["vol low", "vol mid-low", "vol mid-high", "vol high"])
table("dir")
table("bad")

# the neutral periods: share of days neutral per year, and what trading them would have made
days = pd.DataFrame({"trend": trend, "why": neutral_reason}).dropna()
days["y"] = [x.year for x in days.index]
print("\nShare of trading days with NO gold trend (no trades allowed), by year:")
print(days.groupby("y").trend.apply(lambda s: (s == 0).mean()).round(2).to_dict())
print("2026 no-trade days by reason:", days[days.y == 2026].why.value_counts().to_dict())
both = simulate_pyr(g, hours=24, stop_atr=2.0, trail_atr=3.0, trend=None, add_at=(1.0,), flat_ny=16 + 50 / 60)
bi = g.set_index("time").index.get_indexer(pd.DatetimeIndex(both.entry_time))
both["neutral"] = tr_arr[bi] == 0
both["long"] = both.dir == 1
both["era"] = pd.cut(both.entry_time.dt.year, [2009, 2014, 2019, 2023, 2025, 2026], labels=["2010-14", "2015-19", "2020-23", "2024-25", "2026"])
nb = both[both.neutral]
print("\nHYPOTHETICAL trades on NEUTRAL days (both directions allowed), R by era:")
print(nb.groupby(["era", "long"]).r.agg(["count", "sum", "mean"]).round(2).unstack("long").to_string())
