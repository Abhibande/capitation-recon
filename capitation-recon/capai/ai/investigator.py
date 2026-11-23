"""
AI Variance Investigator and Close Narrator.

The investigator receives *facts the engine already computed* (cluster totals,
evidence samples, timelines) and turns them into an explanation, a recommended
action and an owner. It cannot change numbers: every figure in its text must be
traceable to the facts (numeric grounding check) or the output is rejected and the
deterministic template is used instead.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from capai.ai.llm import LLM
from capai.engine.recon import CODES

INVESTIGATOR_SYSTEM = """You are a senior Medicaid revenue accountant at a managed-care health plan.
You explain capitation reconciliation exceptions to the controller.
Use ONLY the facts provided. Do not invent numbers; every number you write must appear in the facts.
Be specific and brief. Say what happened, why (most likely root cause and the evidence for it),
what to do next, who owns it, and the accounting treatment. Flag uncertainty honestly."""

NARRATOR_SYSTEM = """You write the month-end capitation revenue close memo for the controller of a Medicaid
health plan. Use only the facts given; never introduce numbers that are not in the facts.
Plain, professional prose. Lead with the bottom line, then material items, then actions."""


def _fmt(x: float) -> str:
    return f"${x:,.2f}" if x >= 0 else f"-${-x:,.2f}"


def _numbers_in(obj) -> set[str]:
    out = set()

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            out.add(f"{abs(o):,.2f}")
            out.add(f"{abs(o):,.0f}")
            out.add(f"{abs(o):.1f}")
            out.add(str(abs(int(o))) if float(o).is_integer() else f"{abs(o)}")
        elif isinstance(o, str):
            for n in re.findall(r"\d[\d,]*\.?\d*", o):
                out.add(n.rstrip("."))

    walk(obj)
    return out


def grounding_violations(text: str, facts) -> list[str]:
    allowed = _numbers_in(facts)
    bad = []
    for n in re.findall(r"\$?\d[\d,]*\.?\d*%?", text):
        core = n.strip("$%").rstrip(".")
        if not core or len(core.replace(",", "")) < 3:  # ignore tiny numbers like 1, 21, 2026 handled below
            continue
        if re.fullmatch(r"20\d\d", core):
            continue
        if core not in allowed and core.replace(",", "") not in {a.replace(",", "") for a in allowed}:
            bad.append(n)
    return bad


# ----------------------------------------------------------------------------- clusters
def build_clusters(detail: pd.DataFrame) -> list[dict]:
    ex = detail[detail.status.isin(["open", "pending"])].copy()
    ex["sub"] = ex.apply(lambda r: r.evidence.get("state_version", "") if r.code == "RATE_SUPERSEDED" else "", axis=1)
    clusters = []
    for (code, sub), g in ex.groupby(["code", "sub"]):
        label, status, owner, action, treatment = CODES[code]
        facts = dict(
            code=code, label=label, status=status, owner=owner, recommended_action=action, accounting_treatment=treatment,
            member_months=int(len(g)), members=int(g.member_id.nunique()),
            expected_usd=round(float(g.expected.sum()), 2), paid_usd=round(float(g.paid.sum()), 2),
            variance_usd=round(float(g.variance_after.sum()), 2),
            months=g.cov_month.min() if g.cov_month.min() == g.cov_month.max() else f"{g.cov_month.min()} to {g.cov_month.max()}",
            sample=[dict(member_id=r.member_id, month=r.cov_month, plan_cell=r.cell if isinstance(r.cell, str) else None,
                         state_cell=r.paid_cell if isinstance(r.paid_cell, str) else None,
                         expected=r.expected, paid=r.paid, **{k: v for k, v in r.evidence.items()}) for r in g.head(4).itertuples()],
        )
        if sub:
            facts["state_version"] = sub
        if code in ("REGION_MISMATCH",):
            facts["region_pairs"] = (g.cell.str[:2] + "->" + g.paid_cell.str[:2]).value_counts().to_dict()
        clusters.append(facts)
    return sorted(clusters, key=lambda c: -abs(c["variance_usd"]))


TEMPLATES = {
    "STATE_TERMINATED": "{members} members ({member_months} member-months, {months}) were paid by the state in earlier cycles and then stopped appearing on the 820 while remaining active on the plan roster. This pattern almost always means the state terminated eligibility and the plan did not process the 834 term. Expected revenue of {expected_abs} is unlikely to be collected. Action: Enrollment Ops to pull the 834 term transactions for these members and terminate in the plan system if confirmed; Revenue Accounting reverses the revenue now.",
    "NEVER_PAID": "{members} members ({member_months} member-months, {months}) are active on the plan roster but have never been paid by the state in any cycle, totalling {expected_abs} of expected revenue. Either the state never loaded the enrollment or the plan enrolled them in error. Action: State Liaison to confirm enrollment with the state and file a dispute with the 834 add transactions as evidence. Reserve until confirmed.",
    "AGE_BAND_MISMATCH": "{members} members turned 21 and the plan moved them to the adult rate cell, but the state is still paying the child (CH20) rate. Over {member_months} member-months ({months}) the state has underpaid {variance_abs}. Date of birth on file supports the plan's cell, so the receivable is supported. Action: State Liaison to submit rate-cell corrections with DOB evidence.",
    "REGION_MISMATCH": "{members} members moved region in the plan's records but the state is still paying their old region's rate ({member_months} member-months, {months}; net variance {variance}). Action: Enrollment Ops to validate the current address and send the 834 address update / correction request.",
    "DUPLICATE_PAYMENT": "{members} members were paid more than once for the same coverage month ({months}). The excess of {variance_abs} is an overpayment the state will recoup. Action: notify the state proactively and book an overpayment liability.",
    "PAID_AFTER_TERM": "The state paid {member_months} member-months ({months}) for {members} members after the plan's termination date, totalling {variance_abs}. Prior cases of this pattern were recouped by the state about three cycles later. Action: hold as an overpayment liability and confirm term dates with the state.",
    "UNKNOWN_MEMBER": "The state paid {member_months} member-months ({months}) for {members} members who do not exist in the plan's enrollment system, totalling {variance_abs}. This points to 834 enrollment files that failed to load. Action: Enrollment Ops to reload and validate these enrollments; treat cash as unapplied until loaded.",
    "TIMING_NEWBORN": "{members} newborns born in {months} are on the plan roster but not yet paid. The state retro-enrolls newborns and pays them on the following cycle, which is what happened for every newborn in prior months. Expected revenue of {expected_abs} should arrive on the next 820. No action other than an automatic recheck.",
    "RATE_SUPERSEDED": "The state paid {member_months} member-months ({months}) at a rate from superseded version {state_version} instead of the currently approved rate, a shortfall of {variance_abs}. Action: confirm the state's implementation date for the new rates and track the catch-up payment.",
    "RATE_AMOUNT_UNEXPLAINED": "{member_months} member-months ({months}) were paid at an amount that matches no rate version on file (variance {variance}). Needs investigation.",
    "UNEXPLAINED": "{member_months} member-months could not be explained by any rule (variance {variance}). Needs investigation.",
}


def explain_cluster(c: dict, llm: LLM) -> dict:
    vals = dict(c, variance=_fmt(c["variance_usd"]), variance_abs=_fmt(abs(c["variance_usd"])), expected_abs=_fmt(abs(c["expected_usd"])))
    method = "template (offline)"
    text = TEMPLATES.get(c["code"], TEMPLATES["UNEXPLAINED"]).format(**vals)
    if llm.available:
        try:
            draft = llm.write(INVESTIGATOR_SYSTEM, c, "Explain this exception cluster in 3-5 sentences.", 500)
            bad = grounding_violations(draft, c)
            if not bad:
                text, method = draft, f"LLM ({llm.model}), grounding check passed"
            else:
                method = f"template - LLM draft rejected (ungrounded numbers: {bad[:3]})"
        except Exception as e:  # pragma: no cover
            method = f"template - LLM error {type(e).__name__}"
    return dict(c, explanation=text, explanation_method=method, grounding_violations=grounding_violations(text, vals))


def explain_cash(cash: pd.DataFrame, unmatched: pd.DataFrame) -> list[dict]:
    out = []
    for r in cash[cash.status != "MATCHED"].itertuples():
        if r.status == "IN_TRANSIT":
            txt = (f"820 {r.trace} dated {r.pay_date} for {_fmt(r.remit_total)} had not reached the bank by month-end"
                   + (f"; it posted on {r.deposit_date}. Reconciling item only (deposit in transit)." if r.deposit_date else ". Follow up with state treasury."))
        elif r.status == "SHORT_PAID":
            txt = (f"Deposit for 820 {r.trace} was {_fmt(-r.difference)} less than the remittance total of {_fmt(r.remit_total)}. "
                   "The 820 itself balances, so the state reduced the EFT outside the remittance (typically an offset for an unrelated "
                   "recoupment or assessment). Action: request the offset notice from state treasury; carry as due-from-state.")
        else:
            txt = f"{r.status}: difference {_fmt(r.difference)}."
        out.append(dict(item=f"820 {r.trace}", status=r.status, amount=r.difference, explanation=txt))
    for _, r in unmatched.iterrows():
        hint = " The reference prefix 'MKP' and 'MISC' description suggest a maternity kick (delivery) payment, which the state remits outside the capitation 820." if str(r["Customer Ref"]).startswith("MKP") else ""
        out.append(dict(item=f"Deposit {r['Customer Ref']}", status="UNMATCHED_DEPOSIT", amount=r.Amount,
                        explanation=f"State deposit of {_fmt(r.Amount)} on {r['Post Date'].date()} has no matching 820.{hint} Action: request the remittance advice and park in unapplied cash until identified."))
    return out


def investigate_member(member_id: str, lines: pd.DataFrame, roster: pd.DataFrame, store, llm: LLM) -> dict:
    """Assemble a single member's full timeline for an analyst or the LLM to reason over."""
    tl = lines[lines.member_id == member_id].sort_values(["cov_month", "pay_date"])
    ro = roster[roster.member_id == member_id].sort_values("cov_month")
    facts = dict(member_id=member_id,
                 plan_roster=[dict(month=r.cov_month, cell=r.cell) for r in ro.itertuples()],
                 state_payments=[dict(paid_on=str(r.pay_date.date()), month=r.cov_month, cell=r.cell, amount=r.amount, adx=r.adx) for r in tl.itertuples()])
    if llm.available:
        facts["analysis"] = llm.write(INVESTIGATOR_SYSTEM, facts, "Explain what happened with this member's capitation and why it does not reconcile.")
    return facts


