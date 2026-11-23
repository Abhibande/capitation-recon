"""
Rate Intake Agent: turns any state rate publication into a validated, citable
RateChangeProposal that a human approves before it can affect revenue.

    document --> extract (table parser | LLM tool-call | rules fallback)
             --> normalise to canonical schema
             --> validate (completeness, baseline match, reasonableness, dates)
             --> impact preview (which closed periods move, by how much)
             --> approval packet  --> [human sign-off] --> RateStore.commit()

Structured documents (Excel / PDF tables) are parsed deterministically - an LLM
adds risk without adding value there. Free-text notices (emails, letters) are read
by the LLM with a forced tool call against a strict schema. Every extracted field
carries a verbatim citation so the reviewer can check it against the source.
"""
from __future__ import annotations

import email
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from pathlib import Path

from capai.ai.llm import LLM
from capai.engine.rate_store import ALL_CELLS, RateStore, month_range
from capai.reference import CATEGORIES, REGIONS, cell_id

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
REGION_BY_NAME = {v.lower(): k for k, v in REGIONS.items()}

# ----------------------------------------------------------------------------- schema
RATE_CHANGE_TOOL = {
    "name": "record_rate_change",
    "description": "Record the capitation rate change described in a state Medicaid notice.",
    "input_schema": {
        "type": "object",
        "required": ["change_type", "effective_from", "effective_to", "retroactive", "citations", "open_questions"],
        "properties": {
            "change_type": {"type": "string", "enum": ["schedule", "percent_adjustment"]},
            "effective_from": {"type": "string", "description": "First coverage month, YYYY-MM"},
            "effective_to": {"type": "string", "description": "Last coverage month, YYYY-MM (end of rate year if open-ended)"},
            "rates": {"type": "array", "items": {"type": "object", "required": ["region", "category", "rate"],
                       "properties": {"region": {"type": "string", "enum": list(REGIONS)},
                                      "category": {"type": "string", "enum": list(CATEGORIES)},
                                      "rate": {"type": "number"}}}},
            "adjustment": {"type": "object", "properties": {
                "regions": {"type": "array", "items": {"type": "string", "enum": list(REGIONS)}},
                "categories": {"type": "array", "items": {"type": "string", "enum": list(CATEGORIES)},
                               "description": "Empty = all categories"},
                "pct": {"type": "number", "description": "0.021 for +2.1%"},
                "basis": {"type": "string", "enum": ["rates_in_effect_each_month", "original_base_rates"]},
                "rounding": {"type": "string"}}},
            "retroactive": {"type": "boolean"},
            "payment_method": {"type": "string", "description": "How/when the state says it will pay any retro amount"},
            "citations": {"type": "array", "items": {"type": "object", "required": ["field", "quote"],
                          "properties": {"field": {"type": "string"}, "quote": {"type": "string"}}}},
            "open_questions": {"type": "array", "items": {"type": "string"},
                               "description": "Anything ambiguous a human must confirm"},
        },
    },
}

SYSTEM_PROMPT = f"""You extract Medicaid managed-care capitation rate changes for a health plan's revenue team.
Rate cells are region x category. Regions: {REGIONS}. Categories: {CATEGORIES}.
Rules:
- Record only what the document states. Never infer a number that is not written.
- Every field you populate needs a verbatim supporting quote in `citations`.
- If the effective period, the basis of a percentage, rounding, or payment timing is unclear, add it to `open_questions`.
- Dates are coverage months in YYYY-MM. Open-ended changes run to the end of the rate year ({{rate_year_end}}).
"""


@dataclass
class RateChangeProposal:
    source_doc: str
    doc_type: str
    extraction_method: str
    change_type: str
    effective_from: str
    effective_to: str
    published: str | None = None
    rates: dict[str, float] = field(default_factory=dict)
    adjustment: dict | None = None
    retroactive: bool = False
    payment_method: str = ""
    stated_prior_rates: dict[str, float] = field(default_factory=dict)
    citations: list[dict] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    confidence: str = "high"
    checks: list[dict] = field(default_factory=list)
    impact: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------- helpers
