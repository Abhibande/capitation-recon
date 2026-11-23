"""Cash reconciliation, withhold check, prior-period (retro) triangle, exception roll-forward
and draft journal entries for the month-end close."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from capai.engine.recon import CODES, TOL, expected_revenue, reconcile
from capai.engine.rate_store import RateStore, month_range
from capai.reference import QUALITY_WITHHOLD_PCT


def close_date(month: str) -> datetime:
    """Books for a month close on the 6th of the following month."""
    y, m = map(int, month.split("-"))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return datetime(y, m, 6, 18, 0)


def month_end(month: str) -> datetime:
    y, m = map(int, month.split("-"))
    nxt = datetime(y + (m == 12), 1 if m == 12 else m + 1, 1)
    return nxt - timedelta(seconds=1)


# --------------------------------------------------------------------------- cash
def cash_recon(remits, bank: pd.DataFrame, cutoff: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    credits = bank[(bank.Amount > 0) & bank.Description.str.contains("MEDICAID", case=False)].copy()
    credits["matched"] = False
    rows = []
    for rm in remits:
        hit = credits[credits["Customer Ref"] == rm.trace]
        how = "trace number"
        if hit.empty:  # fall back to amount/date proximity
            win = credits[(~credits.matched) & ((credits["Post Date"] - pd.Timestamp(rm.pay_date)).dt.days.between(0, 5))]
            hit = win[(win.Amount - rm.bpr_total).abs() < 0.01]
            how = "amount + date window"
        if hit.empty:
            status = "IN_TRANSIT" if pd.Timestamp(rm.pay_date) <= pd.Timestamp(cutoff) else "NOT_DUE"
            rows.append(dict(trace=rm.trace, pay_date=rm.pay_date, remit_total=rm.bpr_total, deposit_date=None, deposit=0.0,
                             difference=-rm.bpr_total, match_method="-", status=status))
            continue
        b = hit.iloc[0]
        credits.loc[b.name, "matched"] = True
        diff = round(b.Amount - rm.bpr_total, 2)
        if b["Post Date"] > pd.Timestamp(cutoff):
            status = "IN_TRANSIT"
        elif abs(diff) < 0.01:
            status = "MATCHED"
        else:
            status = "SHORT_PAID" if diff < 0 else "OVER_PAID"
        rows.append(dict(trace=rm.trace, pay_date=rm.pay_date, remit_total=rm.bpr_total, deposit_date=b["Post Date"].date(),
                         deposit=b.Amount, difference=diff, match_method=how, status=status))
    unmatched = credits[(~credits.matched) & (credits["Post Date"] <= pd.Timestamp(cutoff))]
    return pd.DataFrame(rows), unmatched.drop(columns=["matched"])


def withhold_check(remits) -> pd.DataFrame:
    rows = []
    for rm in remits:
        gross = sum(l["amount"] for l in rm.lines if l["adx"] is None and l["cov_month"] == rm.period)
        qw = sum(h["amount"] for h in rm.header_adjustments if h["code"] == "QW")
        exp = -round(gross * QUALITY_WITHHOLD_PCT + 1e-9, 2)
        rows.append(dict(period=rm.period, trace=rm.trace, gross_current=round(gross, 2), withheld=qw, contract_withhold=exp,
                         difference=round(qw - exp, 2), status="OK" if abs(qw - exp) < 0.01 else "CHECK"))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- retro triangle
def retro_triangle(roster: pd.DataFrame, store: RateStore, months: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Expected revenue for each coverage month as known at each successive close.
    Diagonal = originally booked; off-diagonal = prior-period adjustments recognised later."""
    known = {}
    for c in months:
        e = expected_revenue(roster, store, close_date(c), c)
        known[c] = e.groupby("cov_month")["expected"].sum()
    rows = []
    for cov in months:
        row = {"coverage_month": cov}
        prev = 0.0
        for c in months:
            if c < cov:
                row[c] = None
                continue
            val = round(float(known[c].get(cov, 0.0)), 2)
            row[c] = round(val - prev, 2)
            prev = val
        row["current_view"] = prev
        rows.append(row)
    tri = pd.DataFrame(rows).set_index("coverage_month")
    # attribution: which rate version caused each move
    attrib = []
    for i, c in enumerate(months[1:], 1):
        p = months[i - 1]
        new_versions = [v for v in store.versions if close_date(p) < v.recorded_at <= close_date(c)]
        ppa = sum((tri.at[cov, c] or 0) for cov in months if cov < c)
        if abs(ppa) > 0.005 or new_versions:
            attrib.append(dict(close=c, prior_period_adjustment=round(ppa, 2),
                               versions=", ".join(f"{v.version_id} ({v.source_doc})" for v in new_versions) or "-"))
    return tri, pd.DataFrame(attrib)


