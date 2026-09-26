"""Replay the strategy on a price file and compare it trade by trade with a TradingView
List of trades export.

  python3 compare.py data/<prices>.csv tv_exports/<export>.csv [--tz Europe/London] [--start 2026-03-31]

--tz is the chart's timezone (TradingView writes trade times in it); --start is the first
bar the chart had loaded, because indicators warm up from there.
"""
import argparse
import pandas as pd
from replay import replay


def load_prices(fn, start=None, tz=None):
    df = pd.read_csv(fn, index_col=0, parse_dates=True)
    if df.index.tz is None: df.index = df.index.tz_localize("UTC")
    if start is not None:
        df = df[df.index >= pd.Timestamp(start, tz=tz).tz_convert("UTC")]
    return df[["open", "high", "low", "close"]]


def load_tv(fn, tz):
    t = pd.read_csv(fn, encoding="utf-8-sig")
    t["time"] = pd.to_datetime(t["Date and time"]).dt.tz_localize(tz).dt.tz_convert("UTC")
    en = t[t.Type.str.startswith("Entry")].set_index("Trade number")
    ex = t[t.Type.str.startswith("Exit")].set_index("Trade number")
    return pd.DataFrame({"entry_time": en.time, "dir": en.Type.str.contains("long").map({True: 1, False: -1}),
                         "entry": en["Price USD"], "qty": en["Size (qty)"], "exit_time": ex.time,
                         "exit": ex["Price USD"], "pnl": ex["Net PnL USD"], "why": ex.Signal})


def summary(T):
    w, lo = T.pnl[T.pnl > 0].sum(), -T.pnl[T.pnl < 0].sum()
    return f"{len(T)} trades, net {T.pnl.sum():+.2f}, PF {w / lo:.3f}, win {100 * (T.pnl > 0).mean():.1f}%"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("prices"); ap.add_argument("tv")
    ap.add_argument("--tz", default="Europe/London"); ap.add_argument("--start", default=None)
    a = ap.parse_args()
    R, _ = replay(load_prices(a.prices, a.start, a.tz))
    V = load_tv(a.tv, a.tz)
    R = R[R.entry_time >= V.entry_time.min() - pd.Timedelta("1D")]
    print("TradingView:", summary(V)); print("Replay:     ", summary(R))
    key = lambda T: set(zip(T.entry_time, T.dir))
    both = key(R) & key(V)
    print(f"Same entry bar and direction: {len(both)} of {len(V)} TradingView trades ({100 * len(both) / len(V):.1f}%)")
    m = V.merge(R, on=["entry_time", "dir"], suffixes=("_tv", "_rp"))
    if len(m):
        print(f"  on those: same exit bar {100 * (m.exit_time_tv == m.exit_time_rp).mean():.1f}%, "
              f"median |entry price diff| {m.eval('abs(entry_tv-entry_rp)').median():.2f}, "
              f"same qty {100 * (m.qty_tv == m.qty_rp).mean():.1f}%")
    only_tv = V[[k not in both for k in zip(V.entry_time, V.dir)]]
    only_rp = R[[k not in both for k in zip(R.entry_time, R.dir)]]
    print(f"Only in TradingView: {len(only_tv)} (net {only_tv.pnl.sum():+.2f})   Only in replay: {len(only_rp)} (net {only_rp.pnl.sum():+.2f})")
    pd.set_option("display.width", 200)
    print("\nFirst trades that differ (TradingView side):"); print(only_tv.head(10).to_string())
    print("\nFirst trades that differ (replay side):"); print(only_rp.head(10).to_string())
