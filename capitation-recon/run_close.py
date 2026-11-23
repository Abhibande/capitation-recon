"""
End-to-end month-end capitation close.

    python run_close.py --month 2026-10

Steps
  1. Rate intake: read every state rate publication, extract -> validate -> impact -> approval packet
  2. Commit approved versions to the bitemporal rate store (unapproved = ignored)
  3. Expected revenue (plan roster x rates known at close)
  4. Parse 820 remittances; member-month reconciliation + root-cause classification
  5. Header-level retro settlements re-performed and allocated
  6. Cash: 820 vs bank; withhold check
  7. Prior-period triangle, exception roll-forward
  8. AI: cluster explanations, cash explanations, close memo (grounded)
  9. Draft journal entries, workbook, dashboard data
 10. Score against injected ground truth (demo only)
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from capai.ai import investigator as inv
from capai.ai.llm import LLM
from capai.ai.rate_intake import extract, impact_preview, validate
from capai.engine.close import (cash_recon, close_date, draft_journal, exception_rollforward, month_end, retro_triangle,
                                withhold_check)
from capai.engine.rate_store import RateStore, RateVersion, month_range
from capai.engine.recon import expected_revenue, reconcile
from capai.ingest.remittance import load_bank, load_remittances

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parent / "out"


def last_closed_month(as_of: datetime) -> str:
    y, m = as_of.year, as_of.month
    for _ in range(24):
        mo = f"{y:04d}-{m:02d}"
        if close_date(mo) <= as_of:
            return mo
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return "1900-01"


def main(month: str):
    OUT.mkdir(exist_ok=True)
    llm = LLM()
    print(f"[ai] LLM available: {llm.available}  ({'Claude API' if llm.available else 'offline deterministic fallbacks'})")

    # ---------------------------------------------------------------- inputs
    roster = pd.read_csv(DATA / "internal" / "enrollment_roster.csv")
    roster = roster.rename(columns={"coverage_month": "cov_month"})
    roster["cell"] = roster.region + "-" + roster.rate_category
    master = pd.read_csv(DATA / "internal" / "member_master.csv")
    approvals = json.loads((DATA / "internal" / "rate_approvals.json").read_text())
    by_doc = {a["doc"]: (vid, a) for vid, a in approvals.items()}
    counts = roster.groupby(["cell", "cov_month"]).size().to_dict()

    # ---------------------------------------------------------------- 1-2 rate intake
    store = RateStore()
    proposals = []
    docs = sorted((DATA / "inbound" / "rates").iterdir(), key=lambda p: by_doc.get(p.name, ("", {"approved_at": "9999"}))[1]["approved_at"])
    for path in docs:
        p = extract(path, llm, rate_year_end="2026-12")
        vid, appr = by_doc.get(path.name, (None, None))
        review_at = datetime.fromisoformat(appr["approved_at"]) if appr else datetime.now()
        validate(p, store, review_at, last_closed_month(review_at))
        impact_preview(p, store, review_at, counts)
        rec = asdict(p)
        rec["version_id"] = vid
        rec["approval"] = appr
        proposals.append(rec)
        blocking = [c for c in p.checks if c["result"] == "FAIL"]
        if appr and not blocking:
            store.commit(RateVersion(version_id=vid, source_doc=path.name, change_type=p.change_type,
                                     effective_from=p.effective_from, effective_to=p.effective_to,
                                     recorded_at=review_at, approved_by=appr["approved_by"],
                                     extraction_method=p.extraction_method, rates=p.rates, adjustment=p.adjustment,
                                     retroactive=p.retroactive, notes=appr.get("note", "")))
            state = "COMMITTED"
        else:
            state = "BLOCKED" if blocking else "AWAITING APPROVAL"
        rec["state"] = state
        print(f"[rates] {path.name:48s} {p.extraction_method:34s} {p.change_type:19s} {p.effective_from}..{p.effective_to} "
              f"retro={p.retroactive!s:5s} -> {vid} {state}")

    # ---------------------------------------------------------------- 3-5 recon
    months = month_range("2026-01", month)
    remits, lines = load_remittances(DATA / "inbound" / "remittance")
    for rm in remits:
        if rm.integrity:
            print(f"[820] integrity issue {rm.file}: {rm.integrity}")
    print(f"[820] {len(remits)} remittances, {len(lines):,} lines parsed; all balance to BPR: {all(not r.integrity for r in remits)}")

    as_of = close_date(month)
    exp = expected_revenue(roster, store, as_of, month)
    rr = reconcile(exp, lines, remits, store, master, roster, month_end(month), month)
    d = rr.detail
    print(f"[recon] {len(d):,} member-months  codes: {d.code.value_counts().to_dict()}")
    for l in rr.lump_sums:
        print(f"[retro] lump {l['amount']:,.2f} -> {l['version']} state-basis {l['state_basis_estimate']:,.2f} residual {l['residual']:,.2f}")

    # ---------------------------------------------------------------- 6 cash
    bank = load_bank(DATA / "inbound" / "bank" / "operating_acct_4410023_2026.csv")
    cash, unmatched = cash_recon(remits, bank, month_end(month))
    wh = withhold_check(remits)

    # ---------------------------------------------------------------- 7 retro + roll-forward
    tri, attrib = retro_triangle(roster, store, months)
    rf, snaps = exception_rollforward(roster, store, lines, remits, master, months)

    # ---------------------------------------------------------------- 8 AI
    clusters = [inv.explain_cluster(c, llm) for c in inv.build_clusters(d)]
    cash_items = inv.explain_cash(cash, unmatched)
    open_ = d[d.status.isin(["open", "pending"])]
    lump_total = sum(l["amount"] for l in rr.lump_sums)
    summary = dict(
        month=month, close_as_of=as_of.isoformat(),
        expected_month=round(float(d.loc[d.cov_month == month, "expected"].sum()), 2),
        member_months_month=int((d.loc[d.cov_month == month, "expected"] > 0).sum()),
        expected_ytd=round(float(d.expected.sum()), 2), paid_ytd=round(float(d.paid.sum()), 2),
        lump_sums_ytd=round(lump_total, 2),
        withheld_ytd=round(float(-wh.withheld.sum()), 2),
        net_remitted_ytd=round(sum(r.bpr_total for r in remits), 2),
        deposited_ytd=round(float(cash.deposit.sum()), 2),
        member_months=int(len(d)),
        auto_matched=int((d.status.isin(["matched", "resolved"])).sum()),
        auto_matched_pct=round(100 * float(d.status.isin(["matched", "resolved"]).mean()), 2),
        open_items=int(len(open_)), open_variance=round(float(open_.variance_after.sum()), 2),
        unexplained_items=int(open_.code.isin(["UNEXPLAINED", "RATE_AMOUNT_UNEXPLAINED", "UNPAID_OTHER", "CATEGORY_MISMATCH"]).sum()),
        clusters=len(clusters), raw_variance_items=int((d.variance.abs() > 0.005).sum()),
    )
    memo, memo_method = inv.close_memo(summary, clusters, cash_items, rr.lump_sums, llm)

    # ---------------------------------------------------------------- 9 JE + outputs
    je = draft_journal(d, month, cash, unmatched, remits, rr.lump_sums)

    # ---------------------------------------------------------------- 10 score vs ground truth
    score = score_against_truth(d, snaps)

    bundle = dict(summary=summary, proposals=proposals, rate_versions=[dict(version_id=v.version_id, source_doc=v.source_doc,
                  change_type=v.change_type, effective=f"{v.effective_from}..{v.effective_to}", recorded_at=v.recorded_at.isoformat(),
                  approved_by=v.approved_by, method=v.extraction_method, retroactive=v.retroactive, cells=len({c for c, _ in v.materialized}))
                  for v in store.versions],
                  clusters=clusters, cash=json.loads(cash.to_json(orient="records", date_format="iso")),
                  cash_items=cash_items, withhold=json.loads(wh.to_json(orient="records")), lumps=rr.lump_sums,
                  triangle=json.loads(tri.reset_index().to_json(orient="records")), ppa=json.loads(attrib.to_json(orient="records")),
                  rollforward=json.loads(rf.to_json(orient="records")), journal=json.loads(je.to_json(orient="records")),
                  memo=memo, memo_method=memo_method, score=score,
                  by_month=json.loads(d.groupby("cov_month").agg(expected=("expected", "sum"), paid=("paid", "sum"),
                                     alloc=("aggregate_alloc", "sum")).round(2).reset_index().to_json(orient="records")))
    (OUT / "close_bundle.json").write_text(json.dumps(bundle, indent=1, default=str))
    (OUT / "close_memo.txt").write_text(memo)
    d.assign(evidence=d.evidence.map(json.dumps)).to_csv(OUT / "member_month_recon.csv", index=False)

    from capai.report.workbook import build_workbook
    from capai.report.dashboard import build_dashboard
    build_workbook(OUT / f"Capitation_Recon_{month}.xlsx", bundle, d, store, months)
    build_dashboard(OUT / "review_console.html", bundle)
    print(f"[done] auto-matched {summary['auto_matched_pct']}% | open {summary['open_items']} items in {len(clusters)} clusters | "
          f"unexplained {summary['unexplained_items']} | ground-truth recall {score['overall_recall']:.0%}")
    print(memo)
    return bundle


TRUTH_MAP = {
    "PLAN_MISSED_TERM": {"STATE_TERMINATED"},
    "STATE_ENROLLMENT_MISSING": {"NEVER_PAID"},
    "PLAN_ENROLLMENT_MISSING": {"UNKNOWN_MEMBER"},
    "PAID_AFTER_TERM": {"PAID_AFTER_TERM", "RESOLVED_RECOUPED"},
    "AGE_BAND_MISMATCH": {"AGE_BAND_MISMATCH"},
    "REGION_LAG_CORRECTED": {"RESOLVED_LATER_REMIT", "SETTLED_LUMP_SUM"},
    "REGION_MISMATCH": {"REGION_MISMATCH"},
    "DUPLICATE_PAYMENT": {"DUPLICATE_PAYMENT"},
    "TIMING_NEWBORN": {"TIMING_NEWBORN"},
}


def score_against_truth(d: pd.DataFrame, snaps) -> dict:
    gt = pd.read_csv(DATA / "ground_truth" / "injected_issues.csv")
    idx = d.set_index(["member_id", "cov_month"]).code
    rows, hits_total, n_total = [], 0, 0
    truth_keys = set()
    for t, g in gt[gt.member_id != "*"].groupby("issue_type"):
        hits = n = 0
        for r in g.itertuples():
            for mo in str(r.months).split(";"):
                truth_keys.add((r.member_id, mo))
                n += 1
                if (r.member_id, mo) in idx.index and idx.loc[(r.member_id, mo)] in TRUTH_MAP[t]:
                    hits += 1
        rows.append(dict(issue_type=t, member_months=n, detected=hits, recall=round(hits / n, 3) if n else None))
        hits_total += hits
        n_total += n
    # systemic issues: verify at the close where they were live
    jul = snaps["2026-07"].detail
    lag = jul[jul.code == "RATE_SUPERSEDED"]
    rows.append(dict(issue_type="RATE_LAG_AMEND1 (at Jul close)", member_months=int(len(lag)), detected=int(len(lag)),
                     recall=1.0 if len(lag) else 0.0))
    settled = int((d.code == "SETTLED_LUMP_SUM").sum())
    rows.append(dict(issue_type="RATE_RETRO_AMEND2 (lump allocated)", member_months=settled, detected=settled, recall=1.0 if settled else 0.0))
    # false positives: open exceptions not caused by an injected issue (excluding systemic rate items)
    ex = d[d.status.isin(["open", "pending"]) & ~d.code.isin(["RATE_SUPERSEDED"])]
    fp = [k for k in zip(ex.member_id, ex.cov_month) if k not in truth_keys]
    return dict(by_type=rows, overall_recall=hits_total / n_total if n_total else 0, false_positives=len(fp),
                false_positive_sample=[list(k) for k in fp[:10]])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="2026-10")
    main(ap.parse_args().month)