# --------------------------------------------------------------------------- roll-forward
def exception_rollforward(roster, store, lines, remits, master, months: list[str]):
    prev_open = {}
    rows, snapshots = [], {}
    for c in months:
        exp = expected_revenue(roster, store, close_date(c), c)
        rr = reconcile(exp, lines, remits, store, master, roster, month_end(c), c)
        d = rr.detail
        op = d[d.status.isin(["open", "pending"])]
        cur = {(r.member_id, r.cov_month): r.variance_after for r in op.itertuples()}
        new = {k: v for k, v in cur.items() if k not in prev_open}
        resolved = {k: v for k, v in prev_open.items() if k not in cur}
        rows.append(dict(close=c, opening_items=len(prev_open), opening_usd=round(sum(prev_open.values()), 2),
                         new_items=len(new), new_usd=round(sum(new.values()), 2),
                         resolved_items=len(resolved), resolved_usd=round(sum(resolved.values()), 2),
                         changed_usd=round(sum(cur[k] - prev_open[k] for k in cur if k in prev_open), 2),
                         closing_items=len(cur), closing_usd=round(sum(cur.values()), 2)))
        snapshots[c] = rr
        prev_open = cur
    return pd.DataFrame(rows), snapshots


# --------------------------------------------------------------------------- journal entries
def draft_journal(detail: pd.DataFrame, month: str, cash: pd.DataFrame, unmatched: pd.DataFrame, remits, lumps) -> pd.DataFrame:
    je = []

    def add(n, desc, dr, cr, amt, basis):
        if abs(amt) >= 0.005:
            je.append(dict(entry=n, description=desc, debit=dr, credit=cr, amount=round(abs(amt), 2), basis=basis))

    cur = detail[(detail.cov_month == month)]
    add(1, f"Capitation revenue - {month} coverage (expected, plan roster x approved rates)",
        "1210 Capitation Receivable", "4100 Capitation Premium Revenue", cur.expected.sum(),
        f"{(cur.expected > 0).sum():,} member-months")
    rm = next(r for r in remits if r.period == month)
    qw = sum(h["amount"] for h in rm.header_adjustments if h["code"] == "QW")
    rt = sum(h["amount"] for h in rm.header_adjustments if h["code"] == "RT")
    lines_total = round(rm.bpr_total - qw - rt, 2)
    add(2, f"Apply {month} 820 (trace {rm.trace}) - member-level lines", "1015 Deposits in Transit / Cash", "1210 Capitation Receivable", lines_total, "820 detail lines")
    add(2, "Quality withhold retained by state (1.0%)", "1215 Quality Withhold Receivable", "1210 Capitation Receivable", -qw, "820 header ADX QW")
    add(2, "Region 3 retro lump sum received (allocated back to Jan-Sep member-months)", "1015 Deposits in Transit / Cash",
        "1210 Capitation Receivable", rt, "820 header ADX RT")

    def s(code, col="variance_after"):
        return detail.loc[detail.code == code, col].sum()

    add(3, "Reverse revenue on member-months the state stopped paying (likely missed terms)", "4100 Capitation Premium Revenue",
        "1210 Capitation Receivable", s("STATE_TERMINATED", "expected"), f"{(detail.code == 'STATE_TERMINATED').sum()} member-months")
    add(4, "Reserve member-months never paid by state, pending dispute", "4100 Capitation Premium Revenue",
        "1290 Allowance - Disputed Capitation", s("NEVER_PAID", "expected"), f"{(detail.code == 'NEVER_PAID').sum()} member-months")
    add(5, "Overpayment liability - duplicate payments", "1210 Capitation Receivable", "2150 Due to State - Overpayments",
        s("DUPLICATE_PAYMENT"), f"{(detail.code == 'DUPLICATE_PAYMENT').sum()} member-months")
    add(5, "Overpayment liability - paid after plan termination (not yet recouped)", "1210 Capitation Receivable",
        "2150 Due to State - Overpayments", s("PAID_AFTER_TERM"), f"{(detail.code == 'PAID_AFTER_TERM').sum()} member-months")
    add(6, "Unapplied capitation - members not on plan roster (pending enrollment load)", "1210 Capitation Receivable",
        "2155 Unapplied Capitation", s("UNKNOWN_MEMBER"), f"{(detail.code == 'UNKNOWN_MEMBER').sum()} member-months")
    short = cash[cash.status == "SHORT_PAID"]
    for r in short.itertuples():
        add(7, f"EFT short vs 820 {r.trace} - reclass to due-from-state pending investigation", "1230 Due from State - EFT Variance",
            "1015 Deposits in Transit / Cash", -r.difference, "bank vs 820 BPR")
    for _, r in unmatched.iterrows():
        add(8, f"Unidentified state deposit ref {r['Customer Ref']} on {r['Post Date'].date()} - park in unapplied cash",
            "1010 Cash - Operating", "2156 Unapplied Cash - Unidentified", r.Amount, r.Description)
    return pd.DataFrame(je)
