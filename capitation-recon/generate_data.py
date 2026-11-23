"""
Synthetic data generator for the capitation revenue reconciliation prototype.

Creates a realistic but fully synthetic CY2026 (Jan-Oct) scenario for one Medicaid
managed-care plan:

  data/inbound/rates/      state rate publications in three different formats
                           (Excel rate sheet, PDF amendment, plain-text email)
  data/inbound/remittance/ ten X12 820-style capitation remittance files
  data/inbound/bank/       operating-account bank statement export (CSV)
  data/internal/           the plan's enrollment roster + member master
  data/ground_truth/       the discrepancies we deliberately injected (used only to
                           score the engine, never read by it)

Everything is seeded and deterministic.
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from capai.reference import CATEGORIES, QUALITY_WITHHOLD_PCT, REGIONS, cell_id

ROOT = Path(__file__).parent / "data"
SEED = 20260101
MONTHS = list(range(1, 11))  # Jan..Oct 2026
YEAR = 2026

R = random.Random(SEED)

# --------------------------------------------------------------------------------------
# Rates (the "state truth")
# --------------------------------------------------------------------------------------
BASE = {"CH01": 655.0, "CH20": 212.0, "ADF": 486.0, "ADM": 394.0, "SSI": 1662.0, "EXP": 561.0, "FC": 724.0}
REGION_FACTOR = {"R1": 0.94, "R2": 1.00, "R3": 0.97, "R4": 1.08}
V2_CHANGES = {"SSI": 1.045, "EXP": 0.98}  # Amendment 1, effective 2026-07-01
V3_REGION, V3_PCT = "R3", 0.021  # Amendment 2, retro to 2026-01-01, on top of rates in effect


def r2(x: float) -> float:
    return float(f"{x + 1e-9:.2f}")


V1 = {}
for reg, f in REGION_FACTOR.items():
    for cat, b in BASE.items():
        V1[cell_id(reg, cat)] = r2(b * f * (1 + R.uniform(-0.015, 0.015)))
V2 = {c: (r2(v * V2_CHANGES[c.split("-")[1]]) if c.split("-")[1] in V2_CHANGES else v) for c, v in V1.items()}


def true_rate(cell: str, month: int) -> float:
    """Final, fully amended rate (what the plan should ultimately earn)."""
    base = V2[cell] if month >= 7 else V1[cell]
    if cell.startswith(V3_REGION):
        base = r2(base * (1 + V3_PCT))
    return base


def state_rate(cell: str, cov_month: int, pay_month: int) -> float:
    """Rate the state's payment system applies when paying `cov_month` in the `pay_month` cycle.
    The state implemented Amendment 1 one cycle late (August) and Amendment 2 in October."""
    base = V2[cell] if (cov_month >= 7 and pay_month >= 8) else V1[cell]
    if cell.startswith(V3_REGION) and pay_month >= 10:
        base = r2(base * (1 + V3_PCT))
    return base


# --------------------------------------------------------------------------------------
# Members & plan enrollment
# --------------------------------------------------------------------------------------
def month_start(m: int) -> date:
    return date(YEAR, m, 1)


def age_on(dob: date, d: date) -> int:
    return d.year - dob.year - ((d.month, d.day) < (dob.month, dob.day))


def category_for(member: dict, m: int) -> str:
    prog = member["program"]
    if prog in ("SSI", "EXP", "FC"):
        return prog
    a = age_on(member["dob"], month_start(m))
    if a < 1:
        return "CH01"
    if a <= 20:
        return "CH20"
    return "ADF" if member["sex"] == "F" else "ADM"


members: dict[str, dict] = {}
_next_id = [1000001]


def new_member(start: int, program=None, dob=None, sex=None, region=None, newborn=False) -> str:
    mid = f"M{_next_id[0]}"
    _next_id[0] += 1
    program = program or R.choices(["TANF", "EXP", "SSI", "FC"], [0.62, 0.25, 0.10, 0.03])[0]
    sex = sex or R.choice("FM")
    if dob is None:
        if program == "TANF":
            age = R.randint(0, 20) if R.random() < 0.70 else R.randint(21, 60)
        elif program == "EXP":
            age = R.randint(19, 63)
        elif program == "SSI":
            age = R.randint(22, 64)
        else:
            age = R.randint(1, 19)
        dob = date(YEAR - age - 1, R.randint(1, 12), R.randint(1, 28))
    region = region or R.choices(list(REGIONS), [0.20, 0.30, 0.25, 0.25])[0]
    members[mid] = dict(id=mid, dob=dob, sex=sex, program=program, start=start, end=10,
                        regions=[(start, region)], newborn=newborn)
    return mid


def region_at(member: dict, m: int) -> str:
    reg = member["regions"][0][1]
    for frm, rg in member["regions"]:
        if m >= frm:
            reg = rg
    return reg


for _ in range(4000):
    new_member(1)

# Injected: 15 TANF children who turn 21 during the year (state will not move them to adult cell)
age_lag_ids = []
for k in range(15):
    turn_month = 3 + (k % 7)  # birthday in Mar..Sep -> adult cell from following month
    mid = new_member(1, program="TANF", dob=date(YEAR - 21, turn_month, 10))
    age_lag_ids.append(mid)

protected = set(age_lag_ids)
for m in MONTHS[1:]:
    active = [mid for mid, x in members.items() if x["start"] <= m - 1 <= x["end"] and x["end"] >= m - 1]
    # terminations
    for mid in R.sample(active, int(len(active) * 0.02)):
        if mid not in protected and members[mid]["end"] == 10:
            members[mid]["end"] = m - 1
    # new enrollment
    for _ in range(int(len(active) * 0.022)):
        new_member(m)
    # newborns (born during month m)
    for _ in range(18):
        new_member(m, program="TANF", dob=date(YEAR, m, R.randint(1, 28)), newborn=True)
    # region moves
    still = [mid for mid in active if members[mid]["end"] >= m and mid not in protected]
    for mid in R.sample(still, int(len(still) * 0.004)):
        cur = region_at(members[mid], m)
        members[mid]["regions"].append((m, R.choice([r for r in REGIONS if r != cur])))

plan_roster: dict[tuple[str, int], str] = {}
for mid, x in members.items():
    for m in range(x["start"], x["end"] + 1):
        plan_roster[(mid, m)] = cell_id(region_at(x, m), category_for(x, m))

# --------------------------------------------------------------------------------------
# State eligibility view (starts as plan roster, then diverges)
# --------------------------------------------------------------------------------------
state_view = dict(plan_roster)
truth = []  # ground-truth injected issues


def add_truth(kind, mid, months, note):
    truth.append(dict(issue_type=kind, member_id=mid, months=";".join(f"{YEAR}-{m:02d}" for m in months), note=note))


used = set(age_lag_ids)


def pick(pool, n):
    pool = [p for p in pool if p not in used]
    chosen = R.sample(pool, n)
    used.update(chosen)
    return chosen


full_year = [mid for mid, x in members.items() if x["start"] == 1 and x["end"] == 10 and len(x["regions"]) == 1 and not x["newborn"]]

# A) state terminated member, plan never processed the term (plan-side error)
for mid in pick(full_year, 25):
    k = R.randint(3, 8)
    for m in range(k, 11):
        del state_view[(mid, m)]
    add_truth("PLAN_MISSED_TERM", mid, range(k, 11), f"State termed eff {YEAR}-{k:02d}; plan roster still active")

# B) plan enrolled member that the state never loaded (state-side error)
late_adds = [mid for mid, x in members.items() if 4 <= x["start"] <= 9 and x["end"] == 10 and not x["newborn"] and len(x["regions"]) == 1]
for mid in pick(late_adds, 10):
    x = members[mid]
    for m in range(x["start"], 11):
        del state_view[(mid, m)]
    add_truth("STATE_ENROLLMENT_MISSING", mid, range(x["start"], 11), "Member on plan roster, never paid by state")

# C) member the state pays that is missing from plan roster (834 load gap)
for _ in range(8):
    mid = new_member(1)
    x = members.pop(mid)  # not in plan system at all
    k = R.randint(3, 8)
    reg = x["regions"][0][1]
    for m in range(k, 11):
        state_view[(mid, m)] = cell_id(reg, category_for(x, m))
    add_truth("PLAN_ENROLLMENT_MISSING", mid, range(k, 11), "State paying member not on plan roster")
    used.add(mid)

# D) paid after plan termination; state recoups 3 cycles later (if within window)
recoup_plan = []  # (mid, months, recoup_pay_month)
termed = [mid for mid, x in members.items() if 2 <= x["end"] <= 7 and not x["newborn"]]
for mid in pick(termed, 15):
    e = members[mid]["end"]
    cell = plan_roster[(mid, e)]
    for m in (e + 1, e + 2):
        state_view[(mid, m)] = cell
    rp = e + 4
    recoup_plan.append((mid, (e + 1, e + 2), rp))
    add_truth("PAID_AFTER_TERM", mid, (e + 1, e + 2),
              f"Plan termed after {YEAR}-{e:02d}; " + (f"state recoups in {YEAR}-{rp:02d} 820" if rp <= 10 else "not yet recouped"))

# E) age-band lag: state keeps child cell after 21st birthday
for mid in age_lag_ids:
    x = members[mid]
    bad = []
    for m in MONTHS:
        if plan_roster[(mid, m)].split("-")[1] in ("ADF", "ADM"):
            state_view[(mid, m)] = cell_id(region_at(x, m), "CH20")
            bad.append(m)
    add_truth("AGE_BAND_MISMATCH", mid, bad, "State still paying CH20 after member turned 21")

# F) region change lag: temporary (corrected next cycle) and permanent
movers = [(mid, frm) for mid, x in members.items() for frm, _ in x["regions"][1:] if mid not in used]
temp_lag = [(mid, frm) for mid, frm in movers if frm in (2, 3, 4, 5, 8) and members[mid]["end"] >= frm + 1]
R.shuffle(temp_lag)
region_corrections = []  # (mid, cov_month, old_cell, new_cell) paid in cov_month+1
for mid, frm in temp_lag[:20]:
    used.add(mid)
    x = members[mid]
    old = cell_id(region_at(x, frm - 1), category_for(x, frm))
    new = plan_roster[(mid, frm)]
    state_view[(mid, frm)] = old
    region_corrections.append((mid, frm, old, new))
    add_truth("REGION_LAG_CORRECTED", mid, [frm], f"State paid {old} then corrected to {new} next cycle")
perm = [(mid, frm) for mid, frm in movers if mid not in used and frm <= 8]
R.shuffle(perm)
for mid, frm in perm[:6]:
    used.add(mid)
    x = members[mid]
    bad = []
    for m in range(frm, x["end"] + 1):
        old_reg = region_at(x, frm - 1)
        state_view[(mid, m)] = cell_id(old_reg, category_for(x, m))
        bad.append(m)
    add_truth("REGION_MISMATCH", mid, bad, "State never updated member region")

# --------------------------------------------------------------------------------------
# Payments (820 lines)
# --------------------------------------------------------------------------------------
lines = defaultdict(list)  # pay_month -> list of dict(member, cov, cell, amount, kind, adx)
newborn_ids = {mid for mid, x in members.items() if x["newborn"]}

for (mid, m), cell in sorted(state_view.items(), key=lambda kv: (kv[0][1], kv[0][0])):
    if mid in newborn_ids and members[mid]["start"] == m:
        pm = m + 1  # newborns are retro-enrolled by the state one cycle later
        if pm <= 10:
            lines[pm].append(dict(member=mid, cov=m, cell=cell, amount=state_rate(cell, m, pm), adx="53", kind="retro_enroll"))
        continue
    lines[m].append(dict(member=mid, cov=m, cell=cell, amount=state_rate(cell, m, m), adx=None, kind="cap"))

# newborns whose birth month is Oct are pending at Oct close
for mid in newborn_ids:
    if members[mid]["start"] == 10:
        add_truth("TIMING_NEWBORN", mid, [10], "Newborn retro-enrolled by state next cycle (Nov 820)")

# region-lag corrections (reverse old, pay new) in the following cycle
for mid, frm, old, new in region_corrections:
    pm = frm + 1
    lines[pm].append(dict(member=mid, cov=frm, cell=old, amount=-state_rate(old, frm, frm), adx="52", kind="correction"))
    lines[pm].append(dict(member=mid, cov=frm, cell=new, amount=state_rate(new, frm, pm), adx="53", kind="correction"))
    state_view[(mid, frm)] = new

# Amendment 1 catch-up for July SSI/EXP, paid in the September cycle
for ln in list(lines[7]):
    cat = ln["cell"].split("-")[1]
    if ln["kind"] == "cap" and ln["cov"] == 7 and cat in V2_CHANGES:
        delta = r2(V2[ln["cell"]] - V1[ln["cell"]])
        lines[9].append(dict(member=ln["member"], cov=7, cell=ln["cell"], amount=delta, adx=("53" if delta > 0 else "52"), kind="rate_retro"))
add_truth("RATE_LAG_AMEND1", "*", [7], "State paid July SSI/EXP at pre-amendment rates; caught up in Sep 820")

# Recoupments
for mid, months_, rp in recoup_plan:
    if rp <= 10:
        for m in months_:
            cell = state_view[(mid, m)]
            paid = [l for p in lines for l in lines[p] if l["member"] == mid and l["cov"] == m]
            amt = sum(l["amount"] for l in paid)
            lines[rp].append(dict(member=mid, cov=m, cell=cell, amount=-r2(amt), adx="52", kind="recoup"))
            del state_view[(mid, m)]

# Duplicates in the May cycle
may_caps = [l for l in lines[5] if l["kind"] == "cap"]
for ln in R.sample(may_caps, 12):
    lines[5].append(dict(ln))
    add_truth("DUPLICATE_PAYMENT", ln["member"], [5], "Member paid twice in May 820")

# Amendment 2 retro lump sum (state computes it on its own eligibility basis) in Oct cycle
lump = 0.0
for (mid, m), cell in state_view.items():
    if m <= 9 and cell.startswith(V3_REGION):
        if mid in newborn_ids and members[mid]["start"] == m and m == 9:
            continue  # Sept newborns were paid in Oct at the new rate already
        base = V2[cell] if m >= 7 else V1[cell]
        lump += r2(base * (1 + V3_PCT)) - base
lump = r2(lump)
add_truth("RATE_RETRO_AMEND2", "*", range(1, 10), f"Region 3 +2.1% retro; state lump sum {lump:,.2f} in Oct 820")

# --------------------------------------------------------------------------------------
# Write 820 files
# --------------------------------------------------------------------------------------
def business_day_on_or_before(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def next_business_day(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


remit_dir = ROOT / "inbound" / "remittance"
remit_dir.mkdir(parents=True, exist_ok=True)
remits = []
for pm in MONTHS:
    pay_date = date(YEAR, 10, 29) if pm == 10 else business_day_on_or_before(date(YEAR, pm, 26))
    trace = f"8202026{pm:02d}{R.randint(1000, 9999)}"
    gross_current = r2(sum(l["amount"] for l in lines[pm] if l["kind"] == "cap" and l["cov"] == pm))
    hdr = [("QW", -r2(gross_current * QUALITY_WITHHOLD_PCT), "QUALITY WITHHOLD 1.0 PCT")]
    if pm == 10:
        hdr.append(("RT", lump, "AMEND 2 R3 RETRO JAN-SEP 2026"))
    total = r2(sum(l["amount"] for l in lines[pm]) + sum(h[1] for h in hdr))
    seg = []
    seg.append(f"ISA*00*          *00*          *ZZ*STATEMEDICAID  *ZZ*SUNRISEHP01    *{pay_date:%y%m%d}*0600*^*00501*{100000000 + pm:09d}*0*P*:")
    seg.append(f"GS*RA*STATEMEDICAID*SUNRISEHP01*{pay_date:%Y%m%d}*0600*{pm}*X*005010X218")
    seg.append("ST*820*0001*005010X218")
    seg.append(f"BPR*C*{total:.2f}*C*ACH*CCP*01*071000013*DA*4410023*1366000123**01*021000021*DA*88812004*{pay_date:%Y%m%d}")
    seg.append(f"TRN*1*{trace}*1366000123")
    seg.append(f"DTM*582****RD8*{YEAR}{pm:02d}01-{YEAR}{pm:02d}{(date(YEAR, pm % 12 + 1, 1) - timedelta(days=1)).day if pm < 12 else 31}")
    seg.append("N1*PE*SUNRISE HEALTH PLAN*FI*841234567")
    seg.append("N1*PR*STATE DEPARTMENT OF MEDICAID")
    n = 0
    for ln in sorted(lines[pm], key=lambda l: (l["member"], l["cov"])):
        n += 1
        last = (date(YEAR, ln["cov"] % 12 + 1, 1) - timedelta(days=1)).day if ln["cov"] < 12 else 31
        seg.append(f"ENT*{n}*2J*EI*{ln['member']}")
        seg.append(f"NM1*IL*1******C1*{ln['member']}")
        seg.append(f"REF*ZZ*{ln['cell']}")
        seg.append(f"RMR*AZ*CAP{YEAR}{ln['cov']:02d}**{ln['amount']:.2f}")
        seg.append(f"DTM*582****RD8*{YEAR}{ln['cov']:02d}01-{YEAR}{ln['cov']:02d}{last:02d}")
        if ln["adx"]:
            seg.append(f"ADX*{ln['amount']:.2f}*{ln['adx']}")
    n += 1
    seg.append(f"ENT*{n}*2J*FI*841234567")
    for code, amt, desc in hdr:
        seg.append(f"ADX*{amt:.2f}*{code}*ZZ*{desc}")
    seg.append(f"SE*{len(seg) - 1}*0001")
    seg.append(f"GE*1*{pm}")
    seg.append(f"IEA*1*{100000000 + pm:09d}")
    (remit_dir / f"820_SUNRISEHP_{YEAR}{pm:02d}.x12").write_text("~\n".join(seg) + "~\n")
    remits.append(dict(pm=pm, date=pay_date, trace=trace, total=total))

# --------------------------------------------------------------------------------------
# Bank statement
# --------------------------------------------------------------------------------------
bank_dir = ROOT / "inbound" / "bank"
bank_dir.mkdir(parents=True, exist_ok=True)
bank_rows = []
for rm in remits:
    dep = date(YEAR, 11, 2) if rm["pm"] == 10 else next_business_day(rm["date"])
    amt = rm["total"]
    if rm["pm"] == 8:
        amt = r2(amt - 18432.17)  # unexplained state offset
    bank_rows.append([dep.isoformat(), dep.isoformat(), "ACH CREDIT STATE DEPT MEDICAID CAP PMT", f"{amt:.2f}", f"BK{R.randint(10**8, 10**9 - 1)}", rm["trace"]])
add_truth("CASH_SHORT", "*", [8], "Aug EFT short 18,432.17 vs 820 (state offset)")
add_truth("CASH_IN_TRANSIT", "*", [10], "Oct 820 dated 10/29 deposited 11/02")
bank_rows.append(["2026-09-14", "2026-09-14", "ACH CREDIT STATE DEPT MEDICAID MISC", "46250.00", f"BK{R.randint(10**8, 10**9 - 1)}", "MKP0914"])
add_truth("UNMATCHED_DEPOSIT", "*", [9], "State deposit with no 820 (likely maternity kick payment)")
for m in MONTHS:
    eom = date(YEAR, m + 1, 1) - timedelta(days=1) if m < 12 else date(YEAR, 12, 31)
    bank_rows.append([eom.isoformat(), eom.isoformat(), "INTEREST CREDIT", f"{R.uniform(900, 1600):.2f}", f"BK{R.randint(10**8, 10**9 - 1)}", ""])
    for _ in range(3):
        d = date(YEAR, m, R.randint(2, 27))
        bank_rows.append([d.isoformat(), d.isoformat(), "ACH DEBIT PROVIDER CLAIMS PMT", f"-{R.uniform(1.5e6, 2.4e6):.2f}", f"BK{R.randint(10**8, 10**9 - 1)}", f"CLM{R.randint(10**5, 10**6)}"])
bank_rows.sort(key=lambda r: r[0])
with open(bank_dir / "operating_acct_4410023_2026.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Post Date", "Value Date", "Description", "Amount", "Bank Ref", "Customer Ref"])
    w.writerows(bank_rows)

# --------------------------------------------------------------------------------------
# Rate publications (3 formats)
# --------------------------------------------------------------------------------------
rates_dir = ROOT / "inbound" / "rates"
rates_dir.mkdir(parents=True, exist_ok=True)

# 1) Excel rate sheet (wide)
wb = Workbook()
ws = wb.active
ws.title = "CY2026 Rates"
ws["A1"] = "STATE DEPARTMENT OF MEDICAID"
ws["A1"].font = Font(bold=True, size=14)
ws["A2"] = "Medicaid Managed Care Capitation Rates - Calendar Year 2026"
ws["A3"] = "Effective 01/01/2026 through 12/31/2026   |   Plan: Sunrise Health Plan   |   Published 12/05/2025"
ws["A5"] = "Region"
ws["B5"] = "Region Name"
cats = list(CATEGORIES)
for j, c in enumerate(cats):
    ws.cell(row=5, column=3 + j, value=f"{c}\n{CATEGORIES[c]}")
for col in range(1, 3 + len(cats)):
    ws.cell(row=5, column=col).font = Font(bold=True, color="FFFFFF")
    ws.cell(row=5, column=col).fill = PatternFill("solid", fgColor="1F3864")
    ws.cell(row=5, column=col).alignment = Alignment(wrap_text=True, horizontal="center")
for i, (reg, name) in enumerate(REGIONS.items()):
    ws.cell(row=6 + i, column=1, value=reg)
    ws.cell(row=6 + i, column=2, value=name)
    for j, c in enumerate(cats):
        cell = ws.cell(row=6 + i, column=3 + j, value=V1[cell_id(reg, c)])
        cell.number_format = "$#,##0.00"
ws["A11"] = "Rates are per member per month (PMPM). Rates are certified actuarially sound and are subject to CMS approval."
ws.column_dimensions["B"].width = 14
for j in range(len(cats)):
    ws.column_dimensions[chr(ord("C") + j)].width = 16
ws.row_dimensions[5].height = 45
wb.save(rates_dir / "CY2026_Capitation_Rates_SunriseHP.xlsx")

# 2) PDF amendment (long format table, only changed cells)
styles = getSampleStyleSheet()
doc = SimpleDocTemplate(str(rates_dir / "Rate_Amendment_1_Effective_2026-07-01.pdf"), pagesize=letter,
                        leftMargin=60, rightMargin=60, topMargin=50, bottomMargin=50)
story = [
    Paragraph("<b>STATE DEPARTMENT OF MEDICAID</b>", styles["Title"]),
    Paragraph("Office of Managed Care Finance", styles["Normal"]),
    Spacer(1, 10),
    Paragraph("June 10, 2026", styles["Normal"]),
    Paragraph("To: Sunrise Health Plan, Chief Financial Officer", styles["Normal"]),
    Spacer(1, 8),
    Paragraph("<b>RE: Capitation Rate Amendment No. 1 to the CY2026 Rate Schedule</b>", styles["Heading3"]),
    Paragraph(
        "Following the mid-year actuarial review, the Department is amending capitation rates for the SSI/ABD Adult and "
        "Expansion Adult rate cells. <b>The amended rates below are effective for coverage months beginning July 1, 2026</b> "
        "and replace the corresponding CY2026 rates. All other rate cells remain unchanged. Rates are per member per month.",
        styles["Normal"]),
    Spacer(1, 10),
]
tbl = [["Region", "Rate Cell", "CY2026 Rate", "Amended Rate", "Change"]]
for reg in REGIONS:
    for cat in V2_CHANGES:
        c = cell_id(reg, cat)
        tbl.append([f"{reg} - {REGIONS[reg]}", f"{cat} - {CATEGORIES[cat]}", f"${V1[c]:,.2f}", f"${V2[c]:,.2f}", f"{(V2[c] / V1[c] - 1) * 100:+.1f}%"])
t = Table(tbl, colWidths=[110, 160, 75, 80, 55])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
]))
story += [t, Spacer(1, 12),
          Paragraph("Questions regarding this amendment may be directed to the Office of Managed Care Finance. "
                    "This amendment is subject to CMS approval of the associated contract amendment.", styles["Normal"]),
          Spacer(1, 18), Paragraph("Sincerely,<br/>Director, Office of Managed Care Finance", styles["Normal"])]
doc.build(story)

# 3) Email (unstructured narrative, percentage rule, retroactive)
eml = f"""From: Managed Care Finance <mcfinance@medicaid.state.example>
To: finance@sunrisehp.example
Date: Fri, 18 Sep 2026 15:42:10 -0500
Subject: CY2026 Rate Amendment No. 2 - Region 3 adjustment (RETROACTIVE)
Content-Type: text/plain; charset="utf-8"

