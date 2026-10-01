"""Generate the 'minimum close penetration' experiment EA from the deployed gold EA.

Rule (InpCloseMinAtr):
  >= 0 : a breakout order may only be armed if the last closed bar CLOSED at least
         InpCloseMinAtr x ATR beyond the channel edge it is breaking.
  <  0 : off - byte-for-byte the live behaviour.

Applied in both the live path (OnBarClose) and the paper/regime engine (PaperStep) so the
regime state stays consistent with the trades that are actually taken.
"""
import os
import re

SRC = r"c:\Users\Abdo\Downloads\pine2\mt5\GoldTrendBreakout.mq5"
OUT_DIR = r"c:\Users\Abdo\Downloads\pine2\research\ea"
OUT = os.path.join(OUT_DIR, "GTBClosePen.mq5")
os.makedirs(OUT_DIR, exist_ok=True)

src = open(SRC, encoding="utf-8-sig", errors="replace").read()
orig = src

# ---- 1. the new input, next to the other signal inputs -------------------------------
anchor = 'input double InpBufAtr        = 0.05;    // Breakout buffer (ATR)'
assert src.count(anchor) == 1, "InpBufAtr input line not found"
src = src.replace(anchor, anchor + '\ninput double InpCloseMinAtr   = -1;      // Min close beyond the level to arm an order (ATR, -1 = off)')

# ---- 2. live path: gate both sides of the entry block --------------------------------
# The gate must be measured against the channel WITHOUT the bar that just closed (bars 2..),
# because the entry channel (bars 1..) already contains that bar's own extreme - its close can
# never be beyond it, which would make the test degenerate.
old = ('      if(canEnter && longOk) SendStop(1, longTrig, longTrig - stopDist, lots, "GTB Buy", expiry, riskNow);\n'
       '      if(canEnter && shortOk) SendStop(-1, shortTrig, shortTrig + stopDist, lots, "GTB Sell", expiry, riskNow);')
assert src.count(old) == 1, "live entry block not found"
new = ('      int hiG = iHighest(_Symbol, PERIOD_CURRENT, MODE_HIGH, chanLen, 2);   // level without the bar that just closed\n'
       '      int loG = iLowest(_Symbol, PERIOD_CURRENT, MODE_LOW, chanLen, 2);\n'
       '      double c1 = iClose(_Symbol, PERIOD_CURRENT, 1);                       // where that bar left the price\n'
       '      bool longCloseOk  = (InpCloseMinAtr < 0) || (hiG >= 0 && c1 >= iHigh(_Symbol, PERIOD_CURRENT, hiG) + InpCloseMinAtr * atr);\n'
       '      bool shortCloseOk = (InpCloseMinAtr < 0) || (loG >= 0 && c1 <= iLow(_Symbol, PERIOD_CURRENT, loG) - InpCloseMinAtr * atr);\n'
       '      if(canEnter && longOk && longCloseOk) SendStop(1, longTrig, longTrig - stopDist, lots, "GTB Buy", expiry, riskNow);\n'
       '      if(canEnter && shortOk && shortCloseOk) SendStop(-1, shortTrig, shortTrig + stopDist, lots, "GTB Sell", expiry, riskNow);')
src = src.replace(old, new)

# ---- 3. paper engine: same gate when the next bar's orders are built -----------------
old = ('      if(hi >= 0 && (!InpUseTrend || trend == 1))\n'
       '      { double t = iHigh(_Symbol, PERIOD_CURRENT, hi) + InpBufAtr * atr; sh_ordDir[sh_nOrd] = 1; sh_ordTrig[sh_nOrd] = t; sh_ordStop[sh_nOrd] = t - InpStopAtr * atr; sh_nOrd++; }\n'
       '      if(lo >= 0 && (!InpUseTrend || trend == -1))\n'
       '      { double t = iLow(_Symbol, PERIOD_CURRENT, lo) - InpBufAtr * atr; sh_ordDir[sh_nOrd] = -1; sh_ordTrig[sh_nOrd] = t; sh_ordStop[sh_nOrd] = t + InpStopAtr * atr; sh_nOrd++; }')
assert src.count(old) == 1, "paper entry block not found"
new = ('      int hiG = iHighest(_Symbol, PERIOD_CURRENT, MODE_HIGH, chanLen, s + 1);   // level without bar s\n'
       '      int loG = iLowest(_Symbol, PERIOD_CURRENT, MODE_LOW, chanLen, s + 1);\n'
       '      bool longCloseOk  = (InpCloseMinAtr < 0) || (hiG >= 0 && c >= iHigh(_Symbol, PERIOD_CURRENT, hiG) + InpCloseMinAtr * atr);\n'
       '      bool shortCloseOk = (InpCloseMinAtr < 0) || (loG >= 0 && c <= iLow(_Symbol, PERIOD_CURRENT, loG) - InpCloseMinAtr * atr);\n'
       '      if(hi >= 0 && (!InpUseTrend || trend == 1) && longCloseOk)\n'
       '      { double t = iHigh(_Symbol, PERIOD_CURRENT, hi) + InpBufAtr * atr; sh_ordDir[sh_nOrd] = 1; sh_ordTrig[sh_nOrd] = t; sh_ordStop[sh_nOrd] = t - InpStopAtr * atr; sh_nOrd++; }\n'
       '      if(lo >= 0 && (!InpUseTrend || trend == -1) && shortCloseOk)\n'
       '      { double t = iLow(_Symbol, PERIOD_CURRENT, lo) - InpBufAtr * atr; sh_ordDir[sh_nOrd] = -1; sh_ordTrig[sh_nOrd] = t; sh_ordStop[sh_nOrd] = t + InpStopAtr * atr; sh_nOrd++; }')
src = src.replace(old, new)

# ---- 4. rename the property so the tester report is unmistakable --------------------
src = src.replace('#property copyright "Gold Trend Breakout"',
                  '#property copyright "Gold Trend Breakout - close-penetration experiment"')

open(OUT, "w", encoding="utf-8").write(src)
print("wrote", OUT, len(src), "chars (source", len(orig), ")")
print("new input:", re.search(r"input double InpCloseMinAtr.*", src).group(0).strip())
