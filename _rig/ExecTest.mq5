//+------------------------------------------------------------------+
//| ExecTest.mq5 - REAL-ORDER execution test on the demo account.    |
//|                                                                  |
//| Runs the same order kinds the two live EAs use, on every symbol  |
//| and in both directions, and reads every stop/target back from    |
//| the SERVER (PositionSelect / OrderSelect), not just from the     |
//| trade call's return value:                                       |
//|   market BUY  + SL      -> read back -> modify stop -> close     |
//|   market SELL + SL      -> read back -> close                    |
//|   BUY  STOP pending + SL-> read back -> cancel                   |
//|   SELL STOP pending + SL-> read back -> cancel                   |
//| Also dumps each symbol's contract spec and the $ risk of the     |
//| size the EAs' formula would pick (validates the sizing math).    |
//|                                                                  |
//| Only touches its own magic number. Report:                        |
//|   Common\Files\GoldBreakout\exec_test.log (+ the Experts journal) |
//| When it finishes, every position/order it created is gone.        |
//+------------------------------------------------------------------+
#property copyright "ExecTest"
#property version   "1.00"

#include <Trade\Trade.mqh>

input string InpSymbols     = "XAUUSD,US100.cash"; // Symbols to test (comma separated)
input double InpVolume      = 0.01;                // Volume per trade
input double InpRiskPct     = 1.0;                 // Risk % used for the sizing check
input long   InpMagic       = 99990001;            // Magic number for the test trades
input int    InpDeviation   = 300;                 // Deviation (points)
input bool   InpCleanupOnly = false;               // true = only close/delete this magic

CTrade trade;
int    g_h = INVALID_HANDLE;
string g_sym[];
int    g_nsym = 0;
int    g_si = 0;        // current symbol index
int    g_step = 0;      // step inside the symbol
double g_slDist = 0;    // stop distance for the current symbol
double g_entry = 0;     // entry price of the open test position
double g_expectSL = 0;  // stop we asked the server to set
ulong  g_ticket = 0;    // position ticket
ulong  g_order = 0;     // pending order ticket
ulong  g_pendingClose = 0; // position we just closed (verified one step later)

void L(const string s)
{
   Print(s);
   if(g_h != INVALID_HANDLE) { FileWriteString(g_h, s + "\n"); FileFlush(g_h); }
}

double StopsDist(const string sym)
{
   double pt  = SymbolInfoDouble(sym, SYMBOL_POINT);
   long   lvl = SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
   long   frz = SymbolInfoInteger(sym, SYMBOL_TRADE_FREEZE_LEVEL);
   return MathMax(200.0 * pt, (lvl + frz + 10) * pt);
}


//--- does our magic hold anything? -----------------------------------
bool MyPos(const string sym, int &dir, double &vol, double &open, double &sl, double &tp, ulong &ticket)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != sym) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      dir = (int)PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1;
      vol = PositionGetDouble(POSITION_VOLUME); open = PositionGetDouble(POSITION_PRICE_OPEN);
      sl = PositionGetDouble(POSITION_SL); tp = PositionGetDouble(POSITION_TP); ticket = t;
      return true;
   }
   return false;
}

bool MyOrd(const string sym, int &dir, double &price, double &sl, double &tp, ulong &ticket)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != sym) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      dir = (int)OrderGetInteger(ORDER_TYPE) == ORDER_TYPE_BUY_STOP ? 1 : -1;
      price = OrderGetDouble(ORDER_PRICE_OPEN); sl = OrderGetDouble(ORDER_SL); tp = OrderGetDouble(ORDER_TP);
      ticket = t;
      return true;
   }
   return false;
}