def _date_to_month(text: str) -> str | None:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(1)):02d}"
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(\d{4})", text, re.I)
    if m:
        return f"{int(m.group(2)):04d}-{MONTHS[m.group(1).lower()]:02d}"
    return None


def _money(s) -> float:
    return float(str(s).replace("$", "").replace(",", "").strip())


# ----------------------------------------------------------------------------- parsers
def parse_excel(path: Path) -> RateChangeProposal:
    from openpyxl import load_workbook

    ws = load_workbook(path, data_only=True).active
    rows = [[c for c in r] for r in ws.iter_rows(values_only=True)]
    header_idx = next(i for i, r in enumerate(rows) if r and str(r[0]).strip().lower() == "region")
    header = rows[header_idx]
    cat_cols = {}
    for j, h in enumerate(header):
        token = str(h or "").split("\n")[0].strip().upper()
        if token in CATEGORIES:
            cat_cols[j] = token
    preamble = " ".join(str(c) for r in rows[:header_idx] for c in r if c)
    eff = re.search(r"Effective\s+(\S+)\s+through\s+(\S+)", preamble, re.I)
    pub = re.search(r"Published\s+(\S+)", preamble, re.I)
    rates, cites = {}, []
    for r in rows[header_idx + 1:]:
        if not r or str(r[0]).strip().upper() not in REGIONS:
            continue
        reg = str(r[0]).strip().upper()
        for j, cat in cat_cols.items():
            rates[cell_id(reg, cat)] = round(float(r[j]), 2)
    cites.append({"field": "effective period", "quote": eff.group(0) if eff else ""})
    cites.append({"field": "rates", "quote": f"{len(rates)} rate cells read from sheet '{ws.title}' rows {header_idx + 2}-{header_idx + 1 + len(REGIONS)}"})
    return RateChangeProposal(
        source_doc=path.name, doc_type="excel_rate_sheet", extraction_method="deterministic table parser",
        change_type="schedule", effective_from=_date_to_month(eff.group(1)), effective_to=_date_to_month(eff.group(2)),
        published=pub.group(1) if pub else None, rates=rates, citations=cites)


def parse_pdf(path: Path, rate_year_end: str) -> RateChangeProposal:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        tables = [t for p in pdf.pages for t in p.extract_tables()]
    eff_sentence = re.search(r"[^.]*effective[^.]*\.", text.replace("\n", " "), re.I)
    eff_from = _date_to_month(eff_sentence.group(0)) if eff_sentence else None
    rates, prior = {}, {}
    for t in tables:
        hdr = [str(h or "").lower() for h in t[0]]
        if not any("amended" in h for h in hdr):
            continue
        i_reg = next(i for i, h in enumerate(hdr) if "region" in h)
        i_cell = next(i for i, h in enumerate(hdr) if "cell" in h or "category" in h)
        i_new = next(i for i, h in enumerate(hdr) if "amended" in h or "new" in h)
        i_old = next((i for i, h in enumerate(hdr) if "cy20" in h or "prior" in h or "current" in h), None)
        for row in t[1:]:
            reg = row[i_reg].split()[0].strip().upper()
            cat = row[i_cell].split()[0].strip().upper()
            c = cell_id(reg, cat)
            rates[c] = _money(row[i_new])
            if i_old is not None:
                prior[c] = _money(row[i_old])
    date_line = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}", text)
    return RateChangeProposal(
        source_doc=path.name, doc_type="pdf_rate_amendment", extraction_method="deterministic PDF table parser",
        change_type="schedule", effective_from=eff_from, effective_to=rate_year_end,
        published=date_line.group(0) if date_line else None, rates=rates, stated_prior_rates=prior,
        citations=[{"field": "effective date", "quote": eff_sentence.group(0).strip() if eff_sentence else ""},
                   {"field": "rates", "quote": f"{len(rates)} rows read from amendment table"}])


def _read_text_notice(path: Path) -> tuple[str, str | None]:
    raw = path.read_text()
    if path.suffix.lower() == ".eml":
        msg = email.message_from_string(raw, policy=policy.default)
        body = msg.get_body(preferencelist=("plain",)).get_content()
        return f"Subject: {msg['subject']}\nDate: {msg['date']}\n\n{body}", msg["date"]
    return raw, None


