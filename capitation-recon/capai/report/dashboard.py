"""Self-contained HTML review console for the close (no external assets)."""
from __future__ import annotations

import json

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Capitation Close Review Console</title>
<style>
:root{--ink:#14213d;--mut:#5c6b80;--line:#e3e8ef;--bg:#f6f8fb;--card:#fff;--acc:#1f4e9c;--ok:#1d7a4f;--warn:#b7791f;--bad:#b42318;--soft:#eef3fb}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 -apple-system,Segoe UI,Inter,Arial,sans-serif;color:var(--ink);background:var(--bg)}
header{background:var(--ink);color:#fff;padding:18px 28px;display:flex;justify-content:space-between;align-items:center}
header h1{font-size:18px;margin:0;font-weight:600}header .sub{color:#b9c4d6;font-size:12px}
nav{display:flex;gap:4px;padding:0 28px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:2}
nav button{border:0;background:none;padding:12px 14px;font:inherit;color:var(--mut);cursor:pointer;border-bottom:2px solid transparent}
nav button.on{color:var(--acc);border-color:var(--acc);font-weight:600}
main{padding:22px 28px;max-width:1320px;margin:auto}section{display:none}section.on{display:block}
.grid{display:grid;gap:14px}.k4{grid-template-columns:repeat(4,1fr)}.k2{grid-template-columns:1.3fr 1fr}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.kpi .v{font-size:24px;font-weight:650;font-variant-numeric:tabular-nums}.kpi .l{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.kpi .s{color:var(--mut);font-size:12px;margin-top:2px}
h2{font-size:15px;margin:0 0 10px}h3{font-size:13px;margin:14px 0 6px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:11px;text-transform:uppercase;color:var(--mut);letter-spacing:.04em;font-weight:600}td.n,th.n{text-align:right}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;font-weight:600}
.p-open{background:#fde8e7;color:var(--bad)}.p-pending{background:#fff4dc;color:var(--warn)}.p-ok{background:#e3f4ea;color:var(--ok)}.p-warn{background:#fff4dc;color:var(--warn)}
.cl{border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:10px;background:#fff}
.cl .top{display:flex;justify-content:space-between;gap:12px;align-items:baseline}.cl .amt{font-size:18px;font-weight:650;font-variant-numeric:tabular-nums}
.cl .ex{margin:8px 0;color:#2b3a52}.cl .meta{font-size:12px;color:var(--mut);display:flex;gap:16px;flex-wrap:wrap}
.cl .act{margin-top:10px;display:flex;gap:8px}.btn{border:1px solid var(--line);background:#fff;border-radius:7px;padding:5px 10px;font:inherit;font-size:12px;cursor:pointer}
.btn.pri{background:var(--acc);color:#fff;border-color:var(--acc)}.done{opacity:.55}
.ai{font-size:11px;color:var(--acc);background:var(--soft);padding:1px 6px;border-radius:4px}
pre{white-space:pre-wrap;font:13px/1.5 ui-monospace,Menlo,Consolas,monospace;background:#fbfcfe;border:1px solid var(--line);border-radius:8px;padding:14px}
.tri td{font-size:12px;text-align:right}.tri td.h{background:#fde3d3;font-weight:600}.tri td.d{background:#eef3fb}
.small{font-size:12px;color:var(--mut)}.flex{display:flex;gap:10px;align-items:center}
</style></head><body>
<header><div><h1>Capitation Revenue Close &mdash; Review Console</h1><div class="sub" id="hdr"></div></div><div class="sub">Synthetic demo data &middot; Sunrise Health Plan</div></header>
<nav id="nav"></nav><main>
<section id="overview"></section><section id="exceptions"></section><section id="rates"></section><section id="retro"></section><section id="cash"></section><section id="memo"></section>
</main>
<script>
const B = __DATA__;
const $=s=>document.querySelector(s);
const fm=(x,d=0)=>(x<0?'-':'')+'$'+Math.abs(x).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const f2=x=>fm(x,2), n0=x=>x.toLocaleString('en-US');
const tabs=[['overview','Overview'],['exceptions','Exceptions ('+B.clusters.length+')'],['rates','Rate intake'],['retro','Retro & prior periods'],['cash','Cash'],['memo','Close memo']];
$('#nav').innerHTML=tabs.map(([k,l],i)=>`<button data-k="${k}" class="${i?'':'on'}">${l}</button>`).join('');
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button,section').forEach(e=>e.classList.remove('on'));b.classList.add('on');$('#'+b.dataset.k).classList.add('on')});
$('#overview').classList.add('on');
const S=B.summary;$('#hdr').textContent=`${S.month} close · as of ${S.close_as_of.slice(0,10)} · ${n0(S.member_months)} member-months reconciled`;

// ---------------- overview
function bars(rows,key1,key2,w=560,h=200){const max=Math.max(...rows.map(r=>Math.max(r[key1],r[key2])));const bw=w/rows.length;let s=`<svg viewBox="0 0 ${w} ${h+28}" width="100%">`;
rows.forEach((r,i)=>{const x=i*bw+6,a=(r[key1]/max)*h,b=(r[key2]/max)*h;s+=`<rect x="${x}" y="${h-a}" width="${bw/2-6}" height="${a}" fill="#c9d6ea"><title>Expected ${f2(r[key1])}</title></rect><rect x="${x+bw/2-4}" y="${h-b}" width="${bw/2-6}" height="${b}" fill="#1f4e9c"><title>Paid incl. retro alloc ${f2(r[key2])}</title></rect><text x="${x+bw/2-5}" y="${h+16}" font-size="11" text-anchor="middle" fill="#5c6b80">${r.cov_month.slice(5)}</text>`});
return s+`</svg>`}
const bm=B.by_month.map(r=>({...r,paid_all:r.paid+r.alloc}));
const topC=B.clusters.slice(0,5);
$('#overview').innerHTML=`<div class="grid k4">
<div class="card kpi"><div class="l">Expected ${S.month}</div><div class="v">${fm(S.expected_month)}</div><div class="s">${n0(S.member_months_month)} member-months</div></div>
<div class="card kpi"><div class="l">Auto-reconciled</div><div class="v">${S.auto_matched_pct.toFixed(1)}%</div><div class="s">${n0(S.raw_variance_items)} raw variances &rarr; ${S.clusters} root causes</div></div>
<div class="card kpi"><div class="l">Open for review</div><div class="v">${n0(S.open_items)}</div><div class="s">net ${f2(S.open_variance)} &middot; ${S.unexplained_items} unexplained</div></div>
<div class="card kpi"><div class="l">Retro verified</div><div class="v">${fm(S.lump_sums_ytd)}</div><div class="s">state lump sum re-performed, residual ${f2(B.lumps[0]?.residual||0)}</div></div></div>
<div class="grid k2" style="margin-top:14px"><div class="card"><h2>Expected vs paid by coverage month (YTD)</h2>${bars(bm,'expected','paid_all')}<div class="small flex"><span style="width:10px;height:10px;background:#c9d6ea;display:inline-block"></span>Expected <span style="width:10px;height:10px;background:#1f4e9c;display:inline-block;margin-left:10px"></span>Paid (incl. allocated retro)</div></div>
<div class="card"><h2>Three-way tie-out (YTD)</h2><table>
<tr><td>Expected (roster &times; approved rates)</td><td class="n">${f2(S.expected_ytd)}</td></tr>
<tr><td>Paid on 820 member lines</td><td class="n">${f2(S.paid_ytd)}</td></tr>
<tr><td>Aggregate retro settlements</td><td class="n">${f2(S.lump_sums_ytd)}</td></tr>
<tr><td><b>Open variance</b></td><td class="n"><b>${f2(S.paid_ytd+S.lump_sums_ytd-S.expected_ytd)}</b></td></tr>
<tr><td>Quality withhold retained by state</td><td class="n">${f2(S.withheld_ytd)}</td></tr>
<tr><td>Net remitted (820 BPR)</td><td class="n">${f2(S.net_remitted_ytd)}</td></tr>
<tr><td>Deposits matched to 820s (incl. in transit)</td><td class="n">${f2(S.deposited_ytd)}</td></tr>
<tr><td><b>820 vs bank</b></td><td class="n"><b>${f2(S.deposited_ytd-S.net_remitted_ytd)}</b></td></tr></table>
<h3>Largest open items</h3><table>${topC.map(c=>`<tr><td>${c.label}</td><td class="n">${f2(c.variance_usd)}</td></tr>`).join('')}</table></div></div>
<div class="card" style="margin-top:14px"><h2>Exception roll-forward</h2><table><tr><th>Close</th><th class="n">Opening</th><th class="n">New</th><th class="n">Resolved</th><th class="n">Closing #</th><th class="n">Closing $</th></tr>
${B.rollforward.map(r=>`<tr><td>${r.close}</td><td class="n">${n0(r.opening_items)}</td><td class="n">${n0(r.new_items)}</td><td class="n">${n0(r.resolved_items)}</td><td class="n">${n0(r.closing_items)}</td><td class="n">${f2(r.closing_usd)}</td></tr>`).join('')}</table>
<div class="small">July spike = state paid superseded Amendment 1 rates (auto-cleared by Sep catch-up). September spike = Region 3 retro amendment booked as receivable (cleared by Oct lump sum).</div></div>`;

// ---------------- exceptions
$('#exceptions').innerHTML=`<div class="small" style="margin-bottom:10px">Each card is one root cause. Explanations are written by the AI investigator from engine-computed facts; every number is checked against those facts before display.</div>`+
B.clusters.map((c,i)=>`<div class="cl" id="cl${i}"><div class="top"><div><span class="pill p-${c.status}">${c.status}</span> <b>${c.label}</b></div><div class="amt">${f2(c.variance_usd)}</div></div>
<div class="ex">${c.explanation}</div>
<div class="meta"><span>${n0(c.member_months)} member-months &middot; ${c.members} members &middot; ${c.months}</span><span>Owner: <b>${c.owner}</b></span><span>Treatment: ${c.accounting_treatment}</span><span class="ai">${c.explanation_method}</span></div>
<details style="margin-top:8px"><summary class="small">Evidence sample</summary><table>${c.sample.map(s=>`<tr><td>${s.member_id}</td><td>${s.month}</td><td>plan ${s.plan_cell||'-'}</td><td>state ${s.state_cell||'-'}</td><td class="n">exp ${f2(s.expected)}</td><td class="n">paid ${f2(s.paid)}</td></tr>`).join('')}</table></details>
<div class="act"><button class="btn pri" onclick="this.closest('.cl').classList.add('done');this.textContent='Accepted'">Accept treatment</button><button class="btn" onclick="this.textContent='Assigned to ${c.owner}'">Assign</button><button class="btn" onclick="this.textContent='Dispute drafted'">Draft state dispute</button></div></div>`).join('');

// ---------------- rates
const chk=r=>`<span class="pill ${r=='pass'?'p-ok':r=='WARN'?'p-warn':'p-open'}">${r}</span>`;
$('#rates').innerHTML=B.proposals.map(p=>`<div class="card" style="margin-bottom:12px"><div class="flex" style="justify-content:space-between"><h2>${p.version_id} &middot; ${p.source_doc}</h2><span class="pill ${p.state=='COMMITTED'?'p-ok':'p-warn'}">${p.state}</span></div>
<div class="grid k2"><div><table>
<tr><td>Format</td><td>${p.doc_type}</td></tr><tr><td>Extraction</td><td>${p.extraction_method}</td></tr>
<tr><td>Change</td><td>${p.change_type}${p.adjustment?` &middot; ${(p.adjustment.pct*100).toFixed(2)}% on ${p.adjustment.regions.join(',')} (${p.adjustment.categories.length?p.adjustment.categories.join(','):'all categories'}), basis: ${p.adjustment.basis}`:` &middot; ${Object.keys(p.rates).length} rate cells`}</td></tr>
<tr><td>Effective</td><td>${p.effective_from} &rarr; ${p.effective_to} ${p.retroactive?'<span class="pill p-open">RETRO</span>':''}</td></tr>
${p.payment_method?`<tr><td>Payment</td><td>${p.payment_method}</td></tr>`:''}
<tr><td>Approved</td><td>${p.approval?p.approval.approved_by+' &middot; '+p.approval.approved_at.slice(0,10):'-'}${p.approval&&p.approval.note?'<br><span class="small">'+p.approval.note+'</span>':''}</td></tr></table>
<h3>Citations</h3>${p.citations.map(c=>`<div class="small"><b>${c.field}:</b> &ldquo;${c.quote}&rdquo;</div>`).join('')}
${p.open_questions.length?'<h3>Questions for reviewer</h3>'+p.open_questions.map(q=>`<div class="small">&bull; ${q}</div>`).join(''):''}</div>
<div><h3>Validation</h3><table>${p.checks.map(c=>`<tr><td>${c.check}</td><td>${chk(c.result)}</td><td class="small">${c.detail}</td></tr>`).join('')}</table>
${Object.keys(p.impact).length?`<h3>Impact vs rates on file</h3><table>${Object.entries(p.impact).map(([m,a])=>`<tr><td>${m}</td><td class="n">${f2(a)}</td></tr>`).join('')}</table>`:''}</div></div></div>`).join('');

// ---------------- retro
const months=B.triangle.map(r=>r.coverage_month);
$('#retro').innerHTML=`<div class="card"><h2>Prior-period development triangle</h2><div class="small" style="margin-bottom:8px">Rows = coverage month. Columns = close in which revenue was recognised. Diagonal = originally booked; shaded off-diagonal = retro adjustments from new rate versions.</div>
<table class="tri"><tr><th>Coverage</th>${months.map(m=>`<th class="n">${m.slice(5)} close</th>`).join('')}<th class="n">Current view</th></tr>
${B.triangle.map(r=>`<tr><td style="text-align:left">${r.coverage_month}</td>${months.map(m=>{const v=r[m];if(v===null)return'<td></td>';const cls=m==r.coverage_month?'d':(Math.abs(v)>0.005?'h':'');return`<td class="${cls}">${Math.abs(v)<0.005?'-':fm(v)}</td>`}).join('')}<td><b>${fm(r.current_view)}</b></td></tr>`).join('')}</table>
<h3>Attribution</h3><table>${B.ppa.map(a=>`<tr><td>${a.close} close</td><td class="n">${f2(a.prior_period_adjustment)}</td><td>${a.versions}</td></tr>`).join('')}</table></div>
<div class="card" style="margin-top:14px"><h2>Aggregate retro settlements</h2><table><tr><th>820</th><th>Description</th><th>Version</th><th class="n">Paid</th><th class="n">Re-performed (state basis)</th><th class="n">Residual</th><th class="n">Allocated to</th></tr>
${B.lumps.map(l=>`<tr><td>${l.trace}</td><td>${l.desc}</td><td>${l.version}</td><td class="n">${f2(l.amount)}</td><td class="n">${f2(l.state_basis_estimate)}</td><td class="n">${f2(l.residual)}</td><td class="n">${n0(l.member_months)} member-months</td></tr>`).join('')}</table></div>`;

// ---------------- cash
$('#cash').innerHTML=`<div class="card"><h2>820 remittances vs bank deposits</h2><table><tr><th>Trace</th><th>820 date</th><th class="n">820 total</th><th>Deposit date</th><th class="n">Deposit</th><th class="n">Difference</th><th>Status</th></tr>
${B.cash.map(c=>`<tr><td>${c.trace}</td><td>${String(c.pay_date).slice(0,10)}</td><td class="n">${f2(c.remit_total)}</td><td>${c.deposit_date?String(c.deposit_date).slice(0,10):'-'}</td><td class="n">${f2(c.deposit)}</td><td class="n">${f2(c.difference)}</td><td><span class="pill ${c.status=='MATCHED'?'p-ok':'p-open'}">${c.status}</span></td></tr>`).join('')}</table>
<h3>Reconciling items</h3>${B.cash_items.map(c=>`<div class="cl"><div class="top"><b>${c.item}</b><span class="amt">${f2(c.amount)}</span></div><div class="ex">${c.explanation}</div></div>`).join('')}
<h3>Quality withhold check</h3><table><tr><th>Period</th><th class="n">Gross current</th><th class="n">Withheld</th><th class="n">Contract 1%</th><th>Status</th></tr>${B.withhold.map(w=>`<tr><td>${w.period}</td><td class="n">${f2(w.gross_current)}</td><td class="n">${f2(w.withheld)}</td><td class="n">${f2(w.contract_withhold)}</td><td><span class="pill p-ok">${w.status}</span></td></tr>`).join('')}</table></div>`;

// ---------------- memo
$('#memo').innerHTML=`<div class="card"><div class="flex" style="justify-content:space-between"><h2>Close memo</h2><span class="ai">${B.memo_method}</span></div><pre>${B.memo}</pre>
<h2 style="margin-top:16px">Draft journal entries</h2><table><tr><th>#</th><th>Description</th><th>Dr</th><th>Cr</th><th class="n">Amount</th></tr>${B.journal.map(j=>`<tr><td>${j.entry}</td><td>${j.description}</td><td>${j.debit}</td><td>${j.credit}</td><td class="n">${f2(j.amount)}</td></tr>`).join('')}</table></div>`;
</script></body></html>"""


def build_dashboard(path, bundle):
    path.write_text(TEMPLATE.replace("__DATA__", json.dumps(bundle, default=str)))
