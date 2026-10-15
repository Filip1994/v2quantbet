/* PKST-V1: append-only route module for the existing Railway Function.
   This module is intentionally isolated from the Research Kelly paths.
   Requires: import { SQL } from "bun" once in the host file. */
const PRODUCTION_START_BANKROLL_MINOR = 3000000; // RSD 30,000.00
const PRODUCTION_ROUND_MINOR = 1000; // RSD 10.00
const PRODUCTION_ROW_LIMIT = 50000;
const PRODUCTION_SQL = [
  "SELECT p.pick_id, p.cloned_at, p.kickoff_at, p.source_universe, p.source_pick_id,",
  " p.home_team, p.away_team, p.market_key, p.selection, p.odds, p.model_probability,",
  " p.market_probability, p.intake_contract_version, p.matched_bucket_ids,",
  " p.bookmaker_name, g.outcome AS goal_outcome, g.settled_at AS goal_settled_at,",
  " c.outcome AS corner_outcome, c.occurred_at AS corner_settled_at,",
  " e.event_kind AS research_event_kind, e.outcome AS research_event_outcome,",
  " e.occurred_at AS research_event_at,",
  " rr.result_classification, rr.regulation_home_goals, rr.regulation_away_goals,",
  " rr.persisted_at AS research_result_at",
  " FROM production_funnel_picks p",
  " LEFT JOIN quantlab_goal_pick_settlements g",
  " ON p.source_universe = 'GOALLAB' AND g.goal_pick_id = p.source_pick_id",
  " LEFT JOIN LATERAL (",
  "   SELECT ce.outcome, ce.occurred_at FROM quantlab_corner_settlement_events ce",
  "   WHERE p.source_universe = 'CORNERLAB' AND ce.shadow_bet_id = p.source_pick_id",
  "   ORDER BY ce.occurred_at DESC, ce.corner_settlement_event_id DESC LIMIT 1",
  " ) c ON TRUE",
  " LEFT JOIN research_signals rs",
  " ON p.source_universe = 'RESEARCH' AND rs.research_signal_id = p.source_pick_id",
  " LEFT JOIN LATERAL (",
  "   SELECT pe.event_kind, pe.outcome, pe.occurred_at FROM pick_settlement_events pe",
  "   WHERE p.source_universe = 'RESEARCH' AND pe.pick_id = rs.production_pick_id",
  "   ORDER BY pe.occurred_at DESC, pe.settlement_event_id DESC LIMIT 1",
  " ) e ON TRUE",
  " LEFT JOIN fixture_result_acquisition_states ras",
  " ON p.source_universe = 'RESEARCH' AND ras.fixture_id = p.source_fixture_id",
  " LEFT JOIN fixture_result_observations rr",
  " ON rr.result_observation_id = ras.current_observation_id",
  " WHERE p.cloned_at >= $1::timestamptz",
  " ORDER BY p.cloned_at ASC, p.pick_id ASC",
  " LIMIT 50001"
].join("\n");

