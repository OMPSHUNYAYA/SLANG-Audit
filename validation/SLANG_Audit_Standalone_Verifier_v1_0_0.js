#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Shunyaya Framework contributors.

'use strict';

const fs = require('fs');
const crypto = require('crypto');

const VERSION = '2.4.0';
const PROFILE_ID = 'SLANG-AUDIT-DECLARED-EVIDENCE-1';
const INPUT_SCHEMA = 'SLANG-AUDIT-STRUCTURE-2';
const CANONICAL_SCHEMA = 'SLANG-AUDIT-CANONICAL-1';
const CERTIFICATE_SCHEMA = 'SLANG-AUDIT-CERTIFICATE-6';
const BUNDLE_SCHEMA = 'SLANG-AUDIT-BUNDLE-6';
const PROOF_SCHEMA = 'SLANG-AUDIT-PROOF-5';
const CANONICALIZATION_ID = 'SLANG-AUDIT-CANONICAL-BOOLEAN-1';
const DELTA_SCHEMA = 'SLANG-AUDIT-DELTA-1';
const DELTA_CERTIFICATE_SCHEMA = 'SLANG-AUDIT-DELTA-CERTIFICATE-1';
const INCREMENTAL_BUNDLE_SCHEMA = 'SLANG-AUDIT-INCREMENTAL-BUNDLE-1';
const LEDGER_SCHEMA = 'SLANG-AUDIT-PROOF-LEDGER-1';
const LEDGER_CHECKPOINT_SCHEMA = 'SLANG-AUDIT-LEDGER-CHECKPOINT-1';
const LEDGER_DELTA_SEQUENCE_SCHEMA = 'SLANG-AUDIT-LEDGER-DELTA-SEQUENCE-1';
const MAX_INPUT_BYTES = 1048576;
const MAX_RULE_FIRINGS = 8192;
const MAX_PROOF_CANDIDATES_PER_LITERAL = 512;
const MAX_WITNESS_COMBINATIONS = 16384;
const MAX_COUNTERFACTUAL_CANDIDATE_SOURCES = 24;
const MAX_COUNTERFACTUAL_CANDIDATE_LITERALS = 24;
const MAX_COUNTERFACTUAL_EVALUATIONS = 65536;
const MAX_LEDGER_ENTRIES = 128;
const ID_RE = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/;
const COMMITMENT_RE = /^sha256:[0-9a-f]{64}$/;

