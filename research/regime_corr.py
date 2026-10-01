"""How does each strategy depend on gold's regime? Oct 2021 - Sep 2026, R per trade (each trade 1R risk, unweighted).
1) mean R per trade while gold GOOD vs BAD + Welch t-test and bootstrap p-value of the difference
2) weekly R: correlation with gold's weekly R and with the share of the week gold was BAD
3) correlation matrix of weekly R between strategies"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from scipy import stats
from third_combo import gold_bad_at
from usdjpy_lb import lb
from pead import trades as pead_trades, SYMS

START, END = pd.Timestamp("2021-10-01", tz="UTC"), pd.Timestamp("2026-09-20", tz="UTC")
ny = lambda s: pd.to_datetime(s, format="%Y.%m.%d %H:%M").dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")

g = pd.read_csv("mt5_bm_halfrisk.csv", sep=";"); g["entry_time"] = ny(g.entry_time_ny)
g = g.dropna(subset=["entry_time"])[["entry_time", "r"]]
nq = pd.read_csv("mt5_nq_ftmo2.csv", sep=";"); nq["entry_time"] = ny(nq.entry_time_ny); nq = nq[["entry_time", "r"]]
pe = pd.concat([pead_trades(s, k=2.5, N=10, confirm=True) for s in SYMS])
pe["entry_time"] = (pd.to_datetime(pe.entry_time) + pd.Timedelta(hours=9, minutes=30)).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
pe = pe[["entry_time", "r"]]
jp = lb()[["entry_time", "r"]]
nf = pd.read_pickle("newfam_trades.pkl"); fo = nf[nf.name == "B pre-FOMC US100.cash"][["entry_time", "r"]]
S = {"gold": g, "Nasdaq ORB": nq, "stock drift": pe, "USDJPY London BO": jp, "pre-FOMC US100": fo}

rows = []
for n, t in S.items():
    t = t[(t.entry_time >= START) & (t.entry_time < END)].copy()
    t["bad"] = gold_bad_at(t.entry_time)
    a, b = t.r[~t.bad], t.r[t.bad]
    tstat, p = stats.ttest_ind(b, a, equal_var=False) if len(a) > 2 and len(b) > 2 else (np.nan, np.nan)
    rng = np.random.default_rng(0); diffs = []
    allr = t.r.values; nb = len(b)
    for _ in range(2000):
        idx = rng.permutation(len(allr)); diffs.append(allr[idx[:nb]].mean() - allr[idx[nb:]].mean())
    perm_p = np.mean(np.abs(diffs) >= abs(b.mean() - a.mean()))
    rows.append({"strategy": n, "trades GOOD / BAD": f"{len(a)} / {len(b)}", "R/trade gold GOOD": round(a.mean(), 3),
                 "R/trade gold BAD": round(b.mean(), 3), "total R GOOD / BAD": f"{a.sum():+.1f} / {b.sum():+.1f}",
                 "diff p-value (t / permutation)": f"{p:.2f} / {perm_p:.2f}"})
pd.set_option("display.width", 250)
print("1) RESULTS BY GOLD REGIME (at trade entry)"); print(pd.DataFrame(rows).to_string(index=False))

wk = pd.DataFrame({n: t[(t.entry_time >= START) & (t.entry_time < END)].set_index("entry_time").r.resample("W").sum() for n, t in S.items()}).fillna(0)
bad_share = pd.Series(gold_bad_at(pd.Series(pd.date_range(START, END, freq="h", tz="UTC"))), index=pd.date_range(START, END, freq="h", tz="UTC")).resample("W").mean()
wk["gold BAD share"] = bad_share.reindex(wk.index).fillna(0)
print("\n2) WEEKLY correlation with gold's weekly R and with the gold-BAD share of the week")
print(pd.DataFrame({"corr with gold weekly R": wk.corr()["gold"], "corr with gold BAD share": wk.corr()["gold BAD share"]}).drop(["gold BAD share"]).round(3).to_string())
print("\n3) WEEKLY R correlation matrix"); print(wk.drop(columns="gold BAD share").corr().round(2).to_string())
mo = wk.drop(columns="gold BAD share").resample("ME").sum()
print("\n4) MONTHS: when gold's month was negative, how often was each other strategy positive (share of those months)")
neg = mo.gold < 0
print((mo[neg] > 0).mean().round(2).to_string(), f"\n(gold negative months: {neg.sum()} of {len(mo)})")
