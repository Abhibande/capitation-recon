from datetime import datetime
from pathlib import Path

from capai.ai.investigator import grounding_violations
from capai.engine.rate_store import RateStore, RateVersion
from capai.ingest.remittance import parse_820

DATA = Path(__file__).parents[1] / "data"


def _store():
    s = RateStore()
    s.commit(RateVersion("V1", "a", "schedule", "2026-01", "2026-12", datetime(2025, 12, 1), "x", "t", rates={"R3-SSI": 1000.0}))
    s.commit(RateVersion("V2", "b", "schedule", "2026-07", "2026-12", datetime(2026, 6, 1), "x", "t", rates={"R3-SSI": 1045.0}))
    s.commit(RateVersion("V3", "c", "percent_adjustment", "2026-01", "2026-12", datetime(2026, 9, 20), "x", "t",
                         adjustment={"regions": ["R3"], "categories": [], "pct": 0.021}, retroactive=True))
    return s


def test_bitemporal_lookup():
    s = _store()
    assert s.rate("R3-SSI", "2026-03", as_of=datetime(2026, 4, 6)) == 1000.0   # what we knew at March close
    assert s.rate("R3-SSI", "2026-03") == 1021.0                                # what we know now (retro)
    assert s.rate("R3-SSI", "2026-08", as_of=datetime(2026, 9, 6)) == 1045.0
    assert s.rate("R3-SSI", "2026-08") == 1066.95                               # compounds on Amendment 1


def test_superseded_rate_detection():
    s = _store()
    assert s.matching_version("R3-SSI", "2026-08", 1045.0)[0] == "V2"
    assert s.matching_version("R3-SSI", "2026-08", 999.0)[0] is None


def test_820_balances():
    for f in (DATA / "inbound" / "remittance").glob("*.x12"):
        rm = parse_820(f)
        assert not rm.integrity, rm.integrity


def test_grounding_rejects_invented_numbers():
    facts = {"variance_usd": -13285.37, "member_months": 63}
    assert grounding_violations("Underpaid $13,285.37 over 63 member-months.", facts) == []
    assert grounding_violations("Underpaid $14,000.00 over 63 member-months.", facts) == ["$14,000.00"]
