import { SQL } from "bun";

type Row = Record<string, any>;
type Strategy = {id:string; label:string; pMode:string; frac:number; cap:number; bucket:string; flat?:number; directBucket?:boolean};

const SOURCE = "https://quantbet-kellylab-production.up.railway.app/kellylab.json";
const HUB_LINK = '<a id="quantbet-hub-return" href="https://quantbet-dashboard-production.up.railway.app/hub" aria-label="Vrati se na QuantBet Hub" style="position:fixed;z-index:2147483647;right:max(12px,env(safe-area-inset-right));bottom:max(12px,env(safe-area-inset-bottom));display:flex;align-items:center;justify-content:center;min-width:88px;min-height:46px;padding:10px 16px;border-radius:999px;background:#10d7b0;color:#06241f;box-shadow:0 6px 24px #0009;font:700 15px/1.2 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;text-decoration:none">⌂ Hub</a>';
function withHubReturn(body:string){ return body.replace('</body>',HUB_LINK+'</body>'); }
const S: Strategy[] = [
  {id:"FLAT_300",label:"Flat 300",pMode:"flat",frac:0,cap:0,bucket:"none",flat:30000},
  {id:"MODEL_Q25_C1",label:"Model · ¼ Kelly · 1%",pMode:"model",frac:.25,cap:.01,bucket:"none"},
  {id:"MODEL_Q25_C2",label:"Model · ¼ Kelly · 2%",pMode:"model",frac:.25,cap:.02,bucket:"none"},
  {id:"MODEL_Q25_C5",label:"Model · ¼ Kelly · 5%",pMode:"model",frac:.25,cap:.05,bucket:"none"},
  {id:"MODEL_Q50_C2",label:"Model · ½ Kelly · 2%",pMode:"model",frac:.50,cap:.02,bucket:"none"},
  {id:"CAL_Q25_C1",label:"Calibrated · ¼ Kelly · 1%",pMode:"cal",frac:.25,cap:.01,bucket:"none"},
  {id:"CAL_Q25_C2",label:"Calibrated · ¼ Kelly · 2%",pMode:"cal",frac:.25,cap:.02,bucket:"none"},
  {id:"CAL_Q25_C3",label:"Calibrated · ¼ Kelly · 3%",pMode:"cal",frac:.25,cap:.03,bucket:"none"},
  {id:"CAL_Q25_C5",label:"Calibrated · ¼ Kelly · 5%",pMode:"cal",frac:.25,cap:.05,bucket:"none"},
  {id:"CAL_Q25_C10",label:"Calibrated · ¼ Kelly · 10%",pMode:"cal",frac:.25,cap:.10,bucket:"none"},
  {id:"CAL_Q50_C2",label:"Calibrated · ½ Kelly · 2%",pMode:"cal",frac:.50,cap:.02,bucket:"none"},
  {id:"BUCKET_SOFT_Q25_C2",label:"Bucket soft · ¼ Kelly · 2%",pMode:"cal",frac:.25,cap:.02,bucket:"soft"},
  {id:"BUCKET_HARD_Q25_C2",label:"Bucket hard · ¼ Kelly · 2%",pMode:"cal",frac:.25,cap:.02,bucket:"hard"},
  {id:"BUCKET_DIRECT_C2",label:"Bucket direct · 2%",pMode:"cal",frac:0,cap:.02,bucket:"direct",directBucket:true},
  {id:"BUCKET_DIRECT_C3",label:"Bucket direct · 3%",pMode:"cal",frac:0,cap:.03,bucket:"direct",directBucket:true},
  {id:"BUCKET_DIRECT_C5",label:"Bucket direct · 5%",pMode:"cal",frac:0,cap:.05,bucket:"direct",directBucket:true},
  {id:"CAL_MINUS2_Q25_C2",label:"Calibrated −2pp · ¼ Kelly · 2%",pMode:"minus2",frac:.25,cap:.02,bucket:"none"}
];

