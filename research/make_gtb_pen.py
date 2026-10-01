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

# ---- 5. experiment switches: breakeven-after-add toggle + stop-and-re-enter -----------
anchor = 'input double InpCloseMinAtr   = -1;      // Min close beyond the level to arm an order (ATR, -1 = off)'
assert src.count(anchor) == 1
src = src.replace(anchor, anchor + '\n'
    'input bool   InpBeAfterAdd    = true;    // Move both stops to the entry after the add\n'
    'input bool   InpReentryEnable = false;   // After a stop-out, go again in the same direction\n'
    'input double InpReentryStopAtr= 1.5;    // ... with this initial stop (ATR)\n'
    'input int    InpReentryBars   = 48;      // ... if the stop-out is not older than this many bars\n'
    'input int    InpReentryMax    = 1;       // ... at most this many re-entries per week of trading')

# BE after the add (and the add order\'s own stop) follow the switch
old = '      if(g_added) g_stop = g_dir == 1 ? MathMax(g_stop, g_entry) : MathMin(g_stop, g_entry);'
assert src.count(old) == 1
src = src.replace(old, '      if(g_added && InpBeAfterAdd) g_stop = g_dir == 1 ? MathMax(g_stop, g_entry) : MathMin(g_stop, g_entry);')
old = '      double addStop = g_dir == 1 ? MathMax(g_stop, g_entry) : MathMin(g_stop, g_entry);'
assert src.count(old) == 1
src = src.replace(old, '      double addStop = InpBeAfterAdd ? (g_dir == 1 ? MathMax(g_stop, g_entry) : MathMin(g_stop, g_entry)) : g_stop;')
old = '      if(g_added) g_stop = g_dir == 1 ? MathMax(g_stop, g_entry) : MathMin(g_stop, g_entry);\n      SetStopAll(g_stop);'
src = src.replace(old, '      if(g_added && InpBeAfterAdd) g_stop = g_dir == 1 ? MathMax(g_stop, g_entry) : MathMin(g_stop, g_entry);\n      SetStopAll(g_stop);')

# globals for the re-entry
anchor = 'string   g_nextCloseReason = "";'
assert src.count(anchor) == 1
src = src.replace(anchor, anchor + '\nbool     g_reArmed = false;      // a stop-out is waiting for its re-entry\n'
                                        'int      g_reDir = 0;            // direction of that re-entry\n'
                                        'double   g_rePrice = 0;          // price at which we were stopped out\n'
                                        'datetime g_reBar = 0;            // bar in which that happened\n'
                                        'int      g_reChain = 0;          // re-entries already taken after the last real entry')

# a real (non re-entry) fill resets the chain; a re-entry fill does not
anchor_in = '   if(entry == DEAL_ENTRY_IN)\n   {\n      int day = PragueDayKey((datetime)HistoryDealGetInteger(tr.deal, DEAL_TIME));'
assert src.count(anchor_in) == 1
src = src.replace(anchor_in, '   if(entry == DEAL_ENTRY_IN)\n   {\n'
        '      if(StringFind(HistoryDealGetString(tr.deal, DEAL_COMMENT), "GTB Re") < 0) g_reChain = 0;\n'
        '      int day = PragueDayKey((datetime)HistoryDealGetInteger(tr.deal, DEAL_TIME));')

# arm the re-entry when our position is stopped out
old = ('   else if(entry == DEAL_ENTRY_OUT)\n'
       '   {\n'
       '      long reason = HistoryDealGetInteger(tr.deal, DEAL_REASON);')
assert src.count(old) == 1
src = src.replace(old, old + '\n'
       '      // the position that just closed: an OUT deal of type BUY closes a short, and vice versa.\n'
       '      // (g_dir is only set at bar closes, so it is still 0 when a trade stops out inside its entry bar.)\n'
       '      int closedDir = HistoryDealGetInteger(tr.deal, DEAL_TYPE) == DEAL_TYPE_BUY ? -1 : 1;\n'
       '      if(InpReentryEnable && reason == DEAL_REASON_SL && g_reDir == 0)\n'
       '      {\n'
       '         g_reArmed = true; g_reDir = closedDir; g_rePrice = HistoryDealGetDouble(tr.deal, DEAL_PRICE);\n'
       '         g_reBar = (datetime)HistoryDealGetInteger(tr.deal, DEAL_TIME);\n'
       '      }')

# ---- 6. optional second add (amplify the winners, the tail that pays for the losses) ----
anchor = 'input bool   InpReentryEnable = false;   // After a stop-out, go again in the same direction'
assert src.count(anchor) == 1
src = src.replace(anchor, 'input double InpAdd2AtR      = 0;       // Second add at this R (0 = off)\n' + anchor)

