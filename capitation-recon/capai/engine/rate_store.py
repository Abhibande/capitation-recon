"""
Bitemporal capitation rate store.

Every rate has two time axes:
  * effective (valid) time  - the coverage months the rate applies to
  * knowledge (recorded) time - when finance approved it and it became usable

That lets the engine answer both "what is the right rate for March?" and
"what rate did we *believe* applied to March when we closed April?" - which is
exactly what is needed to separate current-period revenue from prior-period
(retroactive) adjustments.

Versions are immutable. A percentage-style amendment ("+2.1% on all Region 3
cells, on top of rates in effect") is materialised against the state of the
store as of the moment it is recorded, so the materialised numbers are frozen and
auditable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from capai.reference import CATEGORIES, REGIONS, cell_id


def month_range(start: str, end: str) -> list[str]:
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def r2(x: float) -> float:
    return float(f"{x + 1e-9:.2f}")


ALL_CELLS = [cell_id(r, c) for r in REGIONS for c in CATEGORIES]


@dataclass
class RateVersion:
    version_id: str
    source_doc: str
    change_type: str  # "schedule" | "percent_adjustment"
    effective_from: str
    effective_to: str
    recorded_at: datetime  # = approval timestamp; versions are invisible before this
    approved_by: str
    extraction_method: str
    rates: dict[str, float] = field(default_factory=dict)  # schedule: cell -> rate
    adjustment: dict | None = None  # percent rule
    retroactive: bool = False
    notes: str = ""
    materialized: dict[tuple[str, str], float] = field(default_factory=dict)  # (cell, month) -> rate


class RateStore:
    def __init__(self):
        self.versions: list[RateVersion] = []

    # ------------------------------------------------------------------ write
    def commit(self, v: RateVersion) -> RateVersion:
        if self.versions and v.recorded_at < self.versions[-1].recorded_at:
            raise ValueError("versions must be committed in recorded_at order")
        months = month_range(v.effective_from, v.effective_to)
        if v.change_type == "schedule":
            for cell, rate in v.rates.items():
                for mo in months:
                    v.materialized[(cell, mo)] = r2(rate)
        elif v.change_type == "percent_adjustment":
            adj = v.adjustment or {}
            regions = adj.get("regions") or list(REGIONS)
            cats = adj.get("categories") or list(CATEGORIES)
            pct = float(adj["pct"])
            for cell in ALL_CELLS:
                reg, cat = cell.split("-")
                if reg not in regions or cat not in cats:
                    continue
                for mo in months:
                    base = self.rate(cell, mo, as_of=v.recorded_at)
                    if base is None:  # cell not contracted for this month; nothing to adjust
                        continue
                    v.materialized[(cell, mo)] = r2(base * (1 + pct))
        else:
            raise ValueError(v.change_type)
        self.versions.append(v)
        return v

    # ------------------------------------------------------------------ read
    def lookup(self, cell: str, month: str, as_of: datetime | None = None):
        """Return (rate, version_id) in force for a coverage month, as known at `as_of`."""
        for v in reversed(self.versions):
            if as_of is not None and v.recorded_at > as_of:
                continue
            r = v.materialized.get((cell, month))
            if r is not None:
                return r, v.version_id
        return None, None

    def rate(self, cell: str, month: str, as_of: datetime | None = None):
        return self.lookup(cell, month, as_of)[0]

    def history(self, cell: str, month: str) -> list[tuple[str, float, datetime]]:
        """Every rate this cell-month has carried, oldest knowledge first."""
        out, last = [], None
        for v in self.versions:
            r, vid = self.lookup(cell, month, as_of=v.recorded_at)
            if r is not None and r != last:
                out.append((vid, r, v.recorded_at))
                last = r
        return out

    def matching_version(self, cell: str, month: str, amount: float, tol: float = 0.005):
        """Which historical version (if any) produces this exact rate? Used to detect
        the state paying a superseded rate."""
        for vid, r, _ in reversed(self.history(cell, month)):
            if abs(r - amount) <= tol:
                return vid, r
        return None, None

    def get(self, version_id: str) -> RateVersion:
        return next(v for v in self.versions if v.version_id == version_id)

    def grid(self, as_of: datetime | None = None, months: Iterable[str] = ()) -> list[dict]:
        rows = []
        for cell in ALL_CELLS:
            for mo in months:
                r, vid = self.lookup(cell, mo, as_of)
                rows.append(dict(cell=cell, month=mo, rate=r, version_id=vid))
        return rows