const STAKE_ROUND_STEP_MINOR = 1000; // 10 RSD: accounting values use minor units.
function roundedStake(rawMinor:number,maxMinor:number,stepMinor:number){
  if(!Number.isFinite(rawMinor)||!Number.isFinite(maxMinor)||rawMinor<=0||maxMinor<=0) return 0;
  if(stepMinor===0) return Math.max(0,Math.min(Math.round(rawMinor),Math.floor(maxMinor))); // exact unit, still strictly cash-capped
  const nearest=Math.round(rawMinor/stepMinor)*stepMinor;
  const maxRounded=Math.floor(maxMinor/stepMinor)*stepMinor;
  return Math.max(0,Math.min(nearest,maxRounded)); // never exceed bankroll or strategy cap
}
function d(v:any){ if(v==null||v==="") return null; const x=new Date(v); return isNaN(x.getTime())?null:x; }
function rawKelly(o:number,p:number){ return Math.max(0,(o*p-1)/(o-1)); }
function pnl(stake:number,odds:number,outcome:string){
  if(outcome==="PENDING") return null;
  if(outcome==="VOID") return 0;
  if(outcome==="LOSS") return -stake;
  return Math.round(stake*(odds-1));
}
function bucketQuality(r:Row){
  const dims=r.calibration_snapshot?.dimensions||[];
  const scores:number[]=[];
  const odds=Number(r.odds), breakeven=1/odds;
  for(const x of dims){
    const n=Number(x.n||0);
    const wr=x.win_rate==null?null:Number(x.win_rate);
    if(!(n>0)||wr==null) continue;
    const evidence=n/(n+150);
    const empiricalEdge=Math.max(0,wr-breakeven);
    const edgeScore=Math.min(1,empiricalEdge/.20);
    scores.push(evidence*edgeScore);
  }
  return scores.length?scores.reduce((a,b)=>a+b,0)/scores.length:0;
}
function prob(r:Row,mode:string){
  if(mode==="model") return Number(r.model_probability);
  if(mode==="cal") return Number(r.kelly_probability);
  if(mode==="minus2") return Math.max(Number(r.market_fair_probability),Number(r.kelly_probability)-.02);
  return 0;
}
function plan(r:Row,s:Strategy,bank:number,roundStep:number){
  if(s.flat!=null){
    const intended=Math.min(s.flat,bank);
    const stake=roundedStake(intended,bank,roundStep);
    return {stake,raw_stake_minor:Math.round(intended),rounding_delta_minor:stake-Math.round(intended),
      quality:1,applied:bank?stake/bank:0,p:null,decision:stake>0?"BET":"NO_BET"};
  }
  const p=prob(r,s.pMode), raw=rawKelly(Number(r.odds),p), q=bucketQuality(r);
  let applied:number;
  if(s.directBucket){
    applied=s.cap*q;
  } else {
    const mult=s.bucket==="soft"?.25+.75*q:s.bucket==="hard"?q:1;
    applied=Math.min(raw*s.frac*mult,s.cap);
  }
  const rawStake=(applied>0&&bank>0)?Math.round(bank*applied):0;
  const stake=roundedStake(rawStake,Math.min(bank,bank*s.cap),roundStep);
  return {stake,raw_stake_minor:rawStake,rounding_delta_minor:stake-rawStake,
    quality:q,applied:bank?stake/bank:0,p,decision:stake>0?"BET":"NO_BET"};
}
function simulate(rows:Row[],start:number,s:Strategy,roundStep:number){
  const ordered=[...rows].sort((a,b)=>(d(a.source_decision_at)?.getTime()||0)-(d(b.source_decision_at)?.getTime()||0));
  const alloc:any[]=[];
  for(const r of ordered){
    const cut=d(r.source_decision_at)?.getTime()||0;
    let realized=0;
    for(const a of alloc){
      const acq=d(a.result_first_acquired_at)?.getTime();
      if(acq!=null&&acq<cut) realized+=Number(a.pnl||0);
    }
    const bank=Math.max(1,start+realized), z=plan(r,s,bank,roundStep);
    alloc.push({...z, id:r.kelly_pick_id, outcome:r.outcome, odds:Number(r.odds),
      result_first_acquired_at:r.result_first_acquired_at, source_decision_at:r.source_decision_at, pnl:pnl(z.stake,Number(r.odds),r.outcome),
      home:r.home_team,away:r.away_team,market:r.market,selection:r.selection});
  }
  const settled=alloc.filter(a=>a.pnl!=null);
  const totalPnl=settled.reduce((a,x)=>a+Number(x.pnl||0),0);
  const staked=settled.reduce((a,x)=>a+Number(x.stake||0),0);
  let bal=start,peak=start,maxdd=0;
  for(const a of [...settled].sort((x,y)=>(d(x.result_first_acquired_at)?.getTime()||9e15)-(d(y.result_first_acquired_at)?.getTime()||9e15))){
    bal+=Number(a.pnl||0); peak=Math.max(peak,bal); if(peak>0) maxdd=Math.max(maxdd,(peak-bal)/peak);
  }
  const bets=alloc.filter(a=>a.decision==="BET");
  return {
    strategy_id:s.id,label:s.label,pick_count:alloc.length,bet_count:bets.length,no_bet_count:alloc.length-bets.length,
    settled_count:settled.length,pnl_minor:totalPnl,terminal_bankroll_minor:start+totalPnl,return_pct:totalPnl/start*100,
    staking_roi_pct:staked?totalPnl/staked*100:null,max_drawdown_pct:maxdd*100,
    avg_stake_minor:bets.length?Math.round(bets.reduce((a,x)=>a+x.stake,0)/bets.length):0,
    max_stake_minor:Math.max(0,...alloc.map(a=>a.stake)),open_stake_minor:alloc.filter(a=>a.outcome==="PENDING").reduce((a,x)=>a+x.stake,0),
    allocations:alloc
  };
}

/** Cash-backed replay, chronological by actual pick materialization time.
 * Capital is not reused while a pick is open. A timestamped result
 * returns the stake plus payout only when the source's durable settlement
 * event has been confirmed. Result observations alone do not release cash.
 */