anchor = 'bool     g_reArmed = false;      // a stop-out is waiting for its re-entry'
assert src.count(anchor) == 1
src = src.replace(anchor, 'bool     g_added2 = false;       // the second add is filled\n' + anchor)

# reset the flag together with g_added
old = '   if(g_dir != 0 && n == 0) { g_dir = 0; g_added = false; }'
assert src.count(old) == 1
src = src.replace(old, '   if(g_dir != 0 && n == 0) { g_dir = 0; g_added = false; g_added2 = false; }')

# the second add: same machinery, one level higher, at most one unit
old = '   if(g_dir != 0 && !g_added && InpAddAtR > 0 && n == 1)'
assert src.count(old) == 1
src = src.replace(old,
    '   if(g_dir != 0 && g_added && !g_added2 && InpAdd2AtR > 0 && n == 2)\n'
    '   {\n'
    '      double r02 = MathAbs(g_entry - g_stop0);\n'
    '      double addLvl2 = g_entry + g_dir * InpAdd2AtR * r02;\n'
    '      double addStop2 = InpBeAfterAdd ? (g_dir == 1 ? MathMax(g_stop, g_entry) : MathMin(g_stop, g_entry)) : g_stop;\n'
    '      double addDist2 = MathAbs(addLvl2 - addStop2);\n'
    '      double taken2; double lots2 = addDist2 > 0 ? LotsFor(riskNow, addDist2, taken2) : 0;\n'
    '      double others2 = OtherOpenRisk();\n'
    '      bool fits2 = !InpPropRules || (dayLoss + others2 + taken2 <= InpDailyLimitPct && totalLoss + others2 + taken2 <= InpTotalLimitPct);\n'
    '      if(lots2 > 0 && fits2 && !nearNews && !closingBar && !nextClosing && !limitHit && !g_passed)\n'
    '         if(SendStop(g_dir, addLvl2, addStop2, lots2, "GTB Add2", expiry, riskNow))\n'
    '            { g_added2 = true; LogEvent("ADD", StringFormat("second add at +%.1fR", InpAdd2AtR)); }\n'
    '   }\n'
    '   if(g_dir != 0 && !g_added && InpAddAtR > 0 && n == 1)')
old = ('   // --- entries, only while flat ----------------------------------------------------------------------\n'
       '   DeletePending("GTB Buy");')
assert src.count(old) == 1
src = src.replace(old, old + '\n'
       '   if(InpReentryEnable && g_reArmed)\n'
       '   {\n'
       '      bool fresh = g_reBar > 0 && (iTime(_Symbol, PERIOD_CURRENT, 0) - g_reBar) <= (datetime)(InpReentryBars * per);\n'
       '      if(g_dir == 0 && g_reDir != 0 && fresh && !nearNews && !closingBar && !nextClosing && !limitHit && !g_passed)\n'
       '      {\n'
       '         double rdist = InpReentryStopAtr * atr;\n'
       '         double taken2; double rlots = LotsFor(riskNow, rdist, taken2);\n'
       '         if(rlots > 0)\n'
       '         {\n'
       '            if(SendStop(g_reDir, g_rePrice, g_rePrice - g_reDir * rdist, rlots, "GTB Re", expiry, riskNow))\n'
       '               { g_reChain++; g_reArmed = false; LogEvent("ENTRY", StringFormat("re-entry %s at %.2f after the stop-out", g_reDir == 1 ? "buy" : "sell", g_rePrice)); }\n'
       '         }\n'
       '      }\n'
       '      if(!fresh) { g_reArmed = false; g_reDir = 0; }\n'
       '   }\n'
       '   if(g_reArmed && g_dir != 0) { g_reArmed = false; g_reDir = 0; }')

# ---- 7. split entry: part of the risk at the level, the rest only once the break extends -----
anchor = 'input double InpAdd2AtR      = 0;       // Second add at this R (0 = off)'
assert src.count(anchor) == 1
src = src.replace(anchor, 'input double InpEntryFrac    = 1.0;     // Share of the risk taken at the breakout\n' + anchor)
old = '      double lots = LotsFor(riskNow, stopDist, taken);'
assert src.count(old) == 1
src = src.replace(old, '      double lots = LotsFor(riskNow * InpEntryFrac, stopDist, taken);')
old = '      double lots = addDist > 0 ? LotsFor(riskNow, addDist, taken) : 0;'
assert src.count(old) == 1
src = src.replace(old, '      double lots = addDist > 0 ? LotsFor(riskNow * InpEntryFrac, addDist, taken) : 0;')


open(OUT, "w", encoding="utf-8").write(src)
print("wrote", OUT, len(src), "chars (source", len(orig), ")")
print("new input:", re.search(r"input double InpCloseMinAtr.*", src).group(0).strip())