Good afternoon,

CMS has approved the state directed payment preprint for Southeast providers. To fund it,
the Department is increasing capitation for every rate cell in Region 3 (Southeast) by 2.1%.

The increase is effective retroactive to January 1, 2026, and applies on top of whatever
rate was in effect for each coverage month - i.e., January-June coverage is increased from
the original CY2026 rates and July coverage onward is increased from the Amendment No. 1
rates. Rates should be rounded to the nearest cent.

Our payment system will begin paying the new Region 3 rates with the October 2026 cycle.
Retroactive amounts for January through September 2026 coverage will be paid as a single
lump-sum adjustment on the October 2026 remittance rather than member-by-member.

No other regions are affected. A formal rate letter will follow.

Thank you,
Office of Managed Care Finance
State Department of Medicaid
"""
(rates_dir / "Rate_Amendment_2_Region3_retro.eml").write_text(eml)

# --------------------------------------------------------------------------------------
# Internal plan data
# --------------------------------------------------------------------------------------
internal = ROOT / "internal"
internal.mkdir(parents=True, exist_ok=True)
with open(internal / "member_master.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["member_id", "dob", "sex", "program"])
    for mid, x in sorted(members.items()):
        w.writerow([mid, x["dob"].isoformat(), x["sex"], x["program"]])
with open(internal / "enrollment_roster.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["member_id", "coverage_month", "region", "rate_category"])
    for (mid, m), cell in sorted(plan_roster.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        reg, cat = cell.split("-")
        w.writerow([mid, f"{YEAR}-{m:02d}", reg, cat])

# Sign-offs recorded by finance when each rate version was reviewed in the intake queue
approvals = {
    "RV-2026-001": {"approved_by": "D. Okafor (Revenue Accounting Mgr)", "approved_at": "2025-12-10T14:05:00", "doc": "CY2026_Capitation_Rates_SunriseHP.xlsx"},
    "RV-2026-002": {"approved_by": "D. Okafor (Revenue Accounting Mgr)", "approved_at": "2026-06-15T10:20:00", "doc": "Rate_Amendment_1_Effective_2026-07-01.pdf"},
    "RV-2026-003": {"approved_by": "L. Martinez (Controller)", "approved_at": "2026-09-22T16:45:00", "doc": "Rate_Amendment_2_Region3_retro.eml",
                    "note": "Confirmed with state by phone 9/21: percentage compounds on Amendment 1 rates from July."},
}
(internal / "rate_approvals.json").write_text(json.dumps(approvals, indent=2))

gt = ROOT / "ground_truth"
gt.mkdir(parents=True, exist_ok=True)
with open(gt / "injected_issues.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["issue_type", "member_id", "months", "note"])
    w.writeheader()
    w.writerows(truth)
(gt / "true_rates.json").write_text(json.dumps({f"{c}|{m}": true_rate(c, m) for c in V1 for m in MONTHS}, indent=0))

print(f"members on plan roster: {len(members):,}  member-months: {len(plan_roster):,}")
print(f"820 files: {len(remits)}  lines: {sum(len(v) for v in lines.values()):,}  R3 lump sum: {lump:,.2f}")
print(f"injected issues: {len(truth)}")