function simulateCashBacked(rows:Row[],start:number,s:Strategy,roundStep:number,asOf:number){
  const ordered=[...rows].sort((a,b)=>
    (d(a.materialized_at)?.getTime()??Number.POSITIVE_INFINITY)-(d(b.materialized_at)?.getTime()??Number.POSITIVE_INFINITY)
    ||(d(a.source_decision_at)?.getTime()??Number.POSITIVE_INFINITY)-(d(b.source_decision_at)?.getTime()??Number.POSITIVE_INFINITY)
    ||String(a.kelly_pick_id).localeCompare(String(b.kelly_pick_id)));
  const alloc:any[]=[];
  let available=start, reserved=0, peak=start, maxdd=0, maxReserved=0, maxConcurrent=0, realizedPnl=0;
  const settle=(cutoff:number,inclusive:boolean)=>{
    const eligible=alloc.flatMap(a=>(a.settlement_events||[])
      .slice(a.event_cursor||0).filter((e:any)=>{
        const t=d(e.occurred_at)?.getTime();
        return t!=null&&t<=asOf&&(inclusive?t<=cutoff:t<cutoff);
      }).map((e:any,sequence:number)=>({a,e,sequence}))
    ).sort((x,y)=>(d(x.e.occurred_at)?.getTime()||0)-(d(y.e.occurred_at)?.getTime()||0)
      ||String(x.a.id).localeCompare(String(y.a.id))
      ||x.sequence-y.sequence);
    for(const {a,e} of eligible){
      const kind=String(e.event_kind||"");
      const outcome=String(e.outcome||"PENDING");
      if(kind==="REVERSAL"){
        if(!a.settled)throw Error("Reversal without prior cash settlement: "+a.id);
        available-=a.stake+a.pnl;reserved+=a.stake;realizedPnl-=a.pnl;
        a.settled=false;a.outcome="PENDING";a.pnl=null;
        maxReserved=Math.max(maxReserved,reserved);
      }else{
        if(!["NORMAL","CORRECTION","MANUAL_VOID"].includes(kind)||!["WIN","LOSS","VOID"].includes(outcome))
          throw Error("Unsupported event in settlement chain: "+a.id+" / "+kind);
        const profit=pnl(a.stake,a.odds,outcome);
        if(profit==null)throw Error("Unpriced settlement");
        if(!a.settled){
          reserved-=a.stake;available+=a.stake+profit;realizedPnl+=profit;
        }else{
          available+=profit-a.pnl;realizedPnl+=profit-a.pnl;
        }
        a.settled=true;a.outcome=outcome;a.pnl=profit;
      }
      if(reserved<0||available<0)throw Error("Cash ledger negative after event: "+a.id+" / "+kind);
      a.event_cursor++;
      a.last_processed_event_at=e.occurred_at;
      a.available_after_settlement_minor=available;
      a.reserved_after_settlement_minor=reserved;
      a.bankroll_after_settlement_minor=available+reserved;
      const equity=available+reserved;
      peak=Math.max(peak,equity);
      if(peak>0)maxdd=Math.max(maxdd,(peak-equity)/peak);
    }
  };
  for(const r of ordered){
    const decisionAt=d(r.source_decision_at)?.getTime();
    const cut=d(r.materialized_at)?.getTime();
    if(decisionAt==null||cut==null)throw Error("Decision or materialization timestamp absent: "+r.kelly_pick_id);
    if(decisionAt>cut)throw Error("Decision follows materialization: "+r.kelly_pick_id);
    if(cut>asOf)continue;
    settle(cut,false);
    const equity=available+reserved;
    if(available<0||reserved<0||equity<0)throw Error("Cash ledger negative before placement");
    const beforeAvailable=available,beforeReserved=reserved;
    const proposed=plan(r,s,equity,roundStep);
    const kickoff=d(r.kickoff_at)?.getTime();
    const firstResult=d(r.result_first_acquired_at)?.getTime();
    const afterKickoff=kickoff!=null&&cut>=kickoff;
    const knownResult=firstResult!=null&&firstResult<=cut;
    const stake=(afterKickoff||knownResult)?0:roundedStake(proposed.stake,available,roundStep);
    const z={...proposed,stake,decision:stake>0?"BET":"NO_BET",
      desired_stake_minor:proposed.stake,applied:equity?stake/equity:0,
      no_bet_reason:stake?"":afterKickoff?"AFTER_KICKOFF":knownResult?"RESULT_ALREADY_KNOWN":proposed.stake>0?"INSUFFICIENT_AVAILABLE_CASH":"NO_EDGE_OR_TOO_SMALL"};
    reserved+=stake;available-=stake;
    const settlementKind=String(r.settlement_event_kind||"");
    if(settlementKind&&!["NORMAL","MANUAL_VOID","CORRECTION","REVERSAL"].includes(settlementKind))
      throw Error("Unsupported settlement event for "+r.kelly_pick_id+": "+settlementKind);
    // A correction replaces the effective final outcome, but its recorded date
    // does not represent the original cash-release time: mark replay provisional.
    // A reversal has NULL outcome by contract: do not invent a settled P/L.
    const sourceOutcome=settlementKind==="MANUAL_VOID"?"VOID":
      (settlementKind==="NORMAL"||settlementKind==="CORRECTION")?String(r.settlement_event_outcome):"PENDING";
    if(settlementKind&&(!d(r.settlement_occurred_at)||(settlementKind!=="REVERSAL"&&!["WIN","LOSS","VOID"].includes(sourceOutcome))))
      throw Error("Incomplete confirmed settlement for "+r.kelly_pick_id);
    if((settlementKind==="NORMAL"||settlementKind==="CORRECTION")&&sourceOutcome!==String(r.outcome))
      throw Error("Confirmed settlement conflicts with result observation for "+r.kelly_pick_id);
    const chain=Array.isArray(r.settlement_event_chain)?r.settlement_event_chain:[];
    const events=chain.length?chain:(settlementKind&&r.settlement_occurred_at
      ?[{settlement_event_id:"legacy:"+r.kelly_pick_id,event_kind:settlementKind,
          outcome:sourceOutcome==="PENDING"?null:sourceOutcome,occurred_at:r.settlement_occurred_at}]:[]);
    alloc.push({...z,id:r.kelly_pick_id,odds:Number(r.odds),
      outcome:"PENDING",source_outcome:sourceOutcome,settled:false,pnl:null,
      settlement_events:events,event_cursor:0,
      result_first_acquired_at:r.result_first_acquired_at,settlement_occurred_at:r.settlement_occurred_at,
      settlement_event_kind:settlementKind||null,source_decision_at:r.source_decision_at,
      materialized_at:r.materialized_at,kickoff_at:r.kickoff_at,
      bankroll_before_minor:equity,available_before_minor:beforeAvailable,reserved_before_minor:beforeReserved,
      available_after_placement_minor:available,reserved_after_placement_minor:reserved,
      home:r.home_team,away:r.away_team,market:r.market,selection:r.selection});
    if(available<0||reserved<0)throw Error("Cash ledger negative after placement");
    maxReserved=Math.max(maxReserved,reserved);
    maxConcurrent=Math.max(maxConcurrent,alloc.filter(a=>a.stake>0&&!a.settled).length);
  }
  settle(asOf,true);
  const settled=alloc.filter(a=>a.settled);
  const staked=settled.reduce((x,a)=>x+a.stake,0);
  const totalPnl=settled.reduce((x,a)=>x+Number(a.pnl||0),0);
  const bets=alloc.filter(a=>a.stake>0);
  const equity=available+reserved;
  if(Math.abs(equity-(start+totalPnl))>1||Math.abs(totalPnl-realizedPnl)>1)throw Error("Profit/bankroll reconciliation failed");
  const openExposure=alloc.filter(a=>a.stake>0&&!a.settled).reduce((x,a)=>x+a.stake,0);
  if(openExposure!==reserved)throw Error("Reserved cash does not equal open stake liability");
  return {
    strategy_id:s.id,label:s.label,bankroll_model:"CASH_RESERVED_V1",
    pick_count:alloc.length,bet_count:bets.length,no_bet_count:alloc.length-bets.length,
    settled_count:settled.length,pnl_minor:totalPnl,
    terminal_bankroll_minor:equity,equity_bankroll_minor:equity,
    available_bankroll_minor:available,reserved_bankroll_minor:reserved,
    return_pct:start?totalPnl/start*100:null,staking_roi_pct:staked?totalPnl/staked*100:null,
    max_drawdown_pct:maxdd*100,
    avg_stake_minor:bets.length?Math.round(bets.reduce((x,a)=>x+a.stake,0)/bets.length):0,
    max_stake_minor:Math.max(0,...alloc.map(a=>a.stake)),
    open_stake_minor:reserved,max_open_stake_minor:maxReserved,max_concurrent_open_bets:maxConcurrent,
    cash_blocked_count:alloc.filter(a=>a.no_bet_reason==="INSUFFICIENT_AVAILABLE_CASH").length,
    after_kickoff_rejected_count:alloc.filter(a=>a.no_bet_reason==="AFTER_KICKOFF").length,
    already_known_result_rejected_count:alloc.filter(a=>a.no_bet_reason==="RESULT_ALREADY_KNOWN").length,
    unavailable_settlement_time_count:alloc.filter(a=>a.source_outcome!=="PENDING"&&!a.settled).length,
    allocations:alloc
  };
}

