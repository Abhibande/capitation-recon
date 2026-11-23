"""Parsers for the state's X12 820-style capitation remittance and the bank statement export."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd


@dataclass
class Remittance:
    file: str
    trace: str
    pay_date: date
    bpr_total: float
    period: str
    lines: list[dict] = field(default_factory=list)
    header_adjustments: list[dict] = field(default_factory=list)
    integrity: list[str] = field(default_factory=list)


def parse_820(path: Path) -> Remittance:
    segs = [s.strip() for s in path.read_text().split("~") if s.strip()]
    rm = None
    cur = None
    org_loop = False
    seg_count = 0
    in_st = False
    for s in segs:
        el = s.split("*")
        tag = el[0]
        if tag == "ST":
            in_st, seg_count = True, 0
        if in_st:
            seg_count += 1
        if tag == "BPR":
            rm = Remittance(file=path.name, trace="", pay_date=datetime.strptime(el[16], "%Y%m%d").date(),
                            bpr_total=float(el[2]), period="")
        elif tag == "TRN":
            rm.trace = el[2]
        elif tag == "DTM" and cur is None and not rm.period:
            rm.period = el[6][:4] + "-" + el[6][4:6]
        elif tag == "ENT":
            org_loop = el[3] == "FI"
            cur = None if org_loop else {"member_id": el[4], "cell": None, "amount": 0.0, "adx": None, "cov_month": None}
            if cur is not None:
                rm.lines.append(cur)
        elif tag == "REF" and cur is not None and el[1] == "ZZ":
            cur["cell"] = el[2]
        elif tag == "RMR" and cur is not None:
            cur["amount"] = float(el[4])
        elif tag == "DTM" and cur is not None and el[1] == "582":
            cur["cov_month"] = el[6][:4] + "-" + el[6][4:6]
        elif tag == "ADX":
            if org_loop:
                rm.header_adjustments.append({"amount": float(el[1]), "code": el[2], "desc": el[4] if len(el) > 4 else ""})
            elif cur is not None:
                cur["adx"] = el[2]
        elif tag == "SE":
            if int(el[1]) != seg_count:
                rm.integrity.append(f"SE count {el[1]} != {seg_count} segments")
            in_st = False
    for ln in rm.lines:
        if not ln["cell"]:
            rm.integrity.append(f"line for {ln['member_id']} missing rate cell")
    calc = round(sum(l["amount"] for l in rm.lines) + sum(h["amount"] for h in rm.header_adjustments), 2)
    if abs(calc - rm.bpr_total) > 0.005:
        rm.integrity.append(f"BPR total {rm.bpr_total:,.2f} != detail {calc:,.2f}")
    return rm


def load_remittances(folder: Path) -> tuple[list[Remittance], pd.DataFrame]:
    remits = [parse_820(p) for p in sorted(folder.glob("*.x12"))]
    rows = []
    for rm in remits:
        for ln in rm.lines:
            rows.append(dict(trace=rm.trace, pay_date=pd.Timestamp(rm.pay_date), pay_period=rm.period, **ln))
    df = pd.DataFrame(rows)
    no_adx = df["adx"].isna()
    df["line_type"] = "other"
    df.loc[no_adx & (df.cov_month == df.pay_period), "line_type"] = "current"
    df.loc[~no_adx, "line_type"] = "adjustment"
    return remits, df


def load_bank(path: Path) -> pd.DataFrame:
    with open(path) as f:
        df = pd.DataFrame(list(csv.DictReader(f)))
    df["Amount"] = df["Amount"].astype(float)
    df["Post Date"] = pd.to_datetime(df["Post Date"])
    return df
