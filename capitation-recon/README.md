# Capitation Revenue Reconciliation — AI-assisted month-end close (prototype)

A working prototype for the monthly Medicaid capitation close at a health plan:
work out what revenue the plan should have earned, reconcile it to what the state paid
(X12 820) and to what reached the bank, explain every difference, and handle rate
changes that apply to months already closed.

**Design principle: deterministic money, AI at the edges.** All dollar figures come from
code that can be audited and re-run. AI reads messy inputs (rate notices) and writes
explanations, and its output passes through schema validation, citations, a check that
every number it writes appears in the engine's figures, and human approval.

## Quick start

```bash
pip install pandas openpyxl pdfplumber reportlab anthropic   # anthropic optional
python generate_data.py          # synthetic CY2026 scenario (seeded)
python run_close.py --month 2026-10
pytest -q tests
```

Set `ANTHROPIC_API_KEY` to use Claude for free-text rate notices, cluster explanations
and the close memo (`CAPAI_MODEL` selects the model). Without a key, the same steps
run offline on rule-based and template fallbacks, and each output is labelled with the
method that produced it.

## Outputs (`out/`)

| File | What it is |
|---|---|
| `review_console.html` | Reviewer UI: KPIs, exception clusters with AI explanations, rate intake packets, retro triangle, cash, memo, draft JEs |
| `Capitation_Recon_2026-10.xlsx` | Close workpaper with live formulas: summary tie-out, exceptions, cash, retro triangle, withhold, roll-forward, draft JEs, rate history, intake packets, detail |
| `close_memo.txt` | Controller memo |
| `member_month_recon.csv` | Every member-month with expected, paid, root-cause code and evidence |
| `close_bundle.json` | All results (feeds the UI) |

## Layout

```
capai/
  reference.py            rate-cell dimensions, 820 adjustment codes, withhold %
  ingest/remittance.py    X12 820 parser (with SE/BPR integrity checks), bank CSV loader
  ai/llm.py               Claude wrapper (forced tool-use extraction, grounded writing)
  ai/rate_intake.py       Rate Intake Agent: extract -> validate -> impact -> approval packet
  ai/investigator.py      clusters, AI explanations, numeric grounding check, close memo
  engine/rate_store.py    bitemporal, versioned rate store (effective time x knowledge time)
  engine/recon.py         expected revenue, member-month matching, root-cause rules, lump-sum re-performance
  engine/close.py         cash recon, withhold check, retro triangle, roll-forward, draft JEs
  report/                 workbook + HTML console
generate_data.py          synthetic scenario with injected discrepancies + ground truth
run_close.py              orchestrates the close and scores against ground truth
```

## Scenario in the synthetic data

* ~5,000 members, 41k member-months, 28 rate cells (4 regions x 7 categories), Jan–Oct 2026
* Rate changes arrive in three formats: Excel rate sheet (CY2026), PDF amendment (SSI/Expansion, effective
  Jul 1), and an **email** announcing a **retroactive** +2.1% for Region 3 back to Jan 1, paid as a lump sum
* Injected problems: state paid July at superseded rates; missed terms; enrollments the state never loaded;
  members paid but not on the plan's roster; payments after termination (some later recouped); age-band and region
  mismatches; duplicate payments; newborn timing; an EFT short-pay; a deposit received after cut-off; an
  unidentified deposit

Results on this data: 99.2% of member-months reconciled automatically, 9,162 raw variances grouped into 8
root causes, 100% of injected issues found with 0 false positives, and the state's $94,327.62 retro lump
sum re-calculated to the cent. The data is synthetic and every answer is known in advance, so expect
lower numbers on real data. The engine reports cases it cannot explain as UNEXPLAINED and does not
force them into a category.

## Simplifications (known)

Full-month capitation only (no proration or kick payments); the roster is treated as final (rates are
tracked by when they were known, enrollment is not); the 820 layout is simplified; JE amounts are
required ending balances, not changes against an actual GL; approvals come from a JSON fixture standing
in for a workflow tool.
