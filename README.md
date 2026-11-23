# Capitation Revenue Reconciliation: AI-assisted month-end close

A working prototype that works out what Medicaid capitation revenue a health plan should
have earned, reconciles it to what the state paid (X12 820) and what reached the bank,
explains every difference, and handles retroactive rate changes.

## ▶ [Open the live demo](https://abhibande.github.io/capitation-recon/)

October 2026 close on synthetic data:

| | |
|---|---|
| Member-months reconciled automatically | **99.2%** of 41,407 |
| Raw differences grouped into root causes | **9,162 → 8** |
| State's $94,327.62 retro lump sum, recalculated | **$0.00 difference** |
| Planted test problems found | **100%**, 0 false alarms |

## How it works
- **Code computes every dollar**: versioned rate history, member-month matching, root-cause rules
- **AI reads and explains**: turns emailed rate notices into structured data, writes plain-English explanations and the close memo; every number it writes is checked against the engine's figures
- **People decide**: rate changes and accounting entries need a named approver

## What's in this repository
- [`capitation-recon/`](capitation-recon): code, sample inputs and tests (see its README)
- [`capitation-recon/data/inbound/`](capitation-recon/data/inbound): sample rate notices (Excel, PDF, email), payment files, bank statement
- Every change automatically re-runs the tests and the full close ([Actions](../../actions)), then republishes the demo

*All data is synthetic; no real member or payment information is used.*
