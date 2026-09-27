"""New York opening-range breakout on any timeframe (bars must align to the hour)."""
import numpy as np
import pandas as pd

COST_OZ = 0.30


def orb(df, allowed, start=8.0, range_h=2.0, tgt_r=2.0, slip_atr=0.0, last_entry=16.0, exit_h=16 + 50 / 60, cost=COST_OZ):
    o, h, l, c, atr = df.o.values, df.h.values, df.l.values, df.c.values, df.atr.values
    ny_h = df.ny_h.values; tday = df.tday.values; tf = df.tf_h.values[0]
    trades = []; n = len(df); i = 0
    while i < n:
        if ny_h[i] != start or not allowed[i]:
            i += 1; continue
        k = int(round(range_h / tf))
        if i + k >= n or tday[i + k - 1] != tday[i] or ny_h[i + k - 1] != start + range_h - tf:
            i += 1; continue
        rh, rl = h[i:i + k].max(), l[i:i + k].min()
        j = i + k; pos = None
        while j < n and tday[j] == tday[i]:
            if pos is None:
                if ny_h[j] >= last_entry: break
                up, dn = h[j] >= rh, l[j] <= rl
                if up and dn: break
                if up or dn:
                    d = 1 if up else -1
                    e = (max(o[j], rh) + slip_atr * atr[j]) if d == 1 else (min(o[j], rl) - slip_atr * atr[j])
                    st = rl if d == 1 else rh
                    risk = abs(e - st)
                    pos = dict(dir=d, entry=e, stop=st, tgt=(e + d * tgt_r * risk) if tgt_r else None, risk=risk, i=j)
                    if (d == 1 and c[j] <= st) or (d == -1 and c[j] >= st):
                        px = st; pos["x"] = j
                        trades.append(dict(entry_time=df.time.iloc[j], exit_time=df.time.iloc[j], dir=d, risk=risk,
                                           r=((px - e) * d - cost) / risk)); break
            else:
                d = pos["dir"]; px = None
                if (d == 1 and l[j] <= pos["stop"]) or (d == -1 and h[j] >= pos["stop"]):
                    px = min(o[j], pos["stop"]) if d == 1 else max(o[j], pos["stop"])
                elif pos["tgt"] is not None and ((d == 1 and h[j] >= pos["tgt"]) or (d == -1 and l[j] <= pos["tgt"])):
                    px = max(o[j], pos["tgt"]) if d == 1 else min(o[j], pos["tgt"])
                elif ny_h[j] + tf > exit_h:
                    px = c[j] if ny_h[j] + tf <= 17 else o[j]
                if px is not None:
                    trades.append(dict(entry_time=df.time.iloc[pos["i"]], exit_time=df.time.iloc[j], dir=d,
                                       risk=pos["risk"], r=((px - pos["entry"]) * d - cost) / pos["risk"])); break
            j += 1
        i = j + 1
    return pd.DataFrame(trades)
