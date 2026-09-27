import pandas as pd, numpy as np, warnings
warnings.filterwarnings("ignore")
from regime import load_mt5, paper_trades, regime_flag, trend_array
from pyramid import simulate_pyr
from range_concepts import run, summary, COST_OZ
df = load_mt5("H1")
paper = paper_trades(df)
bad = regime_flag(df, paper)
ti = df.set_index("time").index
def at(ts): return ti.get_indexer(pd.DatetimeIndex(ts))
rows = []
# --- baseline: live EA behaviour in BAD windows (NY 08-17 entries only), per unit
p = paper.copy(); ei = at(p.entry_time); nyh = df.ny_h.values[ei]
rows.append(summary(p[bad[ei] & (nyh >= 8) & (nyh < 17)], "BASE live EA in BAD (NY only)"))
rows.append(summary(p[bad[ei]], "BASE trend all-session in BAD"))
rows.append(summary(p[~bad[ei]], "BASE trend in GOOD"))
# --- C3: breakout with no daily trend filter
c3 = simulate_pyr(df, hours=24, stop_atr=2.0, trail_atr=3.0, trend=None, add_at=(1.0,), flat_ny=16 + 50 / 60)
ei = at(c3.entry_time); nyh = df.ny_h.values[ei]
rows.append(summary(c3[bad[ei]], "C3 no-trend BO | BAD"))
rows.append(summary(c3[bad[ei] & (nyh >= 8) & (nyh < 17)], "C3 no-trend BO | BAD NY"))
rows.append(summary(c3[~bad[ei]], "C3 no-trend BO | GOOD"))

# --- C4: daily RSI(2) swing reversion, entries 20:00 NY, exits at the 16:00 NY bar close, flat Friday
def c4(df, allowed):
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    d = df.groupby("tday").agg(c=("c", "last"), h=("h", "max"), l=("l", "min"))
    delta = d.c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean(); dn = (-delta.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + up / dn)
    d["sma5"] = d.c.rolling(5).mean()
    tr = np.maximum(d.h - d.l, np.maximum((d.h - d.c.shift()).abs(), (d.l - d.c.shift()).abs()))
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    prev = d.shift(1)   # values known at the start of each trading day
    ny_h = df.ny_h.values; wd = df.time.dt.tz_convert("America/New_York").dt.weekday.values
    tday = df.tday.values
    trades, pos = [], None
    for i in range(1, len(df)):
        td = tday[i]
        if pos is not None:
            dd = pos["dir"]; px = None
            if (dd == 1 and l[i] <= pos["stop"]) or (dd == -1 and h[i] >= pos["stop"]):
                px = min(o[i], pos["stop"]) if dd == 1 else max(o[i], pos["stop"])
            elif ny_h[i] == 16.0:   # bar 16:00-17:00 NY: decide on the close proxy = this bar's open (~16:00)
                sma5 = prev.sma5.get(td)
                done = (dd == 1 and o[i] > sma5) or (dd == -1 and o[i] < sma5) or (td - pos["day"]).days >= 7 or wd[i] == 4
                if done: px = o[i]
            if px is not None:
                trades.append(dict(entry_time=df.time.iloc[pos["i"]], exit_time=df.time.iloc[i], dir=dd,
                                   r=((px - pos["entry"]) * dd - COST_OZ) / pos["risk"])); pos = None
        if pos is None and ny_h[i] == 20.0 and wd[i] != 4 and allowed[i] and td in prev.index:
            pr = prev.loc[td]
            if np.isnan(pr.rsi) or np.isnan(pr.atr): continue
            dd = 1 if pr.rsi < 10 else (-1 if pr.rsi > 90 else 0)
            if dd:
                stop = o[i] - dd * 2 * pr.atr
                pos = dict(dir=dd, entry=o[i], stop=stop, risk=2 * pr.atr, i=i, day=td)
    return pd.DataFrame(trades)
rows.append(summary(c4(df, bad), "C4 daily RSI2 swing | BAD"))
rows.append(summary(c4(df, ~bad), "C4 daily RSI2 swing | GOOD"))

# --- C6: NY opening range (08:00-10:00 NY) breakout, stop at other side, 2R target, flat 16:50
def c6(df, allowed):
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    ny_h = df.ny_h.values; tday = df.tday.values
    trades = []; i = 0; n = len(df)
    while i < n - 3:
        if ny_h[i] == 8.0 and ny_h[i + 1] == 9.0 and allowed[i + 1]:
            rh, rl = max(h[i], h[i + 1]), min(l[i], l[i + 1]); j = i + 2; pos = None
            while j < n and tday[j] == tday[i] and ny_h[j] < 17:
                if pos is None:
                    if ny_h[j] >= 16: break
                    up, dnn = h[j] >= rh, l[j] <= rl
                    if up or dnn:
                        dd = 1 if up and not dnn else (-1 if dnn and not up else 0)
                        if dd == 0: break      # both sides in one bar: skip (unknown order)
                        e = max(o[j], rh) if dd == 1 else min(o[j], rl); st = rl if dd == 1 else rh
                        risk = abs(e - st); pos = dict(dir=dd, entry=e, stop=st, tgt=e + dd * 2 * risk, risk=risk, i=j)
                        if (dd == 1 and c[j] <= st) or (dd == -1 and c[j] >= st):
                            trades.append(dict(entry_time=df.time.iloc[j], r=((st - e) * dd - COST_OZ) / risk)); break
                        j += 1; continue
                else:
                    dd = pos["dir"]; px = None
                    if (dd == 1 and l[j] <= pos["stop"]) or (dd == -1 and h[j] >= pos["stop"]): px = pos["stop"]
                    elif (dd == 1 and h[j] >= pos["tgt"]) or (dd == -1 and l[j] <= pos["tgt"]): px = pos["tgt"]
                    elif ny_h[j] == 16.0: px = c[j] if False else o[j]
                    if px is not None:
                        trades.append(dict(entry_time=df.time.iloc[pos["i"]], r=((px - pos["entry"]) * dd - COST_OZ) / pos["risk"])); break
                j += 1
            i = j
        i += 1
    return pd.DataFrame(trades)
rows.append(summary(c6(df, bad), "C6 NY ORB | BAD"))
rows.append(summary(c6(df, ~bad), "C6 NY ORB | GOOD"))
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).to_string(index=False))