void CloseAllMine()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      string s = PositionGetString(POSITION_SYMBOL);
      if(trade.PositionClose(t)) L(StringFormat("    cleanup: closed %s", s));
      else L(StringFormat("    cleanup: CLOSE FAILED %s ret=%d %s", s, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      if(trade.OrderDelete(t)) L(StringFormat("    cleanup: deleted pending order #%I64u", t));
      else L(StringFormat("    cleanup: DELETE FAILED #%I64u ret=%d %s", t, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
   }
}

void ReportDeals(const ulong posId)
{
   if(!HistorySelectByPosition(posId)) { L("    history: select failed"); return; }
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      L(StringFormat("    deal #%I64u %s %s %.2f lots @ %.3f  profit %.2f comm %.2f swap %.2f reason %s",
                     d,
                     (HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN ? "IN " : "OUT"),
                     (HistoryDealGetInteger(d, DEAL_TYPE) == DEAL_TYPE_BUY ? "buy " : "sell"),
                     HistoryDealGetDouble(d, DEAL_VOLUME), HistoryDealGetDouble(d, DEAL_PRICE),
                     HistoryDealGetDouble(d, DEAL_PROFIT), HistoryDealGetDouble(d, DEAL_COMMISSION),
                     HistoryDealGetDouble(d, DEAL_SWAP),
                     EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(d, DEAL_REASON))));
   }
}


//+------------------------------------------------------------------+
int OnInit()
{
   g_h = FileOpen("GoldBreakout\\exec_test.log", FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
   if(g_h == INVALID_HANDLE) Print("WARNING: cannot open the report file, journal only");
   L("");
   L("================ EXECTEST " + TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS) + " UTC ================");
   L(StringFormat("account %I64d %s %s, balance %.2f %s, leverage 1:%I64d",
                  AccountInfoInteger(ACCOUNT_LOGIN), AccountInfoString(ACCOUNT_SERVER), AccountInfoString(ACCOUNT_COMPANY),
                  AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoString(ACCOUNT_CURRENCY),
                  AccountInfoInteger(ACCOUNT_LEVERAGE)));
   L(StringFormat("terminal trade allowed=%d, account trade allowed=%d",
                  (int)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED), (int)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)));

   string parts[];
   int n = StringSplit(InpSymbols, ',', parts);
   ArrayResize(g_sym, 0);
   for(int i = 0; i < n; i++)
   {
      string s = parts[i]; StringTrimLeft(s); StringTrimRight(s);
      if(StringLen(s) == 0) continue;
      ArrayResize(g_sym, g_nsym + 1); g_sym[g_nsym++] = s;
   }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviation);
   trade.LogLevel(LOG_LEVEL_ERRORS);

   if(InpCleanupOnly)
   {
      L("--- cleanup only: removing everything with magic " + (string)InpMagic);
      CloseAllMine();
      L("--- cleanup done");
      if(g_h != INVALID_HANDLE) { FileClose(g_h); g_h = INVALID_HANDLE; }
      ExpertRemove();
      return INIT_SUCCEEDED;
   }
   EventSetTimer(1);
   return INIT_SUCCEEDED;
}


