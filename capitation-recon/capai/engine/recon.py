"""
Expected revenue and member-month reconciliation (expected vs. state remittance).

Matching happens at the grain where money is actually earned - member x coverage
month - regardless of which 820 cycle paid it, so retro adds, corrections and
recoupments in later remittances net against the month they belong to.

Each discrepancy is classified by deterministic, explainable rules into a root-cause
code. Rules encode the team's tacit knowledge; anything the rules cannot explain
falls through to UNEXPLAINED and is routed to the AI investigator.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from capai.engine.rate_store import RateStore

TOL = 0.005

# code -> (label, status, owner, action, accounting treatment)
CODES = {
    "MATCH": ("Matched", "matched", "-", "-", "None"),
    "RESOLVED_LATER_REMIT": ("Resolved by later remittance", "resolved", "-", "None - corrected by state in a later 820", "None"),
    "RESOLVED_RECOUPED": ("Paid then recouped (net zero)", "resolved", "-", "None - state recovered the overpayment", "Release any overpayment liability"),
    "SETTLED_LUMP_SUM": ("Settled by aggregate retro payment", "resolved", "-", "None - covered by header-level retro lump sum", "Relieve retro rate receivable"),
    "RATE_SUPERSEDED": ("State paid a superseded rate version", "open", "Revenue Accounting", "Confirm state implementation date; track catch-up payment", "Retro rate receivable (fully supported)"),
    "RATE_AMOUNT_UNEXPLAINED": ("Paid amount matches no known rate", "open", "Revenue Accounting", "Investigate (AI investigator)", "Hold - investigate"),
    "AGE_BAND_MISMATCH": ("Rate cell mismatch: age-band transition", "open", "State Liaison", "Submit rate-cell correction to state with DOB evidence", "Receivable supported by DOB; no reserve"),
    "REGION_MISMATCH": ("Rate cell mismatch: region", "open", "Enrollment Ops", "Validate address; send 834 address update / correction request", "Receivable pending address validation"),
    "CATEGORY_MISMATCH": ("Rate cell mismatch: category", "open", "Enrollment Ops", "Compare aid category on 834 vs plan system", "Hold - investigate"),
    "DUPLICATE_PAYMENT": ("Duplicate payment", "open", "Revenue Accounting", "Notify state; expect recoupment", "Overpayment liability for excess"),
    "TIMING_NEWBORN": ("Timing: newborn retro-enrollment", "pending", "Enrollment Ops", "None - state pays newborns next cycle; auto-recheck", "Receivable stands (expected next cycle)"),
    "STATE_TERMINATED": ("Unpaid: state stopped paying (likely missed term)", "open", "Enrollment Ops", "Check 834 term transactions; terminate in plan system if confirmed", "Reverse revenue (likely not earned)"),
    "NEVER_PAID": ("Unpaid: member never paid by state", "open", "State Liaison", "Confirm state enrollment; file dispute with 834 evidence", "Reserve 100% pending state confirmation"),
    "UNPAID_OTHER": ("Unpaid: other", "open", "Revenue Accounting", "Investigate (AI investigator)", "Hold - investigate"),
    "PAID_AFTER_TERM": ("Paid after plan termination", "open", "Revenue Accounting", "Expect state recoupment; confirm term date with state", "Overpayment liability"),
    "PAID_ENROLLMENT_GAP": ("Paid during a plan enrollment gap", "open", "Enrollment Ops", "Check for missed re-enrollment", "Unapplied - pending validation"),
    "UNKNOWN_MEMBER": ("Paid for member not on plan roster", "open", "Enrollment Ops", "Load missing 834 enrollment; validate eligibility", "Unapplied cash - pending enrollment load"),
    "UNEXPLAINED": ("Unexplained", "open", "Revenue Accounting", "Investigate (AI investigator)", "Hold - investigate"),
}


def expected_revenue(roster: pd.DataFrame, store: RateStore, as_of: datetime, through: str) -> pd.DataFrame:
    df = roster[roster.cov_month <= through].copy()
    keys = df[["cell", "cov_month"]].drop_duplicates()
    lut = {(c, m): store.lookup(c, m, as_of) for c, m in keys.itertuples(index=False)}
    df["expected"] = [lut[(c, m)][0] for c, m in zip(df.cell, df.cov_month)]
    df["exp_version"] = [lut[(c, m)][1] for c, m in zip(df.cell, df.cov_month)]
    return df


def _paid_by_member_month(lines: pd.DataFrame) -> pd.DataFrame:
    net = lines.groupby(["member_id", "cov_month", "cell"], as_index=False)["amount"].sum()
    net = net.sort_values("amount", ascending=False).drop_duplicates(["member_id", "cov_month"])
    g = lines.groupby(["member_id", "cov_month"])
    out = pd.DataFrame({
        "paid": g["amount"].sum().round(2),
        "n_current": g["line_type"].apply(lambda s: int((s == "current").sum())),
        "n_lines": g.size(),
        "had_adjustment": g["adx"].apply(lambda s: s.notna().any()),
        "traces": g["trace"].apply(lambda s: ",".join(sorted(set(s)))),
    }).reset_index()
    out = out.merge(net[["member_id", "cov_month", "cell"]].rename(columns={"cell": "paid_cell"}), on=["member_id", "cov_month"])
    return out


@dataclass
class ReconResult:
    detail: pd.DataFrame
    lump_sums: list[dict]


def reconcile(expected: pd.DataFrame, lines: pd.DataFrame, remits, store: RateStore, master: pd.DataFrame,
              roster: pd.DataFrame, cutoff: datetime, through: str) -> ReconResult:
    ln = lines[(lines.pay_date <= pd.Timestamp(cutoff)) & (lines.cov_month <= through)]
    paid = _paid_by_member_month(ln)
    d = expected.merge(paid, on=["member_id", "cov_month"], how="outer", indicator="src")
    d["expected"] = d["expected"].fillna(0.0)
    d["paid"] = d["paid"].fillna(0.0)
    d["n_current"] = d["n_current"].fillna(0).astype(int)
    d["had_adjustment"] = d["had_adjustment"].fillna(False).astype(bool)
    d["variance"] = (d["paid"] - d["expected"]).round(2)
    d["aggregate_alloc"] = 0.0

    plan_span = roster.groupby("member_id")["cov_month"].agg(["min", "max", "nunique"])
    paid_months = ln.groupby("member_id")["cov_month"].agg(lambda s: sorted(set(s)))
    mstr = master.set_index("member_id")
    latest = through

    def classify(r):
        if r.src == "both":
            if abs(r.variance) < TOL and r.paid_cell == r.cell:
                return ("RESOLVED_LATER_REMIT" if r.had_adjustment else "MATCH"), {}
            if r.n_current >= 2 and r.paid_cell == r.cell:
                unit = round(r.paid / r.n_current, 2)
                vid, _ = store.matching_version(r.cell, r.cov_month, unit)
                if abs(unit - r.expected) < TOL or vid:
                    return "DUPLICATE_PAYMENT", {"times_paid": r.n_current, "unit_paid": unit}
            if r.paid_cell == r.cell:
                unit = r.paid / max(1, r.n_current) if r.n_current > 1 else r.paid
                vid, rate = store.matching_version(r.cell, r.cov_month, unit)
                if vid and vid != r.exp_version:
                    return "RATE_SUPERSEDED", {"state_version": vid, "state_rate": rate}
                return "RATE_AMOUNT_UNEXPLAINED", {}
            preg, pcat = r.paid_cell.split("-")
            ereg, ecat = r.cell.split("-")
            if preg != ereg:
                return "REGION_MISMATCH", {"state_region": preg, "plan_region": ereg}
            if ecat in ("ADF", "ADM") and pcat == "CH20" and r.member_id in mstr.index:
                dob = pd.Timestamp(mstr.at[r.member_id, "dob"])
                age = (pd.Timestamp(r.cov_month + "-01") - dob).days / 365.25
                if age >= 21:
                    return "AGE_BAND_MISMATCH", {"age_at_month_start": round(age, 1), "dob": dob.date().isoformat()}
            return "CATEGORY_MISMATCH", {"state_category": pcat, "plan_category": ecat}
        if r.src == "left_only":  # expected, not paid
            m = mstr.loc[r.member_id] if r.member_id in mstr.index else None
            pm = paid_months.get(r.member_id, [])
            if m is not None and m.program == "TANF":
                dob = pd.Timestamp(m.dob)
                if dob.strftime("%Y-%m") == r.cov_month and r.cov_month == latest:
                    return "TIMING_NEWBORN", {"dob": dob.date().isoformat()}
            if pm and max(pm) < r.cov_month:
                return "STATE_TERMINATED", {"last_paid_month": max(pm)}
            if not pm:
                return "NEVER_PAID", {"plan_enrolled_from": plan_span.at[r.member_id, "min"]}
            return "UNPAID_OTHER", {}
        # paid, not expected
        if abs(r.paid) < TOL:
            return "RESOLVED_RECOUPED", {}
        if r.member_id in plan_span.index:
            if r.cov_month > plan_span.at[r.member_id, "max"]:
                return "PAID_AFTER_TERM", {"plan_last_month": plan_span.at[r.member_id, "max"]}
            return "PAID_ENROLLMENT_GAP", {}
        if r.member_id not in mstr.index:
            return "UNKNOWN_MEMBER", {}
        return "UNEXPLAINED", {}

    res = [classify(r) for r in d.itertuples(index=False)]
    d["code"] = [c for c, _ in res]
    d["evidence"] = [e for _, e in res]

    lumps = _apply_lump_sums(d, remits, store, cutoff, through)
    d["variance_after"] = (d["variance"] + d["aggregate_alloc"]).round(2)
    settled = (d.code == "RATE_SUPERSEDED") & (d.variance_after.abs() < TOL)
    d.loc[settled, "code"] = "SETTLED_LUMP_SUM"
    d["status"] = d.code.map(lambda c: CODES[c][1])
    d["label"] = d.code.map(lambda c: CODES[c][0])
    return ReconResult(detail=d.drop(columns=["src"]), lump_sums=lumps)


def _apply_lump_sums(d: pd.DataFrame, remits, store: RateStore, cutoff: datetime, through: str) -> list[dict]:
    """Match header-level retro settlements (ADX 'RT') to the rate version they pay,
    re-perform the state's calculation on the state's own eligibility basis, and
    allocate the lump sum back to member-months."""
    out = []
    retro_versions = [v for v in store.versions if v.retroactive]
    for rm in remits:
        if pd.Timestamp(rm.pay_date) > pd.Timestamp(cutoff):
            continue
        for h in rm.header_adjustments:
            if h["code"] != "RT":
                continue
            best = None
            for v in retro_versions:
                if v.recorded_at.date() > rm.pay_date:
                    continue
                before = v.recorded_at - timedelta(seconds=1)
                alloc = {}
                for idx, r in d[(d.paid > TOL) & d.paid_cell.notna() & (d.cov_month <= through)].iterrows():
                    key = (r.paid_cell, r.cov_month)
                    if key not in v.materialized:
                        continue
                    prior = store.rate(r.paid_cell, r.cov_month, before)
                    unit = r.paid / r.n_current if r.n_current > 1 else r.paid
                    if prior is not None and abs(unit - prior) < TOL:
                        alloc[idx] = round(v.materialized[key] - prior, 2)
                est = round(sum(alloc.values()), 2)
                if best is None or abs(est - h["amount"]) < abs(best[1] - h["amount"]):
                    best = (v, est, alloc)
            if best is None:
                out.append(dict(trace=rm.trace, amount=h["amount"], desc=h["desc"], version=None, state_basis_estimate=None))
                continue
            v, est, alloc = best
            for idx, a in alloc.items():
                d.at[idx, "aggregate_alloc"] = a
            months = sorted({d.at[i, "cov_month"] for i in alloc})
            out.append(dict(trace=rm.trace, pay_date=rm.pay_date, amount=h["amount"], desc=h["desc"], version=v.version_id,
                            state_basis_estimate=est, residual=round(h["amount"] - est, 2),
                            member_months=len(alloc), months=f"{months[0]}..{months[-1]}" if months else ""))
    return out
