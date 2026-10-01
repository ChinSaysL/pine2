// Helper for the working copy of the strategy on the TradingView chart.
// Usage: node tv.mjs run <pine file> <out csv> [studyId]   push, recompile, wait, dump metrics + trades
//        node tv.mjs read <out csv> [studyId]              dump metrics + trades without pushing
import { readFileSync, writeFileSync } from 'fs';
import * as pine from 'file:///C:/Users/Abdo/tradingview-mcp/src/core/pine.js';
import { evaluate, disconnect } from 'file:///C:/Users/Abdo/tradingview-mcp/src/connection.js';

const [cmd, a1, a2, a3] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));

const SRC = `window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model().model().dataSources()`;
const byId = id => `(${SRC}).find(function(s){try{return s.id()===${JSON.stringify(id)}}catch(e){return false}})`;

async function status(id) {
  return evaluate(`(function(){var s=${byId(id)};if(!s)return null;var st=s.status();if(st&&st.value)st=st.value();return st})()`);
}

async function waitDone(id) {
  await sleep(2000);
  for (let i = 0; i < 200; i++) {
    const st = await status(id);
    if (st && st.type === 3) return st;          // error
    if (st && st.type === 2) return st;          // completed
    await sleep(3000);
  }
  return { type: -1 };
}

async function dump(id, out) {
  // Report of this instance; wait until it has a performance block.
  let rd = null;
  for (let i = 0; i < 40 && !rd; i++) {
    rd = await evaluate(`(function(){var s=${byId(id)};if(!s)return null;var rd=s.reportData();if(rd&&typeof rd.value==='function')rd=rd.value();if(!rd||!rd.performance)return null;var a=rd.performance.all||{};return {net:a.netProfit,netPct:a.netProfitPercent,pf:a.profitFactor,trades:(a.numberOfWiningTrades||0)+(a.numberOfLosingTrades||0),win:a.percentProfitable,maxDD:rd.performance.maxStrategyDrawDown,maxDDPct:rd.performance.maxStrategyDrawDownPercent,comm:a.commissionPaid}})()`);
    if (!rd) await sleep(3000);
  }
  // Export table rows drawn by this instance.
  const rows = await evaluate(`(function(){var s=${byId(id)};if(!s||!s._graphics)return null;var pc=s._graphics._primitivesCollection;var o=pc.dwgtablecells;if(!o)return null;var c=o.get('tableCells');if(c&&c.get)c=c.get(false);if(!c||!c._primitivesDataById)return null;var t={};c._primitivesDataById.forEach(function(v){var k=v.tid||0;(t[k]=t[k]||{})[v.row]=v.t});var res=null;Object.keys(t).forEach(function(k){if(t[k][0]&&String(t[k][0]).indexOf('entry_time')===0){res=Object.keys(t[k]).map(Number).sort(function(a,b){return a-b}).map(function(r){return t[k][r]})}});return res})()`);
  if (rows) writeFileSync(out, rows.join('\n'));
  console.log(JSON.stringify({ metrics: rd, exportedRows: rows ? rows.length - 1 : null }));
}

try {
  const id = (cmd === 'run' ? a3 : a2) || 'NHpiC9';
  if (cmd === 'run') {
    await pine.setSource({ source: readFileSync(a1, 'utf-8') });
    await sleep(500);
    const clicked = await evaluate(`(function(){var b=Array.from(document.querySelectorAll('button')).filter(x=>x.offsetParent!==null);var u=b.find(x=>/^update on chart$/i.test((x.getAttribute('title')||x.textContent||'').trim()));if(u){u.click();return 'Update on chart'}return null})()`);
    if (!clicked) { console.log('No "Update on chart" button - not pushed'); process.exit(1); }
    await sleep(3000);
    const errs = (await pine.getErrors()).errors.filter(e => e.severity >= 8);
    if (errs.length) { console.log('COMPILE ERRORS', JSON.stringify(errs)); process.exit(1); }
    const st = await waitDone(id);
    if (st.type !== 2) { console.log('STATUS', JSON.stringify(st).slice(0, 600)); process.exit(1); }
    await dump(id, a2);
  } else if (cmd === 'read') {
    const st = await waitDone(id);
    if (st.type !== 2) { console.log('STATUS', JSON.stringify(st).slice(0, 600)); process.exit(1); }
    await dump(id, a1);
  }
} finally {
  await disconnect().catch(() => {});
  process.exit(0);
}