//+------------------------------------------------------------------+
void OnTimer()
{
   if(g_si >= g_nsym)
   {
      static bool once = false;
      if(once) return;
      once = true;
      int left = 0;
      for(int i = 0; i < g_nsym; i++) { int d; double v, o, s, t; ulong tk; if(MyPos(g_sym[i], d, v, o, s, t, tk)) left++; }
      L(StringFormat("--- positions of ours still open: %d (must be 0)", left));
      CloseAllMine();
      L("================ EXECTEST COMPLETE ================");
      Print("EXECTEST COMPLETE - report: Common\\Files\\GoldBreakout\\exec_test.log");
      if(g_h != INVALID_HANDLE) { FileClose(g_h); g_h = INVALID_HANDLE; }
      ExpertRemove();
      return;
   }
   if(!TerminalInfoInteger(TERMINAL_CONNECTED)) { static int w; if(w++ % 10 == 0) Print("waiting for connection..."); return; }
   if(AccountInfoInteger(ACCOUNT_LOGIN) == 0)   { static int w2; if(w2++ % 10 == 0) Print("waiting for the account..."); return; }

   string sym = g_sym[g_si];
   if(!SymbolSelect(sym, true)) { L("!!! " + sym + " cannot be selected (not offered by this broker)"); g_si++; g_step = 0; return; }

   MqlTick tk;
   if(!SymbolInfoTick(sym, tk) || tk.ask <= 0 || tk.bid <= 0) return;
   double pt = SymbolInfoDouble(sym, SYMBOL_POINT);
   int    dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   g_slDist = StopsDist(sym);

   if(g_step == 0)
   {
      L("");
      L("--------------- " + sym + " ---------------");
      L(StringFormat("spec: digits=%d point=%s spread=%d pts stops_level=%d pts freeze=%d pts trade_mode=%s filling=%d",
                     dg, DoubleToString(pt, 10), (int)SymbolInfoInteger(sym, SYMBOL_SPREAD),
                     (int)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL), (int)SymbolInfoInteger(sym, SYMBOL_TRADE_FREEZE_LEVEL),
                     EnumToString((ENUM_SYMBOL_TRADE_MODE)SymbolInfoInteger(sym, SYMBOL_TRADE_MODE)),
                     (int)SymbolInfoInteger(sym, SYMBOL_FILLING_MODE)));
      L(StringFormat("spec: volume min=%s step=%s max=%s, tick_size=%s tick_value=%.4f => %.2f %s per 1.0 price per lot",
                     DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), 2),
                     DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP), 2),
                     DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX), 2),
                     DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE), 10),
                     SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE),
                     SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE) / SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE),
                     AccountInfoString(ACCOUNT_CURRENCY)));
      double volMin = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), volStep = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
      double volMax = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
      double perLot = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE) / SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
      double want  = (AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct / 100.0) / (g_slDist * perLot);
      double sized = MathFloor(want / volStep) * volStep;
      sized = MathMax(volMin, MathMin(volMax, sized));
      L(StringFormat("sizing check: stop %s (%s pts) -> %s%% risk = %s lots (clamped %s..%s step %s); risk of %s lots = %.2f %s",
                     DoubleToString(g_slDist, dg), DoubleToString(g_slDist / pt, 0), DoubleToString(InpRiskPct, 2),
                     DoubleToString(want, 4), DoubleToString(volMin, 2), DoubleToString(volMax, 2), DoubleToString(volStep, 2),
                     DoubleToString(sized, 2), sized * g_slDist * perLot, AccountInfoString(ACCOUNT_CURRENCY)));
      trade.SetTypeFillingBySymbol(sym);
      g_step = 1;
      return;
   }
   if(g_step == 1)  // market BUY + SL
   {
      double vol = MathMax(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), InpVolume);
      double sl  = NormalizeDouble(tk.bid - g_slDist, dg);
      L(StringFormat("STEP 1: market BUY %s lots, SL %s", DoubleToString(vol, 2), DoubleToString(sl, dg)));
      bool ok = trade.Buy(vol, sym, 0.0, sl, 0.0, "EXECTEST BUY");
      L(StringFormat("    send: ok=%d retcode=%d (%s) order=%I64u deal=%I64u price=%s volume=%s",
                     ok, trade.ResultRetcode(), trade.ResultRetcodeDescription(), trade.ResultOrder(),
                     trade.ResultDeal(), DoubleToString(trade.ResultPrice(), dg), DoubleToString(trade.ResultVolume(), 2)));
      int d; double v, o, s, t; ulong tkt;
      if(MyPos(sym, d, v, o, s, t, tkt))
      {
         g_ticket = tkt; g_entry = o;
         L(StringFormat("    SERVER read-back: %s %.2f lots @ %s  SL=%s TP=%s  => %s", d > 0 ? "BUY" : "SELL", v,
                        DoubleToString(o, dg), DoubleToString(s, dg), DoubleToString(t, dg),
                        (s > 0 ? "SL SET" : "!!! NO SL")));
      }
      else L("    !!! no position found after the send");
      g_step = 2;
      return;
   }

   if(g_step == 2)  // move the stop in the profitable direction, the way the EAs do it
   {
      int d; double v, o, s, t; ulong tkt;
      if(MyPos(sym, d, v, o, s, t, tkt))
      {
         // a stop must stay on the correct side of the market: below the bid for a long,
         // above the ask for a short (this is what the EA's trailing/breakeven move does)
         double newSl = NormalizeDouble(d > 0 ? tk.bid - 0.5 * g_slDist : tk.ask + 0.5 * g_slDist, dg);
         if(d > 0 && newSl <= s) newSl = NormalizeDouble(s + pt, dg);          // keep it strictly better
         if(d < 0 && newSl >= s) newSl = NormalizeDouble(s - pt, dg);
         bool ok = trade.PositionModify(tkt, newSl, 0.0);
         L(StringFormat("STEP 2: move the stop from %s to %s (breakeven / trail path)",
                        DoubleToString(s, dg), DoubleToString(newSl, dg)));
         L(StringFormat("    send: ok=%d retcode=%d (%s)", ok, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         g_expectSL = newSl;   // verified at the start of the next step, so the server has a moment
      }
      else L("STEP 2: no position to modify");
      g_step = 3;
      return;
   }
   if(g_step == 3)  // verify the stop move, then close at market
   {
      int d; double v, o, s, t; ulong tkt;
      if(MyPos(sym, d, v, o, s, t, tkt))
      {
         L(StringFormat("    STEP 2 verify: SL is now %s (expected %s) => %s", DoubleToString(s, dg),
                        DoubleToString(g_expectSL, dg), (MathAbs(s - g_expectSL) <= pt ? "SL MOVED" : "!!! SL NOT MOVED")));
         bool ok = trade.PositionClose(tkt);
         L(StringFormat("STEP 3: close the %s at market", d > 0 ? "BUY" : "SELL"));
         L(StringFormat("    send: ok=%d retcode=%d (%s) price=%s", ok, trade.ResultRetcode(),
                        trade.ResultRetcodeDescription(), DoubleToString(trade.ResultPrice(), dg)));
         g_pendingClose = tkt;    // confirmed closed at the start of the next step
         ReportDeals(tkt);
      }
      else L("STEP 3: no position to close");
      g_step = 4;
      return;
   }
   if(g_step == 4)  // the BUY must be gone before the next order
   {
      int d; double v, o, s, t; ulong tkt;
      L(StringFormat("    STEP 3 verify: the position is %s", MyPos(sym, d, v, o, s, t, tkt) ? "STILL OPEN (!!!)" : "closed"));
      g_pendingClose = 0;
      double vol = MathMax(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), InpVolume);
      double sl  = NormalizeDouble(tk.ask + g_slDist, dg);
      L(StringFormat("STEP 4: market SELL %s lots, SL %s", DoubleToString(vol, 2), DoubleToString(sl, dg)));
      bool ok = trade.Sell(vol, sym, 0.0, sl, 0.0, "EXECTEST SELL");
      L(StringFormat("    send: ok=%d retcode=%d (%s) order=%I64u deal=%I64u price=%s volume=%s",
                     ok, trade.ResultRetcode(), trade.ResultRetcodeDescription(), trade.ResultOrder(),
                     trade.ResultDeal(), DoubleToString(trade.ResultPrice(), dg), DoubleToString(trade.ResultVolume(), 2)));
      if(MyPos(sym, d, v, o, s, t, tkt))
      {
         g_ticket = tkt;
         L(StringFormat("    SERVER read-back: %s %.2f lots @ %s  SL=%s TP=%s  => %s", d > 0 ? "BUY" : "SELL", v,
                        DoubleToString(o, dg), DoubleToString(s, dg), DoubleToString(t, dg),
                        (s > 0 ? "SL SET" : "!!! NO SL")));
      }
      else L("    !!! no position found after the send");
      g_step = 5;
      return;
   }
   if(g_step == 5)  // close the SELL + history
   {
      int d; double v, o, s, t; ulong tkt;
      if(MyPos(sym, d, v, o, s, t, tkt))
      {
         bool ok = trade.PositionClose(tkt);
         L("STEP 5: close the SELL at market");
         L(StringFormat("    send: ok=%d retcode=%d (%s)", ok, trade.ResultRetcode(), trade.ResultRetcodeDescription()));
         g_pendingClose = tkt;
         ReportDeals(tkt);
      }
      else L("STEP 5: no position to close");
      g_step = 6;
      return;
   }
   if(g_step == 6)
   {
      int d; double v, o, s, t; ulong tkt;
      L(StringFormat("    STEP 5 verify: the position is %s", MyPos(sym, d, v, o, s, t, tkt) ? "STILL OPEN (!!!)" : "closed"));
      DoPending(sym, 1, false, pt, dg);   // BUY STOP + SL
      g_step = 7;
      return;
   }
   if(g_step == 7) { DoPending(sym, -1, false, pt, dg); g_step = 8; return; }  // SELL STOP + SL
   if(g_step == 8) { DoPending(sym, 1, true, pt, dg); g_step = 9; return; }    // BUY STOP  + SL + TP
   if(g_step == 9) { g_si++; g_step = 0; return; }                             // next symbol
}