function hasCompleteSettlementChain(r:Row){
  const events=r.settlement_event_chain;
  if(!Array.isArray(events)||events.length===0)return false;
  let prev:any=null;
  const ids=new Set<string>();
  const kickoff=d(r.current_kickoff_at||r.kickoff_at)?.getTime();
  for(const e of events){
    const id=String(e.settlement_event_id||"");
    const eventAt=d(e.occurred_at)?.getTime();
    if(!id||ids.has(id)||eventAt==null)return false;
    if(["WIN","LOSS"].includes(String(e.outcome||""))&&kickoff!=null&&eventAt<kickoff)return false;
    if(prev){
      if(String(e.prior_event_id||"")!==String(prev.settlement_event_id))return false;
      if((d(e.occurred_at)?.getTime()||0)<(d(prev.occurred_at)?.getTime()||0))return false;
    }else if(e.prior_event_id!=null)return false;
    ids.add(id);prev=e;
  }
  const last=events[events.length-1];
  return String(last.event_kind||"")===String(r.settlement_event_kind||"")
    &&String(last.outcome||"")===String(r.settlement_event_outcome||"")
    &&d(last.occurred_at)?.getTime()===d(r.settlement_occurred_at)?.getTime();
}

async function tournament(roundStep:number,bankrollMode:'real'|'legacy'='real'){
  const res=await fetch(SOURCE,{headers:{"accept":"application/json"}});
  if(!res.ok) throw new Error("KellyLab source HTTP "+res.status);
  const p:any=await res.json();
  const start=Number(p.portfolio.starting_bankroll_minor);
  if(bankrollMode==="real"&&(p.picks||[]).some((r:any)=>!("settlement_event_kind" in r)||!("settlement_occurred_at" in r)))
    throw Error("KellyLab source lacks confirmed settlement fields");
  // Confirmed cash-ledger settlement is the accounting authority. Keep the
  // observed disagreement visible for audit instead of aborting every view.
  const settlementConflicts:any[]=[];
  const asOf=Date.now();
  const settlementRows=(p.picks||[]).map((r:any)=>{
    const kind=String(r.settlement_event_kind||"");
    const confirmed=String(r.settlement_event_outcome||"");
    const observed=String(r.outcome||"PENDING");
    const kickoffMs=d(r.current_kickoff_at||r.kickoff_at)?.getTime();
    // A non-void result booked before a fixture even kicks off is not a
    // confirmed sports outcome. Quarantine it in the shadow replay; never
    // rewrite or erase the original source settlement evidence.
    const bookedMs=d(r.settlement_occurred_at)?.getTime();
    if(kickoffMs!=null&&(kickoffMs>asOf||(bookedMs!=null&&bookedMs<kickoffMs))
       &&kind!=="MANUAL_VOID"&&["WIN","LOSS"].includes(confirmed)){
      settlementConflicts.push({
        kelly_pick_id:r.kelly_pick_id,home_team:r.home_team,away_team:r.away_team,
        market:r.market,selection:r.selection,event_kind:kind,
        audit_reason:"PRE_KICKOFF_SETTLEMENT_QUARANTINED",
        confirmed_outcome:confirmed,observed_outcome:observed,
        kickoff_at:r.kickoff_at,current_kickoff_at:r.current_kickoff_at,
        settlement_occurred_at:r.settlement_occurred_at
      });
      return {...r,outcome:"PENDING",settlement_event_kind:null,
        settlement_event_outcome:null,settlement_occurred_at:null,settlement_event_chain:[]};
    }
    if((kind==="CORRECTION"||kind==="REVERSAL")&&hasCompleteSettlementChain(r)){
      return {...r,outcome:kind==="REVERSAL"?"PENDING":confirmed};
    }
    if(kind==="REVERSAL"){
      settlementConflicts.push({
        kelly_pick_id:r.kelly_pick_id,home_team:r.home_team,away_team:r.away_team,
        market:r.market,selection:r.selection,
        event_kind:kind,audit_reason:"REVERSAL_CASH_TIMELINE_UNAVAILABLE",
        confirmed_outcome:"PENDING",observed_outcome:observed,
        settlement_occurred_at:r.settlement_occurred_at
      });
      return {...r,outcome:"PENDING",settlement_event_kind:null,
        settlement_event_outcome:null,settlement_occurred_at:null,settlement_event_chain:[]};
    }
    if(kind==="CORRECTION"||(kind==="NORMAL"&&["WIN","LOSS","VOID"].includes(confirmed)&&confirmed!==observed)){
      settlementConflicts.push({
        kelly_pick_id:r.kelly_pick_id,home_team:r.home_team,away_team:r.away_team,
        market:r.market,selection:r.selection,
        event_kind:kind,
        audit_reason:kind==="CORRECTION"?"CORRECTION_CASH_TIMELINE_UNAVAILABLE":"SETTLEMENT_OBSERVATION_CONFLICT",
        confirmed_outcome:confirmed,observed_outcome:observed,
        settlement_occurred_at:r.settlement_occurred_at,
        result_first_acquired_at:r.result_first_acquired_at
      });
      if(kind==="CORRECTION")return {...r,outcome:"PENDING",settlement_event_kind:null,
        settlement_event_outcome:null,settlement_occurred_at:null,settlement_event_chain:[]};
      return {...r,outcome:confirmed};
    }
    return r;
  });
  const results=S.map(s=>bankrollMode==="real"?simulateCashBacked(settlementRows,start,s,roundStep,asOf):simulate(p.picks||[],start,s,roundStep)).sort((a,b)=>b.return_pct-a.return_pct||a.max_drawdown_pct-b.max_drawdown_pct);
  results.forEach((r,i)=>r.rank=i+1);
  return {generated_at:new Date().toISOString(),source:SOURCE,bankroll_mode:bankrollMode,
    settlement_clock:bankrollMode==="real"?"confirmed_pick_settlement_event":"legacy_result_observation",
    simulation_disclaimer:"Shadow replay; no actual wagers or bookmaker execution receipts. Rankings are provisional when settlement_conflict_count > 0.",
    rounding_step_minor:roundStep,rounding_mode:roundStep?'nearest_10_RSD_capped':'exact_baseline',starting_bankroll_minor:start,pick_count:(p.picks||[]).length,
    settlement_audit_status:settlementConflicts.length?"REVIEW_REQUIRED":"OK",
    settlement_conflict_count:settlementConflicts.length,
    settlement_conflicts:settlementConflicts,results};
}
function money(v:number){return (v/100).toLocaleString("sr-RS",{minimumFractionDigits:2,maximumFractionDigits:2})+" RSD";}
function pct(v:any){return v==null?"—":Number(v).toFixed(2)+"%";}