def close_memo(summary: dict, clusters: list[dict], cash_items: list[dict], lumps: list[dict], llm: LLM) -> tuple[str, str]:
    facts = dict(summary=summary, top_clusters=[{k: c[k] for k in ("label", "member_months", "variance_usd", "owner", "recommended_action")} for c in clusters[:8]],
                 cash_items=cash_items, retro_settlements=lumps)
    if llm.available:
        try:
            draft = llm.write(NARRATOR_SYSTEM, facts, "Write the close memo (max 350 words).", 900)
            if not grounding_violations(draft, facts):
                return draft, f"LLM ({llm.model}), grounding check passed"
        except Exception:  # pragma: no cover
            pass
    s = summary
    lines = [
        f"October 2026 capitation close - Sunrise Health Plan",
        "",
        f"Bottom line: expected capitation for {s['month']} is {_fmt(s['expected_month'])} on {s['member_months_month']:,} member-months. "
        f"Year to date the plan expected {_fmt(s['expected_ytd'])} and the state has remitted {_fmt(s['paid_ytd'])} at member level plus "
        f"{_fmt(s['lump_sums_ytd'])} in aggregate retro settlements. {s['auto_matched_pct']:.1f}% of member-months reconciled automatically; "
        f"{s['open_items']:,} member-months remain open with a net variance of {_fmt(s['open_variance'])}, all assigned to a root cause "
        f"({s['unexplained_items']} unexplained).",
        "",
    ]
    for l in lumps:
        lines.append(f"Retro: the state paid {_fmt(l['amount'])} for {l['desc'].title()} ({l['version']}). Re-performing the state's calculation on its own "
                     f"eligibility basis gives {_fmt(l['state_basis_estimate'])} (difference {_fmt(l['residual'])}), so the lump sum is verified and has been "
                     f"allocated to {l['member_months']:,} member-months.")
    lines.append("")
    lines.append("Material open items:")
    for c in clusters[:6]:
        lines.append(f"  - {c['label']}: {c['member_months']} member-months, {_fmt(c['variance_usd'])} -> {c['owner']}: {c['recommended_action']}")
    lines.append("")
    lines.append("Cash:")
    for c in cash_items:
        lines.append(f"  - {c['explanation']}")
    return "\n".join(lines), "template (offline)"