// pending stop order: the entry kind the gold EA uses (and the add-on to a winner)
void DoPending(const string sym, const int dir, const bool withTp, const double pt, const int dg)
{
   MqlTick tk;
   if(!SymbolInfoTick(sym, tk)) return;
   double vol  = MathMax(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), InpVolume);
   double dist = MathMax(g_slDist, 10 * (tk.ask - tk.bid));
   double trig = NormalizeDouble(dir > 0 ? tk.ask + dist : tk.bid - dist, dg);
   double sl   = NormalizeDouble(dir > 0 ? trig - g_slDist : trig + g_slDist, dg);
   double tp   = withTp ? NormalizeDouble(dir > 0 ? trig + 2 * g_slDist : trig - 2 * g_slDist, dg) : 0.0;
   L(StringFormat("STEP %d: %s %s lots at %s  SL %s%s", g_step, dir > 0 ? "BUY STOP" : "SELL STOP",
                  DoubleToString(vol, 2), DoubleToString(trig, dg), DoubleToString(sl, dg),
                  (tp > 0 ? ", TP " + DoubleToString(tp, dg) : "")));
   bool ok = (dir > 0) ? trade.BuyStop(vol, trig, sym, sl, tp, ORDER_TIME_GTC, 0, "EXECTEST STOP")
                       : trade.SellStop(vol, trig, sym, sl, tp, ORDER_TIME_GTC, 0, "EXECTEST STOP");
   L(StringFormat("    send: ok=%d retcode=%d (%s) order=%I64u", ok, trade.ResultRetcode(),
                  trade.ResultRetcodeDescription(), trade.ResultOrder()));
   int d; double pr, s, t; ulong o2;
   if(MyOrd(sym, d, pr, s, t, o2))
   {
      L(StringFormat("    SERVER read-back: %s at %s  SL=%s TP=%s => %s, %s",
                     d > 0 ? "BUY STOP" : "SELL STOP", DoubleToString(pr, dg), DoubleToString(s, dg), DoubleToString(t, dg),
                     (s > 0 ? "SL SET" : "!!! NO SL"), (tp > 0 ? (t > 0 ? "TP SET" : "!!! NO TP") : "TP 0 as designed")));
      bool del = trade.OrderDelete(o2);
      L(StringFormat("    cancel: ok=%d retcode=%d (%s) -> still on the server = %s", del, trade.ResultRetcode(),
                     trade.ResultRetcodeDescription(), MyOrd(sym, d, pr, s, t, o2) ? "YES (!!!)" : "no"));
   }
   else L("    !!! the pending order is not on the server");
}

