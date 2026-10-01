"""Ex-ante market selection: no hindsight picking of symbols.
R1: universe sum of each market's trades taken only while its OWN regime is GOOD (paper 60d R >= 0).
R2: top-k rotation: at each trade's entry, the market must rank in the top k of all markets by trailing
    60-day paper R of the same strategy (computed from trades closed before the entry)."""
import numpy as np, pandas as pd
P = [("dev", "2020-01-01", "2022-07-01"), ("holdA", "2022-07-01", "2024-07-01"), ("holdB", "2024-07-01", "2026-10-01")]
t = pd.read_pickle("multi_trades.pkl")
t = t[t.sym != "XAGUSD"]          # silver already rejected (moves with gold)
t["entry_time"] = pd.to_datetime(t.entry_time, utc=True); t["exit_time"] = pd.to_datetime(t.exit_time, utc=True)
def rep(x, label):
    out = [label]
    for p, a, b in P:
        s = x[(x.entry_time >= a) & (x.entry_time < b)]
        pf = s.r[s.r > 0].sum() / max(-s.r[s.r < 0].sum(), 1e-9)
        out.append(f"{s.r.sum():+7.1f}R n={len(s):5d} PF={pf:4.2f}")
    print(" | ".join(out))
for strat, g in t.groupby("strat"):
    print("==", strat)
    rep(g[g.gbad], "universe, gold BAD, no selection        ")
    rep(g[g.gbad & ~g.obad], "universe, gold BAD, own regime GOOD     ")
    # trailing 60d paper R per symbol at each entry
    syms = sorted(g.sym.unique())
    ex = {s: g[g.sym == s].sort_values("exit_time") for s in syms}
    cum = {s: (ex[s].exit_time.values.astype("datetime64[ns]"), np.r_[0, np.cumsum(ex[s].r.values)]) for s in syms}
    def trailing(s, ts):
        et, c = cum[s]; ts = np.datetime64(ts.tz_convert(None))
        hi = np.searchsorted(et, ts); lo = np.searchsorted(et, ts - np.timedelta64(60, "D"))
        return c[hi] - c[lo]
    g = g.sort_values("entry_time").copy()
    ranks = []
    for _, row in g.iterrows():
        sc = {s: trailing(s, row.entry_time) for s in syms}
        mine = sc[row.sym]
        ranks.append(1 + sum(v > mine for v in sc.values()))
    g["rank"] = ranks
    for k in (1, 3, 5):
        rep(g[g.gbad & (g["rank"] <= k)], f"universe, gold BAD, top-{k} rotation       ")
    for k in (3, 5):
        rep(g[g["rank"] <= k], f"ALL hours (any gold regime), top-{k}      ")