function esc(v:any){
  return String(v??"").replace(/[&<>"']/g,(c:string)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"} as any)[c]);
}
function localStamp(v:any){
  const x=d(v);
  return x?x.toLocaleString("sr-RS",{timeZone:"Europe/Belgrade",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}):"—";
}
function settlementAuditWarning(t:any){
  const discrepancies=t.settlement_conflicts||[];
  if(!discrepancies.length)return "";
  const items=discrepancies.slice(0,20).map((r:any)=>
    '<li><b>'+esc(r.home_team)+' - '+esc(r.away_team)+'</b> ('+esc(r.market)+' '+esc(r.selection)+
    '): event '+esc(r.event_kind||"NORMAL")+' ('+esc(r.audit_reason)+') / booked '+esc(r.confirmed_outcome)+' / observed '+esc(r.observed_outcome)+
    ' <small>'+esc(r.kelly_pick_id)+'</small></li>').join("");
  return '<section style="border:2px solid #edb85f;border-radius:10px;padding:14px 16px;margin:14px 0;background:#292319;color:#f6dcaf">'+
    '<b>SETTLEMENT DISCREPANCY — REVIEW REQUIRED ('+discrepancies.length+' picks)</b>'+
    '<p style="color:#f6dcaf">Provisional leaderboard. Pre-kickoff WIN/LOSS events are quarantined as PENDING without changing source records. Complete correction/reversal chains are replayed event by event; unresolved or incomplete chains remain flagged for audit. No original settlement evidence is erased.</p>'+
    '<ul style="padding-left:20px;overflow-wrap:anywhere">'+items+'</ul></section>';
}
function historyHtml(t:any){
  const strategies=t.results.slice().sort((a:any,b:any)=>a.label.localeCompare(b.label));
  const byId:any={};
  for(const s of strategies) byId[s.strategy_id]=new Map(s.allocations.map((a:any)=>[a.id,a]));
  const baseline=(strategies[0]?.allocations||[]).slice();
  const stamp=(a:any)=>d(t.bankroll_mode==="real"?a.settlement_occurred_at:a.result_first_acquired_at)?.getTime()||d(a.source_decision_at)?.getTime()||0;
  // The settlement ledger is chronological: no later result is applied to an earlier balance.
  const eventOrder=baseline.slice().filter((a:any)=>a.outcome!=="PENDING").sort((a:any,b:any)=>stamp(a)-stamp(b)||String(a.id).localeCompare(String(b.id)));
  const pending=baseline.slice().filter((a:any)=>a.outcome==="PENDING").sort((a:any,b:any)=>(d(a.materialized_at)?.getTime()||0)-(d(b.materialized_at)?.getTime()||0));
  const bank:any=Object.fromEntries(strategies.map((s:any)=>[s.strategy_id,t.starting_bankroll_minor]));
  const after:any={};
  for(const base of eventOrder){
    const vals:any={};
    for(const s of strategies){
      const a:any=byId[s.strategy_id].get(base.id);
      bank[s.strategy_id]+=Number(a?.pnl||0);
      vals[s.strategy_id]=bank[s.strategy_id];
    }
    after[base.id]=vals;
  }
  for(const base of pending) after[base.id]={...bank};
  const ordered=[...pending.slice().reverse(),...eventOrder.slice().reverse()];
  const selectOptions=strategies.map((s:any)=>'<option value="'+esc(s.strategy_id)+'">'+esc(s.label)+'</option>').join("");
  const strategyHeaders=strategies.map((s:any)=>'<th class="scol" data-sid="'+esc(s.strategy_id)+'">'+esc(s.label)+'</th>').join("");
  const rowHtml=ordered.map((a:any,i:number)=>{
    const state=String(a.outcome||"PENDING");
    const name=esc(a.home)+" – "+esc(a.away);
    const market=esc(a.market)+" "+esc(a.selection)+" @ "+Number(a.odds).toFixed(2);
    const cols=strategies.map((s:any)=>{
      const x:any=byId[s.strategy_id].get(a.id);
      const pl=x?.pnl;
      const pnlDisplay=pl==null?"Pending":(pl>0?"+":"")+money(pl);
      const cl=pl==null?"muted":pl>0?"pos":pl<0?"neg":"muted";
      const balance=after[a.id]?.[s.strategy_id];
      const isBet=x?.stake>0;
      return '<td class="scol" data-sid="'+esc(s.strategy_id)+'"><b>'+money(x?.stake||0)+'</b>'+(x?.rounding_delta_minor?'<small>Raw: '+money(x.raw_stake_minor)+'</small>':'')+'<small class="'+cl+'">P/L '+pnlDisplay+'</small><small>Equity '+money(x?.bankroll_after_settlement_minor??balance??t.starting_bankroll_minor)+'</small>'+(x?.available_after_settlement_minor==null?'':'<small>Available '+money(x.available_after_settlement_minor)+'</small><small>Reserved '+money(x.reserved_after_settlement_minor)+'</small>')+''+(isBet?"":'<small class="muted">NO BET</small>')+'</td>';
    }).join("");
    return '<tr data-status="'+esc(state)+'" data-search="'+esc((a.home||"")+" "+(a.away||"")+" "+(a.market||"")+" "+(a.selection||"")+" "+a.id).toLowerCase()+'" data-order="'+i+'">'+
      '<td><b>'+esc(localStamp((t.bankroll_mode==="real"?a.settlement_occurred_at:a.result_first_acquired_at)||a.materialized_at||a.source_decision_at))+'</b><small>'+(state==="PENDING"?"Placement time":"Settlement time")+'</small></td>'+
      '<td><b>'+name+'</b><small>'+market+'</small></td>'+
      '<td><span class="outcome '+(state==="WIN"?"pos":state==="LOSS"?"neg":"muted")+'">'+esc(state)+'</span></td>'+cols+'</tr>';
  }).join("");
  const settled=eventOrder.length;
  const open=pending.length;
  const qs=t.bankroll_mode==="legacy"?"?bankroll=legacy"+(t.rounding_step_minor?"":"&rounding=exact"):(t.rounding_step_minor?"":"?rounding=exact");
  const otherQS=t.bankroll_mode==="real"?"?bankroll=legacy"+(t.rounding_step_minor?"":"&rounding=exact"):(t.rounding_step_minor?"":"?rounding=exact");
  return '<!doctype html><html lang="sr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kelly Tournament — Settlement History</title>'+
`<style>:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#111315;color:#edf0f2;font:14px/1.45 Inter,system-ui,sans-serif}main{max-width:1600px;margin:auto;padding:24px}h1{margin:12px 0 4px;font-size:27px}h2{margin:18px 0 12px;font-size:18px}p,.muted,small{color:#9ba4af}small{display:block;margin-top:3px;font-size:11px}.nav{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 20px}.nav a{display:inline-block;color:#d9e1e7;text-decoration:none;background:#1b2026;border:1px solid #303740;border-radius:8px;padding:9px 13px}.nav a.active{background:#283544;border-color:#62778a}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}.card,.panel{background:#181b1f;border:1px solid #30363d;border-radius:12px}.card{padding:14px}.card b{display:block;font-size:20px;margin-top:5px}.filters{display:flex;gap:10px;align-items:end;flex-wrap:wrap;padding:14px;background:#181b1f;border:1px solid #30363d;border-radius:12px;margin:16px 0}.filters label{display:flex;flex-direction:column;gap:6px;color:#a9b3bd;font-size:12px}.filters select,.filters input,.pager button{background:#121619;color:#ecf0f2;border:1px solid #46505a;border-radius:7px;padding:9px 10px;font:inherit}.filters input{min-width:230px}.filters #find{flex:1}.panel{overflow:hidden}.scroll{width:100%;overflow:auto;max-height:70vh}table{border-collapse:separate;border-spacing:0;font-size:12px;white-space:nowrap}th,td{border-bottom:1px solid #292e33;border-right:1px solid #292e33;padding:10px 12px;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#242a30;color:#bec7ce;z-index:3;font-size:10px;text-transform:uppercase}td{background:#181b1f}th:first-child,td:first-child{position:sticky;left:0;z-index:2;background:#20252a}th:first-child{z-index:4}td:nth-child(2){min-width:235px}.scol{min-width:155px}.pos{color:#70cf96}.neg{color:#ed8088}.outcome{font-weight:750}.note{font-size:12px;line-height:1.5;margin-top:12px}.pager{display:flex;gap:10px;align-items:center;justify-content:flex-end;padding:12px}.pager button:disabled{opacity:.4;cursor:not-allowed}a{color:#ccdbe8}tr[hidden],.scol[hidden]{display:none!important}@media(max-width:800px){main{padding:14px}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}h1{font-size:22px}.filters input{min-width:100px;width:100%}} </style>`+
'</head><body><main><small>READ-ONLY SHADOW EXPERIMENT · EUROPE/BELGRADE TIMES</small><h1>Settlement History</h1><p>All Research clone outcomes. Each strategy is evaluated on the same picks; only its stake sizing changes. <b>'+(t.bankroll_mode==="real"?'30,000 RSD cash-constrained shadow replay. ':'LEGACY UNRESERVED audit only. ')+(t.rounding_step_minor?'Stakes rounded to nearest 10 RSD.':'Exact unrounded stakes.')+'</b> No actual wagers or verified bookmaker execution receipts.</p>'+
settlementAuditWarning(t)+'<div class="nav"><a href="/'+qs+'">Leaderboard</a><a href="/settlement-history'+qs+'" class="active">Settlement History</a><a href="/kelly-tournament.json'+qs+'">JSON export</a><a href="/settlement-history'+otherQS+'">'+(t.bankroll_mode==="real"?'Legacy audit':'Real cash replay')+'</a></div>'+
'<div class="cards"><div class="card"><small>Strategies</small><b>'+strategies.length+'</b></div><div class="card"><small>All picks</small><b>'+t.pick_count+'</b></div><div class="card"><small>Settled</small><b>'+settled+'</b></div><div class="card"><small>Pending</small><b>'+open+'</b></div></div>'+
'<div class="filters"><label>Outcome<select id="outcome"><option value="SETTLED">Settled (WIN / LOSS / VOID)</option><option value="ALL">All picks</option><option value="WIN">WIN</option><option value="LOSS">LOSS</option><option value="VOID">VOID</option><option value="PENDING">PENDING</option></select></label>'+
'<label>Strategy<select id="strategy"><option value="ALL">All 17 strategies</option>'+selectOptions+'</select></label>'+
'<label id="find">Search match / market / ID<input id="search" type="search" placeholder="Team, market or pick ID…"></label>'+
'<label>Order<select id="order"><option value="new">Newest first</option><option value="old">Oldest first</option></select></label></div>'+
'<div class="panel"><div class="scroll"><table id="history"><thead><tr><th>Time</th><th>Pick / market</th><th>Outcome</th>'+strategyHeaders+'</tr></thead><tbody>'+rowHtml+'</tbody></table></div>'+
'<div class="pager"><small id="count"></small><button id="prev" type="button">Previous</button><span id="page"></span><button id="next" type="button">Next</button></div></div>'+
'<p class="note">Per strategy cell: stake, settled P/L, equity after settlement, available cash, and reserved open stakes (starting from '+money(t.starting_bankroll_minor)+'). NO BET means stake 0 and P/L 0. Pending picks show current realized balance; no future outcome is included. Real cash replay rows use confirmed settlement time. P/L and bankroll are simulated values, not actual wagers. Filters do not change the bankroll calculation.</p>'+
'<p class="note">Research qualification and scope/retirement filters determine the common pick pool; positive bucket ROI is not a mandatory entry gate.</p>'+
'</main>'+
`<script>
(function(){
 const tbody=document.querySelector("#history tbody");
 const rows=Array.from(tbody.querySelectorAll("tr"));
 const status=document.getElementById("outcome"),strategy=document.getElementById("strategy"),search=document.getElementById("search"),order=document.getElementById("order");
 const count=document.getElementById("count"),pageInfo=document.getElementById("page"),prev=document.getElementById("prev"),next=document.getElementById("next");
 const PER_PAGE=100; let page=0;
 function update(){
   const s=status.value,q=search.value.toLowerCase().trim(),chosen=strategy.value,old=order.value==="old";
   const visible=rows.filter(r=>(s==="ALL"||(s==="SETTLED"?r.dataset.status!=="PENDING":r.dataset.status===s))&&r.dataset.search.includes(q));
   if(old) visible.reverse();
   const pages=Math.max(1,Math.ceil(visible.length/PER_PAGE));page=Math.max(0,Math.min(page,pages-1));
   const shown=new Set(visible.slice(page*PER_PAGE,(page+1)*PER_PAGE));
   rows.forEach(r=>{r.hidden=!shown.has(r)});
   document.querySelectorAll(".scol").forEach(c=>{c.hidden=chosen!=="ALL"&&c.dataset.sid!==chosen});
   const result=old?visible:visible;
   result.forEach(r=>{if(shown.has(r)) tbody.appendChild(r)});
   count.textContent=visible.length+" matching picks (showing "+(visible.length?1+page*PER_PAGE:0)+"–"+Math.min(visible.length,(page+1)*PER_PAGE)+")";
   pageInfo.textContent="Page "+(page+1)+" / "+pages;prev.disabled=page===0;next.disabled=page>=pages-1;
 }
 [status,strategy,search,order].forEach(el=>el.addEventListener(el===search?"input":"change",()=>{page=0;update()}));
 prev.addEventListener("click",()=>{page--;update()});next.addEventListener("click",()=>{page++;update()});
 update();
})();
</script>`+'</body></html>';
}

