/* node:test regression suite for isolated Production Kelly route module. */
const fs = require("node:fs");
const assert = require("node:assert/strict");
const { test } = require("node:test");
const src=fs.readFileSync(require("node:path").join(__dirname,"production_kelly_tournament_route_v1.js"),"utf8");
const {prodOutcome,prodSimulate,prodStake,PRODUCTION_STRATEGIES,PRODUCTION_SQL}=
  new Function(src+"\nreturn {prodOutcome,prodSimulate,prodStake,PRODUCTION_STRATEGIES,PRODUCTION_SQL};")();
const start=Date.parse("2026-10-16T12:00:00Z"),kickoff=Date.parse("2026-10-16T13:00:00Z");
function pick(id,at,odds=2,p=0.65,outcome="PENDING",settledAt=null,policy="v1"){
  return {pick_id:id,cloned_at:new Date(at).toISOString(),kickoff_at:new Date(kickoff).toISOString(),
    source_universe:"RESEARCH",source_pick_id:id,home_team:"Home",away_team:"Away",
    market_key:"OU_25",selection:"OVER",odds,model_probability:p,intake_contract_version:policy,
    _result:{outcome,at:settledAt,reason:""}};
}
test("sole input is Production materialized picks, without independently matching buckets",()=>{
  assert.match(PRODUCTION_SQL,/FROM production_funnel_picks p/);
  assert.doesNotMatch(PRODUCTION_SQL,/matching_bucket_ids/);
  assert.match(PRODUCTION_SQL,/intake_contract_version/);
  assert.match(PRODUCTION_SQL,/p\.cloned_at >= \$1/);
});
test("exactly 17 unique sizing strategies share a common Production candidate cohort",()=>{
  assert.equal(PRODUCTION_STRATEGIES.length,17);
  assert.equal(new Set(PRODUCTION_STRATEGIES.map(x=>x.id)).size,17);
  const two=[pick("a",start),pick("b",start+10000)];
  for(const s of PRODUCTION_STRATEGIES){
    const r=prodSimulate(two,s,start+200000);
    assert.equal(r.candidate_count,2);
    assert.deepEqual(r.allocations.map(x=>x.id),["a","b"]);
  }
});
test("stakes are bounded by equity, available cash, individual cap and 10-RSD step",()=>{
  const p=pick("a",start),s=PRODUCTION_STRATEGIES.find(x=>x.id==="P_K25_C10");
  const stake=prodStake(p,s,3000000,50000);
  assert.equal(stake%1000,0);assert.ok(stake<=50000);assert.ok(stake<=300000);
  assert.equal(prodStake({...p,model_probability:0.4},s,3000000,3000000),0);
});
test("settlement only releases reserved cash when source settlement time has arrived",()=>{
  const r=prodSimulate([pick("a",start,2,0.65,"WIN",start+200000)],PRODUCTION_STRATEGIES.find(s=>s.id==="P_K25_C10"),start+100000);
  assert.equal(r.settled_count,0);
  assert.equal(r.available_bankroll_minor+r.reserved_bankroll_minor,3000000);
  assert.ok(r.reserved_bankroll_minor>0);
  const later=prodSimulate([pick("a",start,2,0.65,"WIN",start+200000)],PRODUCTION_STRATEGIES.find(s=>s.id==="P_K25_C10"),start+300000);
  assert.equal(later.settled_count,1);assert.ok(later.pnl_minor>0);assert.equal(later.reserved_bankroll_minor,0);
});
test("after kickoff is NO_BET even if observed outcome is positive",()=>{
  const r=prodSimulate([pick("late",kickoff+1000,3,0.9,"WIN",kickoff+2000)],PRODUCTION_STRATEGIES[0],kickoff+10000);
  assert.equal(r.bet_count,0);assert.equal(r.pnl_minor,0);
});
test("manual void is zero P/L and correction without chain is quarantined",()=>{
  const now=Date.parse("2026-10-16T16:00:00Z");
  const manual=prodOutcome({source_universe:"RESEARCH",research_event_kind:"MANUAL_VOID",research_event_outcome:"VOID",research_event_at:new Date(now).toISOString(),kickoff_at:new Date(kickoff).toISOString()},now+10000);
  assert.equal(manual.outcome,"VOID");
  const corrected=prodOutcome({source_universe:"RESEARCH",research_event_kind:"CORRECTION",research_event_outcome:"WIN",research_event_at:new Date(now).toISOString(),kickoff_at:new Date(kickoff).toISOString()},now+10000);
  assert.equal(corrected.outcome,"PENDING");assert.equal(corrected.reason,"UNVERIFIED_RESEARCH_CORRECTION_CHAIN");
});
test("pre-kickoff win is quarantined, not realized",()=>{
  const r=prodOutcome({source_universe:"CORNERLAB",corner_outcome:"WIN",corner_settled_at:new Date(start).toISOString(),kickoff_at:new Date(kickoff).toISOString()},start+2000000);
  assert.equal(r.outcome,"PENDING");assert.equal(r.reason,"PRE_KICKOFF_SETTLEMENT");
});
test("policy version retained per pick without historical re-selection",()=>{
  const r=prodSimulate([pick("a",start,2,0.65,"LOSS",start+300000,"first"),
    pick("b",start+5000,2,0.65,"WIN",start+400000,"changed")],
    PRODUCTION_STRATEGIES.find(s=>s.id==="P_K25_C2"),start+600000);
  assert.equal(r.by_policy.first.picks,1);assert.equal(r.by_policy.changed.picks,1);
  assert.equal(r.candidate_count,2);
});