def parse_text_with_llm(llm: LLM, path: Path, rate_year_end: str) -> RateChangeProposal:
    text, sent = _read_text_notice(path)
    out = llm.extract(SYSTEM_PROMPT.replace("{rate_year_end}", rate_year_end), text, RATE_CHANGE_TOOL)
    rates = {cell_id(r["region"], r["category"]): float(r["rate"]) for r in out.get("rates", [])}
    adj = out.get("adjustment")
    if adj and not adj.get("categories"):
        adj["categories"] = []
    return RateChangeProposal(
        source_doc=path.name, doc_type="email_notice", extraction_method=f"LLM tool-call ({llm.model})",
        change_type=out["change_type"], effective_from=out["effective_from"], effective_to=out["effective_to"],
        published=sent, rates=rates, adjustment=adj, retroactive=out["retroactive"],
        payment_method=out.get("payment_method", ""), citations=out["citations"], open_questions=out["open_questions"],
        confidence="medium" if out["open_questions"] else "high")


def parse_text_rules(path: Path, rate_year_end: str) -> RateChangeProposal:
    """Offline fallback for free-text notices. Deliberately conservative: always
    medium/low confidence and always routed to a human with explicit questions."""
    text, sent = _read_text_notice(path)
    flat = " ".join(text.split())
    sentences = re.split(r"(?<=[.])\s+", flat)
    cites, questions = [], []

    pct_s = next((s for s in sentences if re.search(r"\d+(\.\d+)?\s?%", s)), None)
    pct = float(re.search(r"(\d+(?:\.\d+)?)\s?%", pct_s).group(1)) / 100 if pct_s else None
    sign = -1 if pct_s and re.search(r"decreas|reduc", pct_s, re.I) else 1
    if pct_s:
        cites.append({"field": "pct", "quote": pct_s})

    s = pct_s or ""
    regions = sorted({REGION_BY_NAME[n] for n in REGION_BY_NAME if n in s.lower()} |
                     {f"R{d}" for d in re.findall(r"Region\s+(\d)", s, re.I)})
    all_cells = bool(re.search(r"every rate cell|all rate cells", pct_s or "", re.I))

    eff_s = next((s for s in sentences if re.search(r"effective", s, re.I) and _date_to_month(s)), None)
    eff_from = _date_to_month(eff_s) if eff_s else None
    if eff_s:
        cites.append({"field": "effective_from", "quote": eff_s})
    retro = bool(re.search(r"retroactive", flat, re.I))

    basis_s = next((s for s in sentences if re.search(r"on top of|in effect for each", s, re.I)), None)
    basis = "rates_in_effect_each_month" if basis_s else None
    if basis_s:
        cites.append({"field": "basis", "quote": basis_s})
    else:
        questions.append("Basis of the percentage (original base rates vs. rates in effect each month) is not stated.")

    pay_s = " ".join(s for s in sentences if re.search(r"lump|remittance|payment system", s, re.I)) or None
    if pay_s:
        cites.append({"field": "payment_method", "quote": pay_s})
    if not all_cells:
        questions.append("Confirm which rate categories are affected.")
    questions.append("Free-text notice parsed by rules fallback (no LLM available) - confirm every field against the source.")
    if re.search(r"formal rate letter will follow", flat, re.I):
        questions.append("State says a formal rate letter will follow - re-check when it arrives.")
    return RateChangeProposal(
        source_doc=path.name, doc_type="email_notice", extraction_method="rules fallback (offline)",
        change_type="percent_adjustment", effective_from=eff_from, effective_to=rate_year_end, published=sent,
        adjustment={"regions": regions, "categories": [] if all_cells else [], "pct": sign * pct, "basis": basis, "rounding": "cent"},
        retroactive=retro, payment_method=pay_s or "", citations=cites, open_questions=questions,
        confidence="medium")