function prodTs(v) {
  if (v == null || v === "") return null;
  const t = new Date(v).getTime();
  return Number.isFinite(t) ? t : null;
}
function prodVal(v) { return v == null ? NaN : Number(v); }
function prodMoney(v) {
  return (Number(v) / 100).toLocaleString("sr-RS", {minimumFractionDigits:2,maximumFractionDigits:2}) + " RSD";
}
function prodPct(v) { return Number.isFinite(v) ? Number(v).toFixed(2)+"%" : "—"; }
function prodEsc(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function prodOutcome(p, asOf) {
  const universe = String(p.source_universe || "");
  let outcome = "PENDING", at = null, reason = "";
  if (universe === "GOALLAB") {
    outcome = String(p.goal_outcome || "PENDING").toUpperCase();
    at = prodTs(p.goal_settled_at);
  } else if (universe === "CORNERLAB") {
    outcome = String(p.corner_outcome || "PENDING").toUpperCase();
    at = prodTs(p.corner_settled_at);
  } else if (universe === "RESEARCH") {
    const eventKind = String(p.research_event_kind || "");
    if (eventKind === "MANUAL_VOID" && p.research_event_outcome === "VOID") {
      outcome = "VOID"; at = prodTs(p.research_event_at);
    } else if (eventKind === "CORRECTION" || eventKind === "REVERSAL") {
      reason = "UNVERIFIED_RESEARCH_CORRECTION_CHAIN";
    } else if (p.result_classification === "NON_PLAYED_VOIDABLE") {
      outcome = "VOID"; at = prodTs(p.research_result_at);
    } else if (p.result_classification === "PLAYED_SETTLEABLE") {
      const home = prodVal(p.regulation_home_goals), away = prodVal(p.regulation_away_goals);
      if (Number.isInteger(home) && Number.isInteger(away) && home >= 0 && away >= 0) {
        let won = null;
        if (p.market_key === "OU_25" && p.selection === "OVER") won = home+away > 2;
        if (p.market_key === "OU_25" && p.selection === "UNDER") won = home+away < 3;
        if (p.market_key === "BTTS" && p.selection === "YES") won = home > 0 && away > 0;
        if (p.market_key === "BTTS" && p.selection === "NO") won = !(home > 0 && away > 0);
        if (won !== null) { outcome = won ? "WIN" : "LOSS"; at = prodTs(p.research_result_at); }
        else reason = "UNSUPPORTED_RESEARCH_MARKET";
      } else reason = "MISSING_GOALS";
    }
  } else reason = "UNKNOWN_SOURCE_UNIVERSE";
  if (!["PENDING", "WIN", "LOSS", "VOID"].includes(outcome)) {
    reason = "UNSUPPORTED_SETTLEMENT_OUTCOME"; outcome = "PENDING"; at = null;
  }
  const kickoff = prodTs(p.kickoff_at);
  if (outcome !== "PENDING" && at === null) {
    reason = "SETTLEMENT_TIME_MISSING"; outcome = "PENDING";
  }
  if (outcome !== "PENDING" && kickoff !== null && at < kickoff && outcome !== "VOID") {
    reason = "PRE_KICKOFF_SETTLEMENT"; outcome = "PENDING"; at = null;
  }
  if (outcome !== "PENDING" && at > asOf) {
    reason = "FUTURE_SETTLEMENT"; outcome = "PENDING"; at = null;
  }
  return {outcome, at, reason};
}
const PRODUCTION_STRATEGIES = [
  {id:"P_FLAT_300",label:"Flat 300 RSD",mode:"flat",cap:0,frac:0},
  {id:"P_FLAT_1PCT",label:"Flat 1% equity",mode:"flatPercent",cap:0.01,frac:0},
  ...[0.25,0.5,1].flatMap(frac => [0.01,0.02,0.03,0.05,0.10].map(cap => ({
    id:"P_K"+(frac*100)+"_C"+(cap*100),label:(frac===0.25?"¼":frac===0.5?"½":"Full")+" Kelly · "+(cap*100)+"% cap",
    mode:"kelly",cap,frac
  })))
];
function prodStake(p, s, equity, available) {
  if (!(equity > 0 && available > 0)) return 0;
  const odds=prodVal(p.odds), probability=prodVal(p.model_probability);
  if (!(odds>1 && Number.isFinite(probability) && probability>=0 && probability<=1)) return 0;
  const fraction=s.mode==="flat"?Math.min(30000,equity)/equity:
    s.mode==="flatPercent"?0.01:Math.min(s.cap,Math.max(0,(odds*probability-1)/(odds-1))*s.frac);
  const desired=equity*fraction;
  const absoluteCap=s.mode==="flat"?equity:s.cap*equity;
  const cap=Math.min(available,absoluteCap);
  return Math.max(0, Math.min(Math.round(desired/PRODUCTION_ROUND_MINOR)*PRODUCTION_ROUND_MINOR,
    Math.floor(cap/PRODUCTION_ROUND_MINOR)*PRODUCTION_ROUND_MINOR));
}
function prodSimulate(rows, s, asOf) {
  let available=PRODUCTION_START_BANKROLL_MINOR,reserved=0,peak=PRODUCTION_START_BANKROLL_MINOR;
  let maxDd=0,settled=0,staked=0,pnl=0,bets=0,blocked=0;
  const allocations=[];
  function settle(cutoff, inclusive) {
    const due=allocations.filter(a => !a.paid && a.outcome !== "PENDING" && a.settledAt != null &&
      (inclusive ? a.settledAt <= cutoff : a.settledAt < cutoff))
      .sort((a,b)=>a.settledAt-b.settledAt || a.id.localeCompare(b.id));
    for (const a of due) {
      const gain=a.outcome==="WIN"?Math.round(a.stake*(a.odds-1)):
        a.outcome==="LOSS"?-a.stake:0;
      available += a.stake+gain;
      reserved -= a.stake;
      pnl+=gain;if(a.stake>0){staked+=a.stake;settled++;}a.pnl=gain;a.paid=true;
      const equity=available+reserved;
      peak=Math.max(peak,equity);
      if (peak>0) maxDd=Math.max(maxDd,(peak-equity)/peak);
      if (available<0 || reserved<0) throw Error("PKST CASH_LEDGER_NEGATIVE");
    }
  }
  for (const p of rows) {
    const at=prodTs(p.cloned_at), kickoff=prodTs(p.kickoff_at);
    if (at===null || kickoff===null) throw Error("PKST MISSING_CANONICAL_TIMESTAMP");
    settle(at,false);
    const equity=available+reserved;
    let reason="",stake=0;
    if (at>=kickoff) reason="AFTER_KICKOFF";
    else if (!(prodVal(p.odds)>1 && prodVal(p.model_probability)>=0 && prodVal(p.model_probability)<=1))
      reason="INVALID_ENTRY_ODDS_OR_PROBABILITY";
    else if (p._result.at!==null && p._result.at<=at)
      reason="RESULT_ALREADY_KNOWN";
    else {
      stake=prodStake(p,s,equity,available);
      if (!stake) {
        const desired=prodStake(p,s,equity,equity);
        reason=desired>0?"INSUFFICIENT_CASH":"NO_POSITIVE_EDGE_OR_TOO_SMALL";
      }
    }
    available-=stake;reserved+=stake;
    if (stake>0) bets++;if (reason==="INSUFFICIENT_CASH") blocked++;
    allocations.push({id:String(p.pick_id),at,kickoff,
      policy:String(p.intake_contract_version),source:String(p.source_universe),
      odds:prodVal(p.odds),stake,reason,settledAt:p._result.at,
      outcome:p._result.outcome,pnl:null,paid:false,
      home:String(p.home_team||""),away:String(p.away_team||""),
      market:String(p.market_key||""),selection:String(p.selection||"")});
  }
  settle(asOf,true);
  const equity=available+reserved;
  const expectedOpen=allocations.filter(a=>!a.paid).reduce((x,a)=>x+a.stake,0);
  if (available<0 || reserved<0 || reserved!==expectedOpen ||
      Math.abs(equity-(PRODUCTION_START_BANKROLL_MINOR+pnl))>1)
    throw Error("PKST CASH_RECONCILIATION_FAILED");
  const policies={};
  for (const a of allocations) {
    const z=policies[a.policy]||(policies[a.policy]={picks:0,bets:0,settled:0,pnl_minor:0});
    z.picks++; if (a.stake>0) z.bets++;if(a.paid&&a.stake>0){z.settled++;z.pnl_minor+=a.pnl;}
  }
  return {strategy_id:s.id,label:s.label,mode:s.mode,fraction:s.frac,cap:s.cap,
    candidate_count:rows.length,bet_count:bets,settled_count:settled,no_bet_count:rows.length-bets,
    cash_blocked_count:blocked,pnl_minor:pnl,terminal_bankroll_minor:equity,
    available_bankroll_minor:available,reserved_bankroll_minor:reserved,
    return_pct:100*pnl/PRODUCTION_START_BANKROLL_MINOR,
    stake_roi_pct:staked?100*pnl/staked:null,max_drawdown_pct:100*maxDd,
    by_policy:policies,allocations};
}
async function productionTournament() {
  const start=String(Bun.env.PRODUCTION_KELLY_START_AT||"");
  const startMs=prodTs(start);
  const asOf=Date.now();
  if (!start || startMs===null || startMs>asOf) throw Error("PKST START_DATE_INVALID");
  if (!Bun.env.DATABASE_URL) throw Error("PKST DATABASE_URL_NOT_CONFIGURED");
  const db=new SQL(Bun.env.DATABASE_URL);
  let raw;
  try { raw=await db.unsafe(PRODUCTION_SQL,[new Date(startMs).toISOString()]); }
  finally { await db.close(); }
  if (!Array.isArray(raw)) throw Error("PKST INVALID_SOURCE_ROWS");
  if (raw.length>PRODUCTION_ROW_LIMIT) throw Error("PKST SCAN_EXCEEDS_CONTRACT_LIMIT");
  const ids=new Set(),issues=[];
  const rows=raw.map(p=>{
    const id=String(p.pick_id||"");
    if (!id || ids.has(id)) throw Error("PKST DUPLICATE_OR_EMPTY_PRODUCTION_PICK_ID");
    ids.add(id);
    if (!String(p.intake_contract_version||"")) throw Error("PKST MISSING_FROZEN_INTAKE_POLICY");
    if (prodTs(p.cloned_at)===null || prodTs(p.kickoff_at)===null) throw Error("PKST INVALID_ENTRY_TIME");
    const result=prodOutcome(p,asOf);
    if (result.reason) issues.push({pick_id:id,reason:result.reason,
      source_universe:p.source_universe,policy:p.intake_contract_version});
    return {...p,_result:result};
  });
  const results=PRODUCTION_STRATEGIES.map(s=>prodSimulate(rows,s,asOf))
    .sort((a,b)=>b.return_pct-a.return_pct || a.max_drawdown_pct-b.max_drawdown_pct);
  results.forEach((r,i)=>r.rank=i+1);
  const policyCounts={};
  for(const p of rows){const k=String(p.intake_contract_version);policyCounts[k]=(policyCounts[k]||0)+1;}
  return {contract:"PKST-V1",source:"production_funnel_picks",mode:"PROSPECTIVE_PRODUCTION_INTAKE_REPLAY",
    accounting_status:"PROVISIONAL_LATEST_SETTLEMENT_REPLAY",
    disclaimer:"Shadow simulation only; latest-source settlement corrections can change a replayed historic stake until immutable allocation/settlement ledger is added. Not real bookmaker execution.",
    started_at:new Date(startMs).toISOString(),generated_at:new Date(asOf).toISOString(),
    source_candidate_count:rows.length,policy_counts:policyCounts,
    source_issue_count:issues.length,source_issues:issues,
    starting_bankroll_minor:PRODUCTION_START_BANKROLL_MINOR,
    rounding_minor:PRODUCTION_ROUND_MINOR,
    results};
}
function productionHtml(t){
  const rows=t.results.map(r=>'<tr><td>#'+r.rank+'</td><td><b>'+prodEsc(r.label)+
    '</b><small>'+prodEsc(r.strategy_id)+'</small></td><td class="'+(r.pnl_minor>=0?"ok":"bad")+'">'+prodMoney(r.pnl_minor)+
    '</td><td>'+prodPct(r.return_pct)+'</td><td>'+prodPct(r.stake_roi_pct)+
    '</td><td>'+prodPct(r.max_drawdown_pct)+'</td><td>'+r.bet_count+
    '</td><td>'+r.settled_count+'</td><td>'+prodMoney(r.reserved_bankroll_minor)+'</td></tr>').join("");
  const policies=Object.entries(t.policy_counts).map(([k,v])=>'<tr><td>'+prodEsc(k)+'</td><td>'+v+'</td></tr>').join("");
  const flat=t.results.find(r=>r.strategy_id==="P_FLAT_300");
  const k10=t.results.find(r=>r.strategy_id==="P_K25_C10");
  const k2=t.results.find(r=>r.strategy_id==="P_K25_C2");
  const recentRows=(flat?flat.allocations:[]).slice(-30).reverse().map(a=>{
    const s10=k10.allocations.find(x=>x.id===a.id),s2=k2.allocations.find(x=>x.id===a.id);
    return '<tr><td>'+prodEsc(new Date(a.at).toISOString())+'</td><td><b>'+prodEsc(a.home)+' – '+prodEsc(a.away)+
      '</b><small>'+prodEsc(a.source)+' · '+prodEsc(a.market)+' '+prodEsc(a.selection)+' @ '+a.odds+'</small></td><td>'+prodEsc(a.outcome)+
      '</td><td>'+prodMoney(s2.stake)+'<small>'+prodEsc(s2.reason||'BET')+'</small></td><td>'+prodMoney(s10.stake)+
      '<small>'+prodEsc(s10.reason||'BET')+'</small></td><td>'+prodEsc(a.policy)+'</td></tr>';
  }).join("");
  return '<!doctype html><html lang="sr"><head><meta charset="utf-8">'+
    '<meta name="viewport" content="width=device-width,initial-scale=1">'+
    '<title>QuantBet · Production Kelly Tournament</title>'+
    '<style>body{margin:0;background:#101821;color:#e7eff7;font:14px system-ui,sans-serif}main{max-width:1350px;margin:auto;padding:22px}a{color:#71cfff}small{display:block;color:#9eafc2;font-size:11px;margin:4px 0}h1{font-size:28px}h2{font-size:18px}section{margin:18px 0;padding:16px;border:1px solid #29445e;border-radius:12px;background:#142333}table{width:100%;border-collapse:collapse;min-width:730px}td,th{padding:10px;border-bottom:1px solid #2c435a;text-align:left}th{color:#a4c5da;font-size:11px}div.scroll{overflow:auto}.ok{color:#73d79a}.bad{color:#f08a95}.warning{color:#fbc96c}.nav{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px}.kpis{display:flex;gap:20px;flex-wrap:wrap}.kpis strong{font-size:20px;display:block}code{overflow-wrap:anywhere}</style></head><body><main>'+
    '<nav class="nav"><a href="https://quantbet-dashboard-production.up.railway.app/hub">⌂ Hub</a>'+
    '<a href="/kelly-tournament">Research Tournament</a>'+
    '<a href="/production-kelly-tournament.json">Production JSON</a></nav>'+
    '<small>PKST-V1 · PROSPECTIVE SHADOW · '+prodEsc(t.generated_at)+'</small>'+
    '<h1>Production Kelly Strategy Tournament</h1>'+
    '<p>Jedini izvor selekcije: <code>production_funnel_picks</code>. Bez ponovne primene bucket filtera. Svih 17 strategija vidi iste Production kandidature od '+prodEsc(t.started_at)+'.</p>'+
    '<section><div class="kpis"><span><small>Production candidates</small><strong>'+t.source_candidate_count+
    '</strong></span><span><small>Strategy count</small><strong>'+t.results.length+
    '</strong></span><span><small>Start bankroll</small><strong>'+prodMoney(t.starting_bankroll_minor)+
    '</strong></span><span><small>Source audit issues</small><strong>'+t.source_issue_count+
    '</strong></span></div></section>'+
    '<p class="warning"><b>PROVISIONAL REPLAY:</b> Rezultati su simulacija, ne stvarne opklade. Naknadne korekcije settlementa mogu promeniti rekonstruisane istorijske uloge dok ne postoji trajni append-only ledger.</p>'+
    '<section><h2>Rang lista</h2><div class="scroll"><table><thead><tr><th>#</th><th>Staking</th><th>P/L</th><th>Return</th><th>Stake ROI</th><th>Max DD</th><th>Bets</th><th>Settled</th><th>Reserved</th></tr></thead><tbody>'+
    rows+'</tbody></table></div></section>'+
    '<section><h2>Latest 30 Production picks</h2><p>Isti kandidati, različita veličina uloga; svako polje čuva izvorni Production policy ID.</p><div class="scroll"><table><thead><tr><th>Clone UTC</th><th>Match / market</th><th>Source result</th><th>¼ Kelly 2%</th><th>¼ Kelly 10%</th><th>Intake policy</th></tr></thead><tbody>'+recentRows+'</tbody></table></div></section>'+
    '<section><h2>Production intake policy versions</h2><p>Istorijski pikovi ostaju vezani za verziju politike pri kloniranju, bez retroaktivnog rerangiranja.</p>'+
    '<div class="scroll"><table><thead><tr><th>Frozen intake contract version</th><th>Candidates</th></tr></thead><tbody>'+
    policies+'</tbody></table></div></section>'+
    '<p>17 strategija: Flat 300 RSD, Flat 1% equity, te ¼ Kelly, ½ Kelly i Full Kelly sa 1/2/3/5/10% cap; sve koriste isti immutable Production model_probability. NO_BET zbog rizika ili gotovine nije eliminacija ulaznog kandidata.</p>'+
    '<p>Ovaj endpoint ne utiče na Production, Research, KellyLab, njegove postojeće rute ili actual betting.</p>'+
    '</main></body></html>';
}