function html(t:any){
  const rows=t.results.map((r:any)=>`<tr><td><b>#${r.rank}</b></td><td><b>${r.label}</b><small>${r.strategy_id}</small></td><td>${money(r.terminal_bankroll_minor)}</td><td>${r.available_bankroll_minor==null?"—":money(r.available_bankroll_minor)}</td><td>${r.reserved_bankroll_minor==null?"—":money(r.reserved_bankroll_minor)}</td><td class="${r.pnl_minor>=0?"pos":"neg"}">${money(r.pnl_minor)}</td><td>${pct(r.return_pct)}</td><td>${pct(r.staking_roi_pct)}</td><td>${pct(r.max_drawdown_pct)}</td><td>${r.bet_count}</td><td>${r.no_bet_count}</td><td>${money(r.avg_stake_minor)}</td><td>${money(r.max_stake_minor)}</td><td>${money(r.open_stake_minor)}</td></tr>`).join("");
  const showIds=["FLAT_300","CAL_Q25_C2","CAL_Q25_C5","BUCKET_SOFT_Q25_C2","BUCKET_HARD_Q25_C2","BUCKET_DIRECT_C2","BUCKET_DIRECT_C5"];
  const byId=Object.fromEntries(t.results.map((r:any)=>[r.strategy_id,r]));
  const base=byId["FLAT_300"]?.allocations||[];
  const latest=[...base].slice(-20).reverse();
  const stakeRows=latest.map((a:any)=>{
    const cells=showIds.map(id=>{
      const z=byId[id]?.allocations?.find((x:any)=>x.id===a.id);
      return `<td><b>${z?money(z.stake):"—"}</b>${z&&id.startsWith("BUCKET")?`<small>Q ${(z.quality*100).toFixed(0)}%</small>`:""}</td>`;
    }).join("");
    return `<tr><td><b>${a.home} – ${a.away}</b><small>${a.market} ${a.selection} @ ${Number(a.odds).toFixed(2)}</small></td>${cells}</tr>`;
  }).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KellyLab Tournament</title>
<style>:root{color-scheme:dark}body{margin:0;background:#111315;color:#edf0f2;font-family:Inter,system-ui,sans-serif}main{max-width:1500px;margin:auto;padding:24px}h1{margin:4px 0}p,small{color:#949ba3}small{display:block;margin-top:3px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}.card,.panel{background:#181b1f;border:1px solid #30363d;border-radius:12px}.card{padding:14px}.card b{display:block;font-size:20px;margin-top:6px}.table{overflow:auto}.panel{overflow:hidden}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:11px;border-bottom:1px solid #292e33;text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#1c2024;color:#9ca3aa;font-size:10px;text-transform:uppercase}.pos{color:#70cf96}.neg{color:#e2757d}a{color:#dfe3e6}.note{font-size:12px;color:#8f969d;line-height:1.5;margin-top:12px}@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr)}main{padding:14px}}</style></head><body><main>
<small>SHADOW SIMULATION | ${t.bankroll_mode==="real"?"CASH-CONSTRAINED REPLAY":"LEGACY AUDIT (UNRESERVED STAKES)"}</small><h1>KellyLab Strategy Tournament</h1>${settlementAuditWarning(t)}<p>Same frozen Research picks. Same 30,000 RSD starting bankroll. No actual wagers or verified bookmaker execution receipts. ${t.rounding_step_minor?"Stakes rounded to nearest 10 RSD, with hard caps respected.":"Original exact-stake benchmark."}</p><p><a href="${t.rounding_step_minor?"/?rounding=exact"+(t.bankroll_mode==="legacy"?"&bankroll=legacy":""):(t.bankroll_mode==="legacy"?"/?bankroll=legacy":"/")}">${t.rounding_step_minor?"Compare with exact-stake baseline →":"Switch to rounded 10 RSD →"}</a></p><p style="margin:10px 0"><a href="${t.bankroll_mode==="real"?"/?bankroll=legacy"+(t.rounding_step_minor?"":"&rounding=exact"):(t.rounding_step_minor?"/":"/?rounding=exact")}">${t.bankroll_mode==="real"?"Compare to old unreserved simulation (audit only) →":"Return to cash-constrained replay →"}</a></p><p style="margin:18px 0"><a href="/settlement-history${t.bankroll_mode==="legacy"?"?bankroll=legacy"+(t.rounding_step_minor?"":"&rounding=exact"):(t.rounding_step_minor?"":"?rounding=exact")}" style="display:inline-block;border:1px solid #526273;background:#24303b;padding:10px 14px;text-decoration:none;font-weight:650">Settlement History — all 17 strategies →</a></p>
<div class="cards"><div class="card"><small>Strategies / Picks</small><b>${t.results.length} / ${t.pick_count}</b></div><div class="card"><small>Starting bankroll / strategy</small><b>${money(t.starting_bankroll_minor)}</b></div><div class="card"><small>Leader available / reserved</small><b>${t.results[0]?.available_bankroll_minor==null?"Legacy":money(t.results[0].available_bankroll_minor)}</b><small>${t.results[0]?.reserved_bankroll_minor==null?"No reservation":money(t.results[0].reserved_bankroll_minor)+" reserved"}</small></div><div class="card"><small>Current leader</small><b>${t.results[0]?.label||"—"}</b></div></div>
<p class="note">${t.bankroll_mode==="real"?"Shadow replay: 30,000 RSD per strategy. Each simulated stake is immediately reserved; available = equity minus all open stakes. Only confirmed settlement events replenish cash. NO BET if insufficient funds, after kickoff or when the result was already known.":"LEGACY simulation: open stakes were not reserved. Figures are retained for audit, NOT an executable 30,000 RSD strategy."}</p><div class="panel"><div class="table"><table><thead><tr><th>Rank</th><th>Strategy</th><th>Equity</th><th>Available</th><th>Reserved</th><th>P/L</th><th>Return</th><th>Stake ROI</th><th>Max DD</th><th>Bets</th><th>No bet</th><th>Avg stake</th><th>Max stake</th><th>Open stake</th></tr></thead><tbody>${rows}</tbody></table></div></div>
<p class="note">Bucket quality now combines empirical win-rate edge versus break-even with sample strength N/(N+150), averaged across all frozen dimensions. Bucket direct allocates cap × quality directly, so it cannot collapse to a flat 300 unless quality itself implies it. Rankings remain descriptive until the settled sample is meaningful.</p>
<h2>Recent stake distribution</h2><div class="panel"><div class="table"><table><thead><tr><th>Pick</th><th>Flat 300</th><th>Cal ¼ 2%</th><th>Cal ¼ 5%</th><th>Bucket soft</th><th>Bucket hard</th><th>Bucket direct 2%</th><th>Bucket direct 5%</th></tr></thead><tbody>${stakeRows||'<tr><td colspan="8">No picks yet.</td></tr>'}</tbody></table></div></div>
<p><a href="/settlement-history${t.bankroll_mode==="legacy"?"?bankroll=legacy"+(t.rounding_step_minor?"":"&rounding=exact"):(t.rounding_step_minor?"":"?rounding=exact")}">Settlement History · all 17 strategies →</a> · <a href="/kelly-tournament.json${t.bankroll_mode==="legacy"?"?bankroll=legacy"+(t.rounding_step_minor?"":"&rounding=exact"):(t.rounding_step_minor?"":"?rounding=exact")}">JSON</a> · <a href="https://quantbet-kellylab-production.up.railway.app/kellylab">KellyLab</a></p>
</main></body></html>`;
}
Bun.serve({port:Number(Bun.env.PORT||3000),async fetch(req){
  const u=new URL(req.url);
  if(u.pathname==="/livez") return new Response("ok\n");
  if(u.pathname==="/production-kelly-tournament"||u.pathname==="/production-kelly-tournament.json"){
    try {
      const report=await productionTournament();
      if(u.pathname.endsWith(".json")) return Response.json(report,{headers:{"cache-control":"no-store"}});
      return new Response(productionHtml(report),{headers:{"content-type":"text/html; charset=utf-8","cache-control":"no-store"}});
    }catch(e){
      console.error("PRODUCTION_KELLY_TOURNAMENT_ERROR",e && e.stack || String(e));
      return Response.json({contract:"PKST-V1",error:"PRODUCTION_KELLY_SOURCE_OR_REPLAY_UNAVAILABLE",status:"DEGRADED"},{status:503,headers:{"cache-control":"no-store"}});
    }
  }
  if(u.pathname!=="/"&&u.pathname!=="/kelly-tournament"&&u.pathname!=="/kelly-tournament.json"&&u.pathname!=="/settlement-history") return new Response("not_found\n",{status:404});
  try{
    const t=await tournament(u.searchParams.get("rounding")==="exact"?0:STAKE_ROUND_STEP_MINOR,u.searchParams.get("bankroll")==="legacy"?"legacy":"real");
    if(u.pathname==="/kelly-tournament.json") return Response.json(t,{headers:{"cache-control":"no-store"}});
    if(u.pathname==="/settlement-history") return new Response(withHubReturn(historyHtml(t)),{headers:{"content-type":"text/html; charset=utf-8","cache-control":"no-store"}});
    return new Response(withHubReturn(html(t)),{headers:{"content-type":"text/html; charset=utf-8","cache-control":"no-store"}});
  }catch(e:any){console.error("KELLY_TOURNAMENT_ERROR",e?.stack||e?.message||String(e));return new Response(String(e?.message||e)+"\n",{status:503});}
}});

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