def extract(path: Path, llm: LLM, rate_year_end: str = "2026-12") -> RateChangeProposal:
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm", ".xls"):
        return parse_excel(path)
    if ext == ".pdf":
        return parse_pdf(path, rate_year_end)
    if llm.available:
        return parse_text_with_llm(llm, path, rate_year_end)
    return parse_text_rules(path, rate_year_end)


# ----------------------------------------------------------------------------- validation
def validate(p: RateChangeProposal, store: RateStore, as_of: datetime, last_closed_month: str) -> RateChangeProposal:
    def chk(name, ok, detail, severity="error"):
        p.checks.append({"check": name, "result": "pass" if ok else ("FAIL" if severity == "error" else "WARN"), "detail": detail})

    chk("effective period parsed", bool(p.effective_from and p.effective_to), f"{p.effective_from} to {p.effective_to}")
    if p.change_type == "schedule":
        unknown = [c for c in p.rates if c not in ALL_CELLS]
        chk("rate cells recognised", not unknown, f"{len(p.rates)} cells; unknown: {unknown or 'none'}")
        if not store.versions:
            missing = [c for c in ALL_CELLS if c not in p.rates]
            chk("base schedule complete", not missing, f"missing: {missing or 'none'}")
        else:
            # does the document's stated 'prior' rate equal what we have on file?
            if p.stated_prior_rates:
                mism = {c: (r, store.rate(c, p.effective_from, as_of)) for c, r in p.stated_prior_rates.items()
                        if abs(r - (store.rate(c, p.effective_from, as_of) or 0)) > 0.005}
                chk("stated prior rates match rate store", not mism,
                    "all match" if not mism else f"{len(mism)} differ: {mism}")
            moves = []
            for c, r in p.rates.items():
                cur = store.rate(c, p.effective_from, as_of)
                if cur:
                    moves.append((c, r / cur - 1))
            big = [(c, f"{x:+.1%}") for c, x in moves if abs(x) > 0.15]
            chk("rate change within +/-15%", not big, f"largest move {max((abs(x) for _, x in moves), default=0):.1%}; outliers: {big or 'none'}", "warn")
        neg = [c for c, r in p.rates.items() if r <= 0]
        chk("rates positive", not neg, f"non-positive: {neg or 'none'}")
    else:
        a = p.adjustment or {}
        chk("percentage parsed", a.get("pct") is not None, f"{(a.get('pct') or 0):+.2%}")
        chk("scope parsed", bool(a.get("regions")), f"regions={a.get('regions')} categories={a.get('categories') or 'ALL'}")
        chk("percentage within +/-15%", abs(a.get("pct") or 0) <= 0.15, f"{(a.get('pct') or 0):+.2%}", "warn")
        chk("basis of percentage stated", bool(a.get("basis")), str(a.get("basis")), "warn")
    retro = bool(p.effective_from and p.effective_from <= last_closed_month)
    p.retroactive = p.retroactive or retro
    chk("retroactive to closed periods", not retro,
        f"affects closed months {p.effective_from}..{last_closed_month} - prior-period adjustment required" if retro else "prospective only", "warn")
    if any(c["result"] == "FAIL" for c in p.checks):
        p.confidence = "low"
    return p


def impact_preview(p: RateChangeProposal, store: RateStore, as_of: datetime, roster_counts: dict[tuple[str, str], int]) -> dict:
    """$ impact by coverage month = member-months x (new rate - current rate)."""
    by_month = {}
    for mo in month_range(p.effective_from, p.effective_to):
        tot = 0.0
        for cell in ALL_CELLS:
            n = roster_counts.get((cell, mo), 0)
            if not n:
                continue
            cur = store.rate(cell, mo, as_of) or 0
            if p.change_type == "schedule":
                new = p.rates.get(cell, cur)
            else:
                reg, cat = cell.split("-")
                a = p.adjustment
                if reg in a["regions"] and (not a.get("categories") or cat in a["categories"]):
                    new = round(cur * (1 + a["pct"]) + 1e-9, 2)
                else:
                    new = cur
            tot += n * (new - cur)
        if tot:
            by_month[mo] = round(tot, 2)
    p.impact = by_month
    return by_month
