"""Out-of-sample 2009-2019 (MetaQuotes H1): main gold strategy + regime filter, and the overnight long drift."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import gen as G, pyramid
from concepts import prep
from regime import paper_trades, regime_flag

def load_full(sym, new_file):
    a = pd.read_csv(f"data/OLD_{sym}_H1.csv"); b = pd.read_csv(new_file)
    d = pd.concat([a, b]).drop_duplicates("utc").sort_values("utc")
    d = d.rename(columns={"utc": "time", "open": "o", "high": "h", "low": "l", "close": "c"})
    d["time"] = pd.to_datetime(d.time, utc=True)
    return prep(d.reset_index(drop=True))

if __name__ == "__main__":
    g = load_full("XAUUSD", "data/XAUUSD_H1.csv")
    p = paper_trades(g); bad = regime_flag(g, p)
    ei = g.set_index("time").index.get_indexer(pd.DatetimeIndex(p.entry_time))
    nyh = g.ny_h.values[ei]
    p["live"] = ~bad[ei] | ((nyh >= 8) & (nyh < 17)); p["bad"] = bad[ei]
    y = p.entry_time.dt.year
    t = pd.DataFrame({"paper(all sessions)": p.r.groupby(y).sum(), "live (regime filter)": p.r[p.live].groupby(y[p.live]).sum(),
                      "live trades in BAD": p.r[p.live & p.bad].groupby(y[p.live & p.bad]).sum(), "n": p.r.groupby(y).count()}).round(1)
    print("MAIN STRATEGY by year (R per unit, $0.30 cost)"); print(t.to_string())
    # overnight long drift
    end_h = (g.ny_h.values + g.tf_h.values[0]) % 24
    D = G.daily_frame(g); P = D.shift(1); tday = g.tday.values
    res = {}
    for entry, exit_ in ((19.0, 3.0), (19.0, 7.0), (20.0, 3.0), (20.0, 7.0)):
        def gfn(i, entry=entry, exit_=exit_):
            if abs(end_h[i] - entry) > 1e-6: return None
            a = P.atr.get(tday[i], np.nan)
            return None if np.isnan(a) else [dict(dir=1, stop_dist=a, exit_at=exit_)]
        for mode, al in (("ALL", None), ("BAD", bad)):
            tr = G.run(g, gfn, allowed=al)
            res[f"{int(entry)}->{int(exit_)} {mode}"] = tr.r.groupby(tr.entry_time.dt.year).sum()
    print("\nOVERNIGHT LONG DRIFT by year (R, stop 1 daily ATR)"); print(pd.DataFrame(res).round(1).to_string())
