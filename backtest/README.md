# Offline replay of the strategy

A Python copy of `pinescsript.txt` used to test changes without TradingView.

- `signals.py` - the indicator part: SuperTrend AI clustering signals, fakeout filter,
  reversal zones and WaveTrend trigger waves (take profit warning events).
- `replay.py` - the strategy part, bar by bar in the script's order, with TradingView's
  broker rules (orders at the bar close, limit/stop fills inside the bar, whole-unit
  sizes). Settings default to the script's defaults.
- `compare.py` - replays a price file and compares it trade by trade with a TradingView
  *List of trades* export.
- `fetch_oanda.py` - downloads OANDA XAU_USD 15m candles (the feed behind TradingView's
  OANDA:XAUUSD). Needs `OANDA_API_TOKEN` in the environment.

## Matching TradingView

    python3 fetch_oanda.py 2026-01-01
    python3 compare.py data/oanda_xauusd_15m_mid.csv tv_exports/oanda_xauusd_15m_closevol_filter.csv --start 2026-03-31
    python3 compare.py data/oanda_xauusd_15m_bid.csv tv_exports/oanda_xauusd_15m_closevol_filter.csv --start 2026-03-31

`--start` must be the first bar the TradingView chart had loaded (the indicators warm up
from there) and `--tz` the chart's timezone (default Europe/London).

On Dukascopy prices (`data/dukascopy_xauusd_15m.csv`, a different broker feed) the replay
lands on the same entry bar as TradingView for about 66% of trades and on the same exit bar
for 92% of those; the rest move by a bar because the two feeds' candles differ by a few
dollars. Matching trade for trade needs OANDA's own candles.