function fail(code) { const e = new Error(code); e.code = code; throw e; }
function isObject(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
function deepClone(v) { return JSON.parse(JSON.stringify(v)); }
function keysExact(obj, keys) { const a = Object.keys(obj).sort(); const b = [...keys].sort(); return a.length === b.length && a.every((x, i) => x === b[i]); }
function sortObj(obj) { const out = {}; for (const k of Object.keys(obj).sort()) out[k] = obj[k]; return out; }
function cmpText(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
function cmpArray(a, b) { const n = Math.min(a.length, b.length); for (let i = 0; i < n; i++) { const c = cmpText(String(a[i]), String(b[i])); if (c) return c; } return a.length - b.length; }
function same(a, b) { return canonicalJson(a) === canonicalJson(b); }

class StrictParser {
  constructor(text) { this.text = text; this.i = 0; }
  ws() { while (this.i < this.text.length && /\s/.test(this.text[this.i])) this.i++; }
  parse() { this.ws(); const v = this.value(); this.ws(); if (this.i !== this.text.length) fail('TRAILING_JSON_DATA'); return v; }
  value() {
    this.ws();
    const c = this.text[this.i];
    if (c === '{') return this.object();
    if (c === '[') return this.array();
    if (c === '"') return this.string();
    if (this.text.startsWith('true', this.i)) { this.i += 4; return true; }
    if (this.text.startsWith('false', this.i)) { this.i += 5; return false; }
    if (this.text.startsWith('null', this.i)) { this.i += 4; return null; }
    if (c === '-' || /[0-9]/.test(c || '')) return this.number();
    fail('INVALID_JSON_VALUE');
  }
  string() {
    const start = this.i++;
    let escaped = false;
    while (this.i < this.text.length) {
      const c = this.text[this.i++];
      if (!escaped && c === '"') {
        const token = this.text.slice(start, this.i);
        try { return JSON.parse(token); } catch (_) { fail('INVALID_JSON_STRING'); }
      }
      if (!escaped && c === '\\') escaped = true; else escaped = false;
      if (c.charCodeAt(0) < 0x20) fail('INVALID_JSON_STRING');
    }
    fail('UNTERMINATED_JSON_STRING');
  }
  number() {
    const start = this.i;
    if (this.text[this.i] === '-') this.i++;
    if (this.text[this.i] === '0') this.i++;
    else {
      if (!/[1-9]/.test(this.text[this.i] || '')) fail('INVALID_JSON_NUMBER');
      while (/[0-9]/.test(this.text[this.i] || '')) this.i++;
    }
    if (this.text[this.i] === '.' || this.text[this.i] === 'e' || this.text[this.i] === 'E') fail('FLOAT_NOT_SUPPORTED');
    const token = this.text.slice(start, this.i);
    const n = Number(token);
    if (!Number.isSafeInteger(n)) fail('INTEGER_OUT_OF_RANGE');
    return n;
  }
  array() {
    this.i++; this.ws(); const out = [];
    if (this.text[this.i] === ']') { this.i++; return out; }
    while (true) {
      out.push(this.value()); this.ws();
      if (this.text[this.i] === ']') { this.i++; return out; }
      if (this.text[this.i] !== ',') fail('INVALID_JSON_ARRAY');
      this.i++; this.ws();
    }
  }
  object() {
    this.i++; this.ws(); const out = {}; const seen = new Set();
    if (this.text[this.i] === '}') { this.i++; return out; }
    while (true) {
      if (this.text[this.i] !== '"') fail('INVALID_JSON_OBJECT_KEY');
      const k = this.string();
      if (seen.has(k)) fail('DUPLICATE_JSON_KEY:' + k);
      seen.add(k); this.ws();
      if (this.text[this.i] !== ':') fail('INVALID_JSON_OBJECT');
      this.i++; out[k] = this.value(); this.ws();
      if (this.text[this.i] === '}') { this.i++; return out; }
      if (this.text[this.i] !== ',') fail('INVALID_JSON_OBJECT');
      this.i++; this.ws();
    }
  }
}

function strictJson(text) {
  if (Buffer.byteLength(text, 'utf8') > MAX_INPUT_BYTES) fail('INPUT_SIZE_LIMIT');
  return new StrictParser(text).parse();
}

function asciiString(s) {
  const q = JSON.stringify(s);
  let out = '"';
  for (let i = 1; i < q.length - 1; i++) {
    const code = q.charCodeAt(i);
    if (code > 0x7f) out += '\\u' + code.toString(16).padStart(4, '0'); else out += q[i];
  }
  return out + '"';
}

function canonicalJson(v) {
  if (v === null) return 'null';
  if (v === true) return 'true';
  if (v === false) return 'false';
  if (typeof v === 'number') { if (!Number.isSafeInteger(v)) fail('NONINTEGER_CANONICAL_NUMBER'); return String(v); }
  if (typeof v === 'string') return asciiString(v);
  if (Array.isArray(v)) return '[' + v.map(canonicalJson).join(',') + ']';
  if (isObject(v)) return '{' + Object.keys(v).sort().map(k => asciiString(k) + ':' + canonicalJson(v[k])).join(',') + '}';
  fail('UNSUPPORTED_CANONICAL_TYPE');
}

function sha256Text(s) { return crypto.createHash('sha256').update(Buffer.from(s, 'utf8')).digest('hex'); }
function identity(prefix, v) { return prefix + ':' + sha256Text(canonicalJson(v)); }
function literalKey(atom, value) { return atom + '=' + (value ? 'true' : 'false'); }
function parseLiteralKey(key) { const p = key.lastIndexOf('='); return [key.slice(0, p), key.slice(p + 1) === 'true']; }

function validateIdentifier(x) { if (typeof x !== 'string' || !ID_RE.test(x)) fail('INVALID_IDENTIFIER'); return x; }
function validateLiteralMap(raw, emptyAllowed=false) {
  if (!isObject(raw) || (!emptyAllowed && Object.keys(raw).length === 0)) fail('INVALID_LITERAL_MAP');
  const out = {};
  for (const k of Object.keys(raw).sort()) { validateIdentifier(k); if (typeof raw[k] !== 'boolean') fail('BOOLEAN_REQUIRED'); out[k] = raw[k]; }
  return out;
}

function normalizeStructure(raw) {
  if (!isObject(raw) || raw.schema !== INPUT_SCHEMA) fail('UNSUPPORTED_INPUT_SCHEMA');
  if (!keysExact(raw, ['schema','atoms','targets','evidence','rules','controls'])) fail('INVALID_INPUT_FIELDS');
  if (!Array.isArray(raw.atoms) || raw.atoms.length === 0 || !Array.isArray(raw.targets) || raw.targets.length === 0 || !Array.isArray(raw.evidence) || !Array.isArray(raw.rules) || !Array.isArray(raw.controls) || raw.controls.length === 0) fail('INVALID_INPUT_COLLECTION');
  const atoms = [...raw.atoms].map(validateIdentifier).sort();
  const targets = [...raw.targets].map(validateIdentifier).sort();
  if (new Set(atoms).size !== atoms.length || new Set(targets).size !== targets.length) fail('DUPLICATE_IDENTIFIER');
  const atomSet = new Set(atoms);
  const evidence = raw.evidence.map(item => {
    if (!isObject(item) || !keysExact(item, ['id','claims','commitment'])) fail('INVALID_EVIDENCE_ITEM');
    const id = validateIdentifier(item.id); const claims = validateLiteralMap(item.claims);
    for (const a of Object.keys(claims)) if (!atomSet.has(a)) fail('UNDECLARED_ATOM');
    if (item.commitment !== null && (typeof item.commitment !== 'string' || !COMMITMENT_RE.test(item.commitment))) fail('INVALID_EVIDENCE_COMMITMENT');
    return {id, claims, commitment:item.commitment};
  }).sort((a,b)=>cmpText(a.id,b.id));
  const rules = raw.rules.map(item => {
    if (!isObject(item) || !keysExact(item, ['id','if_all','then'])) fail('INVALID_RULE_ITEM');
    const id = validateIdentifier(item.id); const if_all=validateLiteralMap(item.if_all); const then=validateLiteralMap(item.then);
    if (Object.keys(then).length !== 1) fail('INVALID_RULE_CONCLUSION');
    for (const a of [...Object.keys(if_all),...Object.keys(then)]) if (!atomSet.has(a)) fail('UNDECLARED_ATOM');
    const ca=Object.keys(then)[0]; if (Object.prototype.hasOwnProperty.call(if_all,ca) && if_all[ca]===then[ca]) fail('SELF_CONFIRMING_RULE');
    return {id, if_all, then};
  }).sort((a,b)=>cmpText(a.id,b.id));
  const controls = raw.controls.map(item => {
    if (!isObject(item) || !keysExact(item,['id','require'])) fail('INVALID_CONTROL_ITEM');
    const id=validateIdentifier(item.id); const require=validateLiteralMap(item.require);
    for (const a of Object.keys(require)) if (!atomSet.has(a)) fail('UNDECLARED_ATOM');
    return {id,require};
  }).sort((a,b)=>cmpText(a.id,b.id));
  if (new Set(evidence.map(x=>x.id)).size !== evidence.length || new Set(rules.map(x=>x.id)).size !== rules.length || new Set(controls.map(x=>x.id)).size !== controls.length) fail('DUPLICATE_COMPONENT_ID');
  const controlSet=new Set(controls.map(x=>x.id)); for (const t of targets) if (!controlSet.has(t)) fail('UNDECLARED_TARGET_CONTROL');
  const core={schema:CANONICAL_SCHEMA,source_schema:INPUT_SCHEMA,profile_id:PROFILE_ID,canonicalization_id:CANONICALIZATION_ID,atoms,targets,evidence,rules,controls};
  core.evidence_ids=evidence.map(x=>identity('slang_audit_evidence_sha256',x));
  core.rule_ids=rules.map(x=>identity('slang_audit_rule_sha256',x));
  core.control_ids=controls.map(x=>identity('slang_audit_control_sha256',x));
  const out={...core}; out.canonical_structure_id=identity('slang_audit_structure_sha256',core); return out;
}

function canonicalToSource(c) { return {schema:c.source_schema,atoms:[...c.atoms],targets:[...c.targets],evidence:deepClone(c.evidence),rules:deepClone(c.rules),controls:deepClone(c.controls)}; }
function supportHas(s,k){return Object.prototype.hasOwnProperty.call(s,k);}

function deriveClosure(c) {
  const support=new Map();
  const add=(k,src)=>{if(!support.has(k))support.set(k,new Set()); const n=support.get(k).size; support.get(k).add(src); return support.get(k).size>n;};
  for(const e of c.evidence) for(const [a,v] of Object.entries(e.claims)) add(literalKey(a,v),'evidence:'+e.id);
  const fired=new Set(); const firings=[]; let changed=true; let firingCount=0;
  while(changed){changed=false; for(const r of c.rules){let ok=true; const premises=[]; for(const [a,v] of Object.entries(r.if_all)){const req=literalKey(a,v),opp=literalKey(a,!v); if(!support.has(req)||support.has(opp)){ok=false;break;} premises.push(req);} if(!ok)continue; const [a,v]=Object.entries(r.then)[0]; if(add(literalKey(a,v),'rule:'+r.id)) changed=true; if(!fired.has(r.id)){firingCount++; if(firingCount>MAX_RULE_FIRINGS)fail('RULE_FIRING_LIMIT'); fired.add(r.id); firings.push({rule_id:r.id,premises:premises.sort(),conclusion:literalKey(a,v)});}}}
  const atom_states={}, support_public={}, contradictory_atoms=[];
  for(const a of c.atoms){const t=support.has(literalKey(a,true)),f=support.has(literalKey(a,false)); atom_states[a]=t&&f?'CONTRADICTORY':t?'TRUE':f?'FALSE':'UNKNOWN'; if(t&&f)contradictory_atoms.push(a); for(const v of [false,true]){const k=literalKey(a,v); if(support.has(k))support_public[k]=[...support.get(k)].sort();}}
  return {atom_states,support:sortObj(support_public),rule_firings:firings.sort((a,b)=>cmpText(a.rule_id,b.rule_id)),contradictory_atoms:contradictory_atoms.sort()};
}

function controlVerdict(control, closure){
  const contradictory=[],violated=[],missing=[],satisfied=[],support=closure.support;
  for(const [a,v] of Object.entries(control.require)){const req=literalKey(a,v),opp=literalKey(a,!v);const hr=supportHas(support,req),ho=supportHas(support,opp); if(hr&&ho)contradictory.push(a); else if(ho)violated.push(req); else if(hr)satisfied.push(req); else missing.push(req);}
  let verdict,witness;
  if(contradictory.length){verdict='ABSTAIN'; const supports={}; for(const a of contradictory)supports[a]={true:support[literalKey(a,true)]||[],false:support[literalKey(a,false)]||[]}; witness={kind:'CONTRADICTION',atoms:contradictory,supports};}
  else if(violated.length){verdict='VIOLATED'; const opposing_support={}; for(const req of violated){const [a,v]=parseLiteralKey(req); opposing_support[req]=support[literalKey(a,!v)];} witness={kind:'VIOLATION',violated_requirements:violated,opposing_support};}
  else if(missing.length){verdict='INCOMPLETE'; witness={kind:'MISSING',missing_requirements:missing,satisfied_requirements:satisfied};}
  else{verdict='PASS'; const supports={}; for(const req of satisfied)supports[req]=support[req]; witness={kind:'SATISFACTION',satisfied_requirements:satisfied,supports};}
  return {control_id:control.id,verdict,requirement_count:Object.keys(control.require).length,witness};
}

function buildResolution(c,closure){const controls=Object.fromEntries(c.controls.map(x=>[x.id,x]));const targets={},verdicts={};for(const t of c.targets){const r=controlVerdict(controls[t],closure);targets[t]=r;verdicts[t]=r.verdict;}let state,reason_codes;if(Object.values(verdicts).includes('ABSTAIN')){state='ABSTAIN';reason_codes=['TARGET_CONTRADICTION'];}else if(Object.values(verdicts).includes('INCOMPLETE')){state='INCOMPLETE';reason_codes=['TARGET_STRUCTURE_INCOMPLETE'];}else{state='RESOLVED';reason_codes=['TARGETS_STRUCTURALLY_RESOLVED'];}return{state,reason_codes,verdicts:sortObj(verdicts),targets:sortObj(targets)};}

function candKey(c){const e=[...c.e].sort(),r=[...c.r].sort();return[c.e.size+c.r.size,c.e.size,c.r.size,e,r];}
function cmpCand(a,b){const ka=candKey(a),kb=candKey(b);for(let i=0;i<3;i++)if(ka[i]!==kb[i])return ka[i]-kb[i];let c=cmpArray(ka[3],kb[3]);if(c)return c;return cmpArray(ka[4],kb[4]);}
function subset(a,b){for(const x of a)if(!b.has(x))return false;return true;}
function addCandidate(arr,c){for(const x of arr)if(subset(x.e,c.e)&&subset(x.r,c.r))return false;const kept=arr.filter(x=>!(subset(c.e,x.e)&&subset(c.r,x.r)));kept.push(c);kept.sort(cmpCand);if(kept.length>MAX_PROOF_CANDIDATES_PER_LITERAL)fail('WITNESS_CANDIDATE_LIMIT');arr.splice(0,arr.length,...kept);return true;}
function combineCandidateLists(lists,extra){let combos=[{e:new Set(),r:new Set()}];for(const list of lists){const next=[];for(const b of combos)for(const c of list){const e=new Set([...b.e,...c.e]),r=new Set([...b.r,...c.r]);addCandidate(next,{e,r});if(next.length>MAX_WITNESS_COMBINATIONS)fail('WITNESS_COMBINATION_LIMIT');}combos=next;}if(extra!==null){const out=[];for(const c of combos)addCandidate(out,{e:new Set(c.e),r:new Set([...c.r,extra])});combos=out;}return combos;}
function deriveProofCandidates(c,closure){const m={};for(const e of c.evidence)for(const [a,v] of Object.entries(e.claims)){const k=literalKey(a,v);if(!m[k])m[k]=[];addCandidate(m[k],{e:new Set([e.id]),r:new Set()});}const fired=new Set(closure.rule_firings.map(x=>x.rule_id));let changed=true;while(changed){changed=false;for(const rule of c.rules){if(!fired.has(rule.id))continue;const p=Object.entries(rule.if_all).map(([a,v])=>literalKey(a,v));if(p.some(k=>!m[k]||!m[k].length))continue;const [a,v]=Object.entries(rule.then)[0],k=literalKey(a,v);const gen=combineCandidateLists(p.map(x=>m[x]),rule.id);if(!m[k])m[k]=[];for(const cand of gen)if(addCandidate(m[k],cand))changed=true;}}const out={};for(const k of Object.keys(m).sort())out[k]=m[k].sort(cmpCand);return out;}
function identityMaps(c){return [Object.fromEntries(c.evidence.map((x,i)=>[x.id,c.evidence_ids[i]])),Object.fromEntries(c.rules.map((x,i)=>[x.id,c.rule_ids[i]])),Object.fromEntries(c.controls.map((x,i)=>[x.id,c.control_ids[i]]))];}

function targetDependencyCone(c,target){const control=Object.fromEntries(c.controls.map(x=>[x.id,x]))[target];const by={};for(const r of c.rules){const [a,v]=Object.entries(r.then)[0],k=literalKey(a,v);(by[k]||(by[k]=[])).push(r);}const q=[];for(const [a,v] of Object.entries(control.require)){q.push(literalKey(a,v),literalKey(a,!v));}const seen=new Set(),rr=new Set();for(let i=0;i<q.length;i++){const k=q[i];if(seen.has(k))continue;seen.add(k);for(const r of by[k]||[]){rr.add(r.id);for(const [a,v] of Object.entries(r.if_all))q.push(literalKey(a,v),literalKey(a,!v));}}const atoms=new Set([...seen].map(x=>parseLiteralKey(x)[0])),ev=new Set();for(const e of c.evidence)if(Object.entries(e.claims).some(([a,v])=>seen.has(literalKey(a,v))))ev.add(e.id);const [em,rm,cm]=identityMaps(c),allE=new Set(c.evidence.map(x=>x.id)),allR=new Set(c.rules.map(x=>x.id)),allA=new Set(c.atoms);const diff=(a,b)=>[...a].filter(x=>!b.has(x)).sort();return{control_id:target,control_identity_id:cm[target],literals:[...seen].sort(),atoms:[...atoms].sort(),evidence_sources:[...ev].sort(),evidence_identity_ids:[...ev].sort().map(x=>em[x]),rules:[...rr].sort(),rule_identity_ids:[...rr].sort().map(x=>rm[x]),excluded_atoms:diff(allA,atoms),excluded_evidence_sources:diff(allE,ev),excluded_rules:diff(allR,rr)};}

function witnessSource(c,target,eids,rids){const control=deepClone(c.controls.find(x=>x.id===target));const evidence=c.evidence.filter(x=>eids.has(x.id)).map(deepClone),rules=c.rules.filter(x=>rids.has(x.id)).map(deepClone),atoms=new Set(Object.keys(control.require));for(const e of evidence)for(const a of Object.keys(e.claims))atoms.add(a);for(const r of rules){for(const a of Object.keys(r.if_all))atoms.add(a);for(const a of Object.keys(r.then))atoms.add(a);}return{schema:INPUT_SCHEMA,atoms:[...atoms].sort(),targets:[target],evidence,rules,controls:[control]};}
function restrictedResult(c,target,eids,rids){const rc=normalizeStructure(witnessSource(c,target,eids,rids));const res=buildResolution(rc,deriveClosure(rc));return[rc,res.targets[target]];}
function literalPath(c){return{evidence_sources:[...c.e].sort(),rules:[...c.r].sort()};}
function witnessCmp(a,b){for(const k of ['source_count','evidence_count','rule_count'])if(a[k]!==b[k])return a[k]-b[k];let c=cmpArray(a.evidence_sources,b.evidence_sources);if(c)return c;c=cmpArray(a.rules,b.rules);if(c)return c;return cmpText(canonicalJson(a.derivation_paths||{}),canonicalJson(b.derivation_paths||{}));}
function materializeWitness(c,target,verdict,eids,rids,paths,decisive){const [restricted,tr]=restrictedResult(c,target,eids,rids);if(tr.verdict!==verdict)return null;const [em,rm,cm]=identityMaps(c),es=[...eids].sort(),rs=[...rids].sort();const core={semantics:'DECLARED_STRUCTURE_ONLY',optimization_metric:'MIN_EVIDENCE_PLUS_RULE_COUNT_THEN_CANONICAL',target,control_identity_id:cm[target],verdict,decisive_literals:[...decisive].sort(),evidence_sources:es,evidence_identity_ids:es.map(x=>em[x]),rules:rs,rule_identity_ids:rs.map(x=>rm[x]),evidence_count:es.length,rule_count:rs.length,source_count:es.length+rs.length,derivation_paths:paths,witness_structure_id:restricted.canonical_structure_id,reproduced_verdict:tr.verdict};return{...core,witness_id:identity('slang_audit_minimal_witness_sha256',core)};}

function minimalTargetWitness(c,closure,target,tr,pc){const control=c.controls.find(x=>x.id===target),verdict=tr.verdict,choices=[];let examined=0;if(verdict==='PASS'){const req=Object.entries(control.require).map(([a,v])=>literalKey(a,v)),lists=req.map(k=>pc[k]||[]);if(lists.some(x=>!x.length))fail('PASS_WITNESS_UNAVAILABLE');let combos=[{e:new Set(),r:new Set(),p:{}}];for(let z=0;z<req.length;z++){const next=[],seen=new Set();for(const b of combos)for(const cand of lists[z]){if(++examined>MAX_WITNESS_COMBINATIONS)fail('WITNESS_COMBINATION_LIMIT');const e=new Set([...b.e,...cand.e]),r=new Set([...b.r,...cand.r]),p={...b.p,[req[z]]:literalPath(cand)},k=canonicalJson({e:[...e].sort(),r:[...r].sort(),p});if(!seen.has(k)){seen.add(k);next.push({e,r,p});}}combos=next;}for(const x of combos){const w=materializeWitness(c,target,verdict,x.e,x.r,x.p,req);if(w)choices.push(w);}}
  else if(verdict==='VIOLATED'){for(const [a,v] of Object.entries(control.require)){const opp=literalKey(a,!v);for(const cand of pc[opp]||[]){if(++examined>MAX_WITNESS_COMBINATIONS)fail('WITNESS_COMBINATION_LIMIT');const w=materializeWitness(c,target,verdict,new Set(cand.e),new Set(cand.r),{[opp]:literalPath(cand)},[opp]);if(w)choices.push(w);}}}
  else if(verdict==='ABSTAIN'){for(const [a,v] of Object.entries(control.require)){const req=literalKey(a,v),opp=literalKey(a,!v);for(const x of pc[req]||[])for(const y of pc[opp]||[]){if(++examined>MAX_WITNESS_COMBINATIONS)fail('WITNESS_COMBINATION_LIMIT');const e=new Set([...x.e,...y.e]),r=new Set([...x.r,...y.r]),p={[req]:literalPath(x),[opp]:literalPath(y)};const w=materializeWitness(c,target,verdict,e,r,p,[req,opp]);if(w)choices.push(w);}}}
  if(verdict==='INCOMPLETE')return null;if(!choices.length)fail('MINIMAL_WITNESS_UNAVAILABLE');choices.sort(witnessCmp);return choices[0];}

function targetGoalLiterals(c,target){const control=c.controls.find(x=>x.id===target),by={};for(const r of c.rules){const [a,v]=Object.entries(r.then)[0],k=literalKey(a,v);(by[k]||(by[k]=[])).push(r);}const q=Object.entries(control.require).map(([a,v])=>literalKey(a,v)),seen=new Set();for(let i=0;i<q.length;i++){const k=q[i];if(seen.has(k))continue;seen.add(k);for(const r of by[k]||[])for(const [a,v] of Object.entries(r.if_all))q.push(literalKey(a,v));}return[...seen].sort();}
function cfSource(c,target,removed,added){const s=canonicalToSource(c),re=new Set([...removed].filter(x=>x.startsWith('evidence:')).map(x=>x.slice(9))),rr=new Set([...removed].filter(x=>x.startsWith('rule:')).map(x=>x.slice(5)));s.targets=[target];s.controls=s.controls.filter(x=>x.id===target);s.evidence=s.evidence.filter(x=>!re.has(x.id));s.rules=s.rules.filter(x=>!rr.has(x.id));const ids=new Set(s.evidence.map(x=>x.id));for(const key of [...added].sort()){const [a,v]=parseLiteralKey(key),seed='counterfactual_'+sha256Text(key).slice(0,16);let id=seed,n=0;while(ids.has(id)){n++;id=seed+'_'+n;}ids.add(id);s.evidence.push({id,claims:{[a]:v},commitment:null});}return s;}
function cfResult(c,target,removed,added){const r=normalizeStructure(cfSource(c,target,removed,added)),res=buildResolution(r,deriveClosure(r));return[res.targets[target].verdict,r.canonical_structure_id];}
function cfSources(c,target){const cone=targetDependencyCone(c,target);return[...cone.evidence_sources.map(x=>'evidence:'+x),...cone.rules.map(x=>'rule:'+x)].sort();}
function goalAdds(c,closure,target){return targetGoalLiterals(c,target).filter(k=>!supportHas(closure.support,k)).sort();}
function removalParts(items){return[[...items].filter(x=>x.startsWith('evidence:')).map(x=>x.slice(9)).sort(),[...items].filter(x=>x.startsWith('rule:')).map(x=>x.slice(5)).sort()];}
function* combinations(a,k,start=0,p=[]){if(p.length===k){yield [...p];return;}for(let i=start;i<=a.length-(k-p.length);i++){p.push(a[i]);yield* combinations(a,k,i+1,p);p.pop();}}
function cutCmp(a,b){if(a.change_count!==b.change_count)return a.change_count-b.change_count;const ta=[...a.removed_evidence_sources.map(x=>'evidence:'+x),...a.removed_rules.map(x=>'rule:'+x)].sort(),tb=[...b.removed_evidence_sources.map(x=>'evidence:'+x),...b.removed_rules.map(x=>'rule:'+x)].sort();let c=cmpArray(ta,tb);if(c)return c;return cmpText(a.counterfactual_verdict,b.counterfactual_verdict);}
function repairCmp(a,b){for(const k of ['change_count','removed_source_count','added_literal_count'])if(a[k]!==b[k])return a[k]-b[k];let c=cmpArray(a.removed_evidence_sources,b.removed_evidence_sources);if(c)return c;c=cmpArray(a.removed_rules,b.removed_rules);if(c)return c;return cmpArray(a.added_literals,b.added_literals);}
function minimalCut(c,target,base){const sources=cfSources(c,target);if(!sources.length)return{status:'NO_DECLARED_SOURCE_CUT_AVAILABLE',baseline_verdict:base};if(sources.length>MAX_COUNTERFACTUAL_CANDIDATE_SOURCES)return{status:'RESOURCE_LIMIT',baseline_verdict:base,candidate_source_count:sources.length};let evals=0;for(let size=1;size<=sources.length;size++){const matches=[];for(const combo of combinations(sources,size)){if(++evals>MAX_COUNTERFACTUAL_EVALUATIONS)return{status:'RESOURCE_LIMIT',baseline_verdict:base,evaluations:evals};const [v,sid]=cfResult(c,target,new Set(combo),new Set());if(v!==base){const [e,r]=removalParts(combo),core={semantics:'DECLARED_STRUCTURE_SOURCE_REMOVAL_ONLY',target,baseline_verdict:base,counterfactual_verdict:v,removed_evidence_sources:e,removed_rules:r,removed_evidence_count:e.length,removed_rule_count:r.length,change_count:combo.length,counterfactual_structure_id:sid},idcore={...core};delete idcore.counterfactual_structure_id;matches.push({...core,cut_id:identity('slang_audit_minimal_cut_sha256',idcore)});}}if(matches.length){matches.sort(cutCmp);return{status:'AVAILABLE',exact_within_declared_resource_bounds:true,minimal_change_count:size,minimal_cut_count:matches.length,selected:matches[0],evaluations:evals};}}return{status:'NO_DECLARED_SOURCE_CUT_AVAILABLE',baseline_verdict:base,evaluations:evals};}
function minimalCompletion(c,closure,target,base){if(base!=='INCOMPLETE')return{status:'NOT_APPLICABLE',baseline_verdict:base};const adds=goalAdds(c,closure,target);if(!adds.length)return{status:'NO_LITERAL_COMPLETION_AVAILABLE',baseline_verdict:base};if(adds.length>MAX_COUNTERFACTUAL_CANDIDATE_LITERALS)return{status:'RESOURCE_LIMIT',baseline_verdict:base,candidate_literal_count:adds.length};let evals=0;for(let size=1;size<=adds.length;size++){const m=[];for(const combo of combinations(adds,size)){if(++evals>MAX_COUNTERFACTUAL_EVALUATIONS)return{status:'RESOURCE_LIMIT',baseline_verdict:base,evaluations:evals};const[v,sid]=cfResult(c,target,new Set(),new Set(combo));if(v==='PASS'){const core={semantics:'HYPOTHETICAL_DECLARED_LITERAL_ADDITION_ONLY',target,baseline_verdict:base,counterfactual_verdict:v,added_literals:[...combo].sort(),change_count:combo.length,counterfactual_structure_id:sid},idcore={...core};delete idcore.counterfactual_structure_id;m.push({...core,completion_id:identity('slang_audit_completion_frontier_sha256',idcore)});}}if(m.length){m.sort((a,b)=>a.change_count-b.change_count||cmpArray(a.added_literals,b.added_literals));return{status:'AVAILABLE',exact_within_declared_resource_bounds:true,minimal_change_count:size,minimal_completion_count:m.length,selected:m[0],evaluations:evals};}}return{status:'NO_LITERAL_COMPLETION_AVAILABLE',baseline_verdict:base,evaluations:evals};}
function minimalRepair(c,closure,target,base){if(base==='PASS')return{status:'NOT_APPLICABLE_ALREADY_PASS',baseline_verdict:base};const sources=cfSources(c,target),adds=goalAdds(c,closure,target);if(sources.length>MAX_COUNTERFACTUAL_CANDIDATE_SOURCES||adds.length>MAX_COUNTERFACTUAL_CANDIDATE_LITERALS)return{status:'RESOURCE_LIMIT',baseline_verdict:base,candidate_source_count:sources.length,candidate_literal_count:adds.length};let evals=0;for(let total=1;total<=sources.length+adds.length;total++){const m=[];for(let rc=Math.max(0,total-adds.length);rc<=Math.min(total,sources.length);rc++){const ac=total-rc;for(const rem of combinations(sources,rc))for(const add of combinations(adds,ac)){if(++evals>MAX_COUNTERFACTUAL_EVALUATIONS)return{status:'RESOURCE_LIMIT',baseline_verdict:base,evaluations:evals};const[v,sid]=cfResult(c,target,new Set(rem),new Set(add));if(v==='PASS'){const[e,r]=removalParts(rem),core={semantics:'DECLARED_SOURCE_REMOVAL_PLUS_HYPOTHETICAL_LITERAL_ADDITION',target,baseline_verdict:base,counterfactual_verdict:v,removed_evidence_sources:e,removed_rules:r,added_literals:[...add].sort(),removed_source_count:rem.length,added_literal_count:add.length,change_count:total,counterfactual_structure_id:sid},idcore={...core};delete idcore.counterfactual_structure_id;m.push({...core,repair_id:identity('slang_audit_minimal_repair_sha256',idcore)});}}}if(m.length){m.sort(repairCmp);return{status:'AVAILABLE',exact_within_declared_resource_bounds:true,minimal_change_count:total,minimal_repair_count:m.length,selected:m[0],evaluations:evals};}}return{status:'NO_REPAIR_TO_PASS_AVAILABLE',baseline_verdict:base,evaluations:evals};}
function counterfactualAnalysis(c,closure,target,tr,w){const base=tr.verdict;return{semantics:'TARGET_SPECIFIC_DECLARED_STRUCTURE_COUNTERFACTUAL_ONLY',baseline_verdict:base,minimal_verdict_cut:minimalCut(c,target,base),completion_frontier:minimalCompletion(c,closure,target,base),minimal_repair_to_pass:minimalRepair(c,closure,target,base),decisive_witness_id:w===null?null:w.witness_id};}
function targetAnalysisItem(c,closure,target,tr,pc){const w=minimalTargetWitness(c,closure,target,tr,pc);return{dependency_cone:targetDependencyCone(c,target),minimal_sufficient_witness:w,witness_status:w===null?'NOT_APPLICABLE_INCOMPLETE_TARGET':'AVAILABLE',counterfactual_analysis:counterfactualAnalysis(c,closure,target,tr,w)};}
function buildTargetAnalysis(c,closure,res){const pc=deriveProofCandidates(c,closure),a={};for(const t of c.targets)a[t]=targetAnalysisItem(c,closure,t,res.targets[t],pc);return sortObj(a);}
function actionProjection(v,idkey){const out={status:v.status??null,baseline_verdict:v.baseline_verdict??null};for(const k of ['minimal_change_count','minimal_cut_count','minimal_completion_count','minimal_repair_count'])if(Object.prototype.hasOwnProperty.call(v,k))out[k]=v[k];if(isObject(v.selected)){out.selected_id=v.selected[idkey]??null;out.counterfactual_verdict=v.selected.counterfactual_verdict??null;}return out;}
function targetProjection(target,tr,a){const c=a.dependency_cone,cone={control_id:c.control_id,control_identity_id:c.control_identity_id,atoms:c.atoms,literals:c.literals,evidence_sources:c.evidence_sources,evidence_identity_ids:c.evidence_identity_ids,rules:c.rules,rule_identity_ids:c.rule_identity_ids},w=a.minimal_sufficient_witness,cf=a.counterfactual_analysis;return{target,target_result:tr,dependency_cone:cone,witness_status:a.witness_status,minimal_witness_id:w===null?null:w.witness_id,minimal_verdict_cut:actionProjection(cf.minimal_verdict_cut,'cut_id'),completion_frontier:actionProjection(cf.completion_frontier,'completion_id'),minimal_repair_to_pass:actionProjection(cf.minimal_repair_to_pass,'repair_id')};}
function targetProofIds(res,a){const out={};for(const t of Object.keys(a).sort())out[t]=identity('slang_audit_target_proof_sha256',targetProjection(t,res.targets[t],a[t]));return out;}

function certificateFromCanonical(c){const closure=deriveClosure(c),resolution=buildResolution(c,closure),ta=buildTargetAnalysis(c,closure,resolution),tp=targetProofIds(resolution,ta);const proof={schema:PROOF_SCHEMA,declared_evidence_only:true,external_truth_verified:false,external_source_provenance_verified:false,replay_performed:false,reconciliation_performed:false,closure,target_analysis:ta,target_proof_ids:tp,target_proof_semantics:'TARGET_LOCAL_IDENTITY_EXCLUDES_UNRELATED_DECLARED_STRUCTURE',minimal_witness_semantics:'TARGET_SPECIFIC_DECLARED_STRUCTURE_ONLY',minimal_witness_search:{exact_within_declared_resource_bounds:true,candidate_limit_per_literal:512,combination_limit_per_target:16384,silent_truncation:false},counterfactual_semantics:'DECLARED_STRUCTURE_ONLY_NO_REAL_WORLD_AUDIT_AUTHORITY',counterfactual_search:{exact_when_status_available:true,candidate_source_limit:24,candidate_literal_limit:24,evaluation_limit_per_analysis:65536,silent_truncation:false},evidence_commitments:{declared_evidence_count:c.evidence.length,committed_evidence_count:c.evidence.filter(x=>x.commitment!==null).length,all_evidence_committed:c.evidence.length>0&&c.evidence.every(x=>x.commitment!==null),commitment_semantics:'IDENTITY_BINDING_ONLY'}};const core={schema:CERTIFICATE_SCHEMA,version:VERSION,profile_id:PROFILE_ID,canonical_structure_id:c.canonical_structure_id,state:resolution.state,reason_codes:resolution.reason_codes,resolution,proof,authority:'NONE'};return{...core,certificate_id:identity('slang_audit_certificate_sha256',core)};}
function resolveStructure(raw){const c=normalizeStructure(raw),cert=certificateFromCanonical(c),core={schema:BUNDLE_SCHEMA,version:VERSION,canonical_structure:c,certificate:cert};return{...core,bundle_id:identity('slang_audit_bundle_sha256',core)};}

function verifyBundle(bundle){try{if(!isObject(bundle)||!keysExact(bundle,['schema','version','canonical_structure','certificate','bundle_id']))return[false,'INVALID_BUNDLE_FIELDS'];if(bundle.schema!==BUNDLE_SCHEMA||bundle.version!==VERSION)return[false,'INVALID_BUNDLE_SCHEMA_VERSION'];const bc={...bundle};delete bc.bundle_id;if(bundle.bundle_id!==identity('slang_audit_bundle_sha256',bc))return[false,'BUNDLE_ID_MISMATCH'];if(!isObject(bundle.certificate))return[false,'INVALID_CERTIFICATE_TYPE'];const cc={...bundle.certificate};delete cc.certificate_id;if(bundle.certificate.certificate_id!==identity('slang_audit_certificate_sha256',cc))return[false,'CERTIFICATE_ID_MISMATCH'];const c=bundle.canonical_structure;if(c===null){return[['FORBIDDEN','UNSUPPORTED'].includes(bundle.certificate.state),'ERROR_BUNDLE_STATE'];}if(!isObject(c))return[false,'INVALID_CANONICAL_STRUCTURE'];const ren=normalizeStructure(canonicalToSource(c));if(!same(ren,c))return[false,'CANONICAL_STRUCTURE_MISMATCH'];if(bundle.certificate.canonical_structure_id!==c.canonical_structure_id)return[false,'CERTIFICATE_STRUCTURE_BINDING_MISMATCH'];const expected=certificateFromCanonical(c);if(!same(expected,bundle.certificate))return[false,'CERTIFICATE_RECOMPUTATION_MISMATCH'];return[true,'PASS'];}catch(e){return[false,'VERIFY_EXCEPTION_'+(e.code||e.message)];}}

function normalizeDelta(raw,base){if(!isObject(raw)||raw.schema!==DELTA_SCHEMA||raw.base_bundle_id!==base.bundle_id)fail('INVALID_DELTA');const allowed=['schema','base_bundle_id','remove_evidence','upsert_evidence','remove_rules','upsert_rules','delta_id'];if(Object.keys(raw).some(k=>!allowed.includes(k)))fail('UNKNOWN_DELTA_FIELD');const c=base.canonical_structure,atoms=new Set(c.atoms);const remE=[...(raw.remove_evidence||[])].map(validateIdentifier).sort(),remR=[...(raw.remove_rules||[])].map(validateIdentifier).sort();if(new Set(remE).size!==remE.length||new Set(remR).size!==remR.length)fail('DUPLICATE_DELTA_OPERATION');const baseE=new Set(c.evidence.map(x=>x.id)),baseR=new Set(c.rules.map(x=>x.id));if(remE.some(x=>!baseE.has(x))||remR.some(x=>!baseR.has(x)))fail('REMOVE_UNKNOWN_COMPONENT');const upE=(raw.upsert_evidence||[]).map(x=>{if(!isObject(x)||!keysExact(x,['id','claims','commitment']))fail('INVALID_DELTA_EVIDENCE');const id=validateIdentifier(x.id),claims=validateLiteralMap(x.claims);for(const a of Object.keys(claims))if(!atoms.has(a))fail('UNDECLARED_ATOM');if(x.commitment!==null&&(typeof x.commitment!=='string'||!COMMITMENT_RE.test(x.commitment)))fail('INVALID_EVIDENCE_COMMITMENT');return{id,claims,commitment:x.commitment};}).sort((a,b)=>cmpText(a.id,b.id));const upR=(raw.upsert_rules||[]).map(x=>{if(!isObject(x)||!keysExact(x,['id','if_all','then']))fail('INVALID_DELTA_RULE');const id=validateIdentifier(x.id),if_all=validateLiteralMap(x.if_all),then=validateLiteralMap(x.then);if(Object.keys(then).length!==1)fail('INVALID_DELTA_RULE');for(const a of [...Object.keys(if_all),...Object.keys(then)])if(!atoms.has(a))fail('UNDECLARED_ATOM');return{id,if_all,then};}).sort((a,b)=>cmpText(a.id,b.id));if(new Set(upE.map(x=>x.id)).size!==upE.length||new Set(upR.map(x=>x.id)).size!==upR.length)fail('DUPLICATE_DELTA_UPSERT');if(remE.some(x=>upE.some(y=>y.id===x))||remR.some(x=>upR.some(y=>y.id===x)))fail('DELTA_REMOVE_UPSERT_CONFLICT');const core={schema:DELTA_SCHEMA,base_bundle_id:base.bundle_id,remove_evidence:remE,upsert_evidence:upE,remove_rules:remR,upsert_rules:upR},did=identity('slang_audit_delta_sha256',core);if(raw.delta_id!==undefined&&raw.delta_id!==did)fail('DELTA_ID_MISMATCH');return{...core,delta_id:did};}
function applyDelta(c,d){const s=canonicalToSource(c),e=Object.fromEntries(s.evidence.map(x=>[x.id,x])),r=Object.fromEntries(s.rules.map(x=>[x.id,x]));for(const id of d.remove_evidence)delete e[id];for(const x of d.upsert_evidence)e[x.id]=deepClone(x);for(const id of d.remove_rules)delete r[id];for(const x of d.upsert_rules)r[x.id]=deepClone(x);s.evidence=Object.keys(e).sort().map(k=>e[k]);s.rules=Object.keys(r).sort().map(k=>r[k]);return s;}
function changedTargets(oldc,newc){const changed=new Set(),oe=Object.fromEntries(oldc.evidence.map(x=>[x.id,x])),ne=Object.fromEntries(newc.evidence.map(x=>[x.id,x]));for(const id of new Set([...Object.keys(oe),...Object.keys(ne)])){const a=oe[id],b=ne[id];if((a===undefined||b===undefined)?a!==b:!same(a,b)){if(a)Object.keys(a.claims).forEach(x=>changed.add(x));if(b)Object.keys(b.claims).forEach(x=>changed.add(x));}}const or=Object.fromEntries(oldc.rules.map(x=>[x.id,x])),nr=Object.fromEntries(newc.rules.map(x=>[x.id,x]));for(const id of new Set([...Object.keys(or),...Object.keys(nr)])){const a=or[id],b=nr[id];if((a===undefined||b===undefined)?a!==b:!same(a,b)){if(a)Object.keys(a.then).forEach(x=>changed.add(x));if(b)Object.keys(b.then).forEach(x=>changed.add(x));}}const uniq=[],seen=new Set();for(const x of [...oldc.rules,...newc.rules]){const k=canonicalJson(x);if(!seen.has(k)){seen.add(k);uniq.push(x);}}let progress=true;while(progress){progress=false;for(const r of uniq)if(Object.keys(r.if_all).some(x=>changed.has(x))){const a=Object.keys(r.then)[0];if(!changed.has(a)){changed.add(a);progress=true;}}}const controls=Object.fromEntries(newc.controls.map(x=>[x.id,x]));return[[...changed].sort(),newc.targets.filter(t=>Object.keys(controls[t].require).some(a=>changed.has(a))).sort()];}
function buildIncremental(base,raw){const vb=verifyBundle(base);if(!vb[0])fail('INVALID_BASE_BUNDLE');const d=normalizeDelta(raw,base),updated=resolveStructure(applyDelta(base.canonical_structure,d)),oldc=base.canonical_structure,newc=updated.canonical_structure,[affected,impacted]=changedTargets(oldc,newc),oldids=base.certificate.proof.target_proof_ids,newids=updated.certificate.proof.target_proof_ids,changed=newc.targets.filter(t=>oldids[t]!==newids[t]).sort(),preserved=newc.targets.filter(t=>oldids[t]===newids[t]).sort();if(changed.some(t=>!impacted.includes(t)))fail('DEPENDENCY_IMPACT_UNDERSPECIFIED');const transitions={};for(const t of impacted)transitions[t]={from:base.certificate.resolution.targets[t].verdict,to:updated.certificate.resolution.targets[t].verdict,proof_changed:oldids[t]!==newids[t]};const dc={schema:DELTA_CERTIFICATE_SCHEMA,version:VERSION,base_bundle_id:base.bundle_id,base_structure_id:oldc.canonical_structure_id,delta_id:d.delta_id,updated_bundle_id:updated.bundle_id,updated_structure_id:newc.canonical_structure_id,affected_atoms:affected,dependency_impacted_targets:impacted,proof_changed_targets:changed,preserved_targets:preserved,transitions,recomputed_target_proof_ids:Object.fromEntries(impacted.map(t=>[t,newids[t]])),preserved_target_proof_ids:Object.fromEntries(preserved.map(t=>[t,oldids[t]])),incremental_semantics:'DEPENDENCY_SCOPED_TARGET_PROOF_RECOMPUTATION_WITH_FULL_EQUIVALENCE_GUARD',full_recomputation_equivalence:true,external_truth_verified:false,external_source_provenance_verified:false,audit_opinion_authority:'NONE'},cert={...dc,delta_certificate_id:identity('slang_audit_delta_certificate_sha256',dc)},core={schema:INCREMENTAL_BUNDLE_SCHEMA,version:VERSION,base_bundle:base,delta:d,delta_certificate:cert,updated_bundle:updated};return{...core,incremental_bundle_id:identity('slang_audit_incremental_bundle_sha256',core)};}
function verifyIncremental(v){try{if(!isObject(v)||v.schema!==INCREMENTAL_BUNDLE_SCHEMA||v.version!==VERSION)return[false,'INVALID_INCREMENTAL_SCHEMA'];const core={...v};delete core.incremental_bundle_id;if(v.incremental_bundle_id!==identity('slang_audit_incremental_bundle_sha256',core))return[false,'INCREMENTAL_BUNDLE_ID_MISMATCH'];const exp=buildIncremental(v.base_bundle,v.delta);return same(exp,v)?[true,'PASS']:[false,'INCREMENTAL_RECOMPUTATION_MISMATCH'];}catch(e){return[false,'INCREMENTAL_EXCEPTION_'+(e.code||e.message)];}}
function buildLedger(genesis,deltas){const vb=verifyBundle(genesis);if(!vb[0])fail('INVALID_LEDGER_GENESIS');if(!Array.isArray(deltas)||deltas.length>MAX_LEDGER_ENTRIES)fail('INVALID_LEDGER_DELTAS');let current=genesis,pred=null;const entries=[];for(let i=0;i<deltas.length;i++){const inc=buildIncremental(current,deltas[i]),d=inc.delta,dc=inc.delta_certificate,u=inc.updated_bundle,core={index:i+1,predecessor_entry_id:pred,base_bundle_id:current.bundle_id,base_structure_id:current.canonical_structure.canonical_structure_id,delta:d,delta_id:d.delta_id,delta_certificate_id:dc.delta_certificate_id,incremental_bundle_id:inc.incremental_bundle_id,updated_bundle_id:u.bundle_id,updated_structure_id:u.canonical_structure.canonical_structure_id,dependency_impacted_targets:dc.dependency_impacted_targets,proof_changed_targets:dc.proof_changed_targets,preserved_targets:dc.preserved_targets,transitions:dc.transitions},entry={...core,entry_id:identity('slang_audit_ledger_entry_sha256',core)};entries.push(entry);pred=entry.entry_id;current=u;}const entryIds=entries.map(x=>x.entry_id),lineage=identity('slang_audit_lineage_root_sha256',{genesis_bundle_id:genesis.bundle_id,entry_ids:entryIds}),cc={schema:LEDGER_CHECKPOINT_SCHEMA,version:VERSION,genesis_bundle_id:genesis.bundle_id,genesis_structure_id:genesis.canonical_structure.canonical_structure_id,entry_count:entries.length,lineage_root_id:lineage,last_entry_id:entries.length?entries[entries.length-1].entry_id:null,terminal_bundle_id:current.bundle_id,terminal_structure_id:current.canonical_structure.canonical_structure_id,terminal_certificate_id:current.certificate.certificate_id,terminal_target_proof_ids:current.certificate.proof.target_proof_ids,checkpoint_semantics:'PINNED_LINEAGE_IDENTITY_REQUIRED_TO_DETECT_REBUILT_ALTERNATIVE_HISTORY',external_truth_verified:false,external_source_provenance_verified:false,audit_opinion_authority:'NONE'},checkpoint={...cc,checkpoint_id:identity('slang_audit_ledger_checkpoint_sha256',cc)},lc={schema:LEDGER_SCHEMA,version:VERSION,genesis_bundle:genesis,entries,terminal_bundle:current,checkpoint,lineage_semantics:'ORDERED_PREDECESSOR_BOUND_DECLARED_AUDIT_STATE_EVOLUTION',external_truth_verified:false,external_source_provenance_verified:false,audit_opinion_authority:'NONE'};return{...lc,ledger_id:identity('slang_audit_proof_ledger_sha256',lc)};}
function verifyCheckpoint(c){try{if(!isObject(c)||c.schema!==LEDGER_CHECKPOINT_SCHEMA||c.version!==VERSION)return[false,'INVALID_CHECKPOINT_SCHEMA'];const core={...c};delete core.checkpoint_id;return c.checkpoint_id===identity('slang_audit_ledger_checkpoint_sha256',core)?[true,'PASS']:[false,'CHECKPOINT_ID_MISMATCH'];}catch(e){return[false,'CHECKPOINT_EXCEPTION'];}}
function verifyLedger(v){try{if(!isObject(v)||v.schema!==LEDGER_SCHEMA||v.version!==VERSION||!Array.isArray(v.entries))return[false,'INVALID_LEDGER_SCHEMA'];const core={...v};delete core.ledger_id;if(v.ledger_id!==identity('slang_audit_proof_ledger_sha256',core))return[false,'LEDGER_ID_MISMATCH'];const exp=buildLedger(v.genesis_bundle,v.entries.map(x=>x.delta));return same(exp,v)?[true,'PASS']:[false,'LEDGER_RECOMPUTATION_MISMATCH'];}catch(e){return[false,'LEDGER_EXCEPTION_'+(e.code||e.message)];}}
function verifyLedgerCheckpoint(v,c){const x=verifyLedger(v);if(!x[0])return x;const y=verifyCheckpoint(c);if(!y[0])return y;return same(v.checkpoint,c)?[true,'PASS']:[false,'PINNED_CHECKPOINT_MISMATCH'];}

function load(path){return strictJson(fs.readFileSync(path,'utf8'));}
function usage(){process.stderr.write('usage: node SLANG_Audit_Standalone_Verifier_v1_0_0.js --self-test | --verify-bundle FILE | --verify-incremental FILE | --verify-ledger FILE | --verify-ledger-checkpoint LEDGER CHECKPOINT\n');return 2;}
function selfTest(){let n=0,p=0;const t=x=>{n++;if(x)p++;};t(sha256Text('abc')==='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');t(canonicalJson({b:1,a:'x'})==='{"a":"x","b":1}');try{strictJson('{"a":1,"a":2}');t(false);}catch(_){t(true);}try{strictJson('{"a":1.2}');t(false);}catch(_){t(true);}console.log('SLANG-Audit JavaScript standalone verifier v1.0.0 self-test');console.log('TOTAL '+p+'/'+n+' '+(p===n?'PASS':'FAIL'));return p===n?0:1;}
function main(){const a=process.argv.slice(2);if(a.length===1&&a[0]==='--self-test')return selfTest();let r;if(a.length===2&&a[0]==='--verify-bundle')r=verifyBundle(load(a[1]));else if(a.length===2&&a[0]==='--verify-incremental')r=verifyIncremental(load(a[1]));else if(a.length===2&&a[0]==='--verify-ledger')r=verifyLedger(load(a[1]));else if(a.length===3&&a[0]==='--verify-ledger-checkpoint')r=verifyLedgerCheckpoint(load(a[1]),load(a[2]));else return usage();console.log(r[0]?'PASS':'FAIL:'+r[1]);return r[0]?0:1;}
process.exitCode=main();
