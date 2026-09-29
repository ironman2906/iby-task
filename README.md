# From Operation Logs to an Automation Proposal

An FDE-style project that turns raw, unlabeled PC operation logs (keystrokes, clicks,
application switches) into 
(1) a segmentation of the log stream into discrete business-process
executions, 
(2) a workload analysis and prioritized automation shortlist, and 
(3) a working prototype for the highest-priority candidate: an invoice reconciliation decision engine.

## Why this exists

Back-office staff (HR, Finance, Logistics) spend their day switching between internal systems
and Office apps. A desktop agent logs every operation, but the logs only record *what was
clicked*, never *which business process it belonged to*. The goal was to recover that missing
structure from the raw event stream, use it to find where automation would actually pay off,
and prove it with something that runs — rather than a slide deck of assumptions.

## What's here

| Stage | Question | Output |
|---|---|---|
| **Step 1 — Segmentation** | Where does one unit of work end and the next begin? | A boundary-detection algorithm, validated against ground truth on Dataset A, applied unchanged to Dataset B |
| **Step 2 — Analysis** | What work is happening, how often, and by whom? | A rule-based process labeler + workload aggregation, feeding a prioritized automation shortlist |
| **Step 3 — Prototype** | Can we automate the top candidate? | A deterministic invoice-reconciliation decision engine, tested against real logged outcomes |

## Results at a glance

- **Segmentation (Dataset A, 63 sessions, ~162k events):** boundary F1 **0.842**, IoU **0.552**
  → after a text-similarity fix (v2): F1 **0.829**, IoU **0.562**, over-segmentation cut from
  **2.08x** to **1.88x**. Recall stayed strong throughout (≥0.92); over-segmentation is the
  main residual weakness and is reported honestly, not hidden.
- **Labeling:** a rule-based labeler (breadcrumb text → ID prefixes → host app → fallback)
  scored **0.786 purity** on held-out Dataset A sessions, decisively beating both DBSCAN
  (~0.10, effectively one giant cluster) and K-Means (0.372, visibly mixed clusters) — both
  of which were tried and explicitly rejected.
- **Automation candidate:** invoice approval / expense reconciliation was selected because it
  was the only candidate with structured, checkable evidence in the logs (vendor, invoice
  number, amount, and logged outcome text), not because it scored highest on a raw frequency
  count.
- **Prototype:** the first, literal decision rule (exact amount match) produced 0 approvals
  out of 108 real invoice rows — a red flag that was investigated rather than shipped. Mining
  the logs for actual resolved outcomes revealed the real driver was the invoice's **type**
  field (`定常`/routine vs. `調整`/adjustment), not amount tolerance. The corrected rule
  yields **28 automatic approvals / 80 holds** on the same 108 rows. This is reported as an
  evidence-based hypothesis from 13 confirmed observations, **not** a validated production
  rule or a time-savings estimate.

Full numbers, methodology, and caveats are in `FINAL_REPORT.md`.

## Repository structure

```
.
├── README.md                          this file
├── README_TASK.md                     original assignment brief
├── FINAL_REPORT.md                    Step 2 analysis, prioritization, Step 3 write-up, risks
├── WORK_LOG.md                        day-by-day log of what was done, tried, and rejected
├── DATA_SCHEMA.md                     data format specification (as provided)
├── data/
│   ├── dataset_a/                     63 sessions, ground truth, used to build/validate Step 1
│   └── dataset_b/                     15 sessions, no ground truth — the production target
├── src/
│   ├── loading/
│   │   ├── loaders.py                 JSONL/session/chunk loading, ground-truth extraction
│   │   └── test_load.py
│   ├── exploration/
│   │   ├── gt_overview.py             ground-truth execution/domain/gap statistics
│   │   ├── check_none_ends.py         investigation of missing end-timestamps in gt.jsonl
│   │   ├── gt_imputation.py           explicit, flagged imputation of missing end times
│   │   ├── test_gt_imputation.py
│   │   ├── data_quality.py            event/field/layer coverage checks
│   │   ├── boundary_inspection.py     true-boundary vs. control-point signal comparison
│   │   ├── diagnose_invoice_type_field.py        Step 3 investigation
│   │   └── diagnose_real_reconciliation_outcomes.py  Step 3 investigation
│   │   └── invoice_reconciliation_prototype.py   Step 3 prototype (final)
│   └── segmentation/
│       └── rule_labeler.py            deterministic process labeler used on Dataset B
└── outputs/
    └── segments.jsonl                 Step 1 deliverable: segmented + labeled Dataset B
```

(`git log` carries the actual chronology — five days of commits, each corresponding to a
stage in `WORK_LOG.md`, including the approaches that were tried and abandoned.)

## Step 1 deliverable format

`outputs/segments.jsonl` — one JSON object per line:

```json
{"session_id": "ses_20260701-183232-LAPTOP-76QMG9DE", "start": "2026-07-01T18:32:32Z", "end": "2026-07-01T18:35:41Z", "label": "expense_processing"}
```

Boundaries were tuned and validated on Dataset A; labels were validated for internal
consistency (same process → same label) using the rule-based labeler's purity score, not
against any Dataset B ground truth, since none exists.

## Method summary

**Segmentation.** Four weighted signals — `app_switch`, `url_change`, `text_change`
(positive), and `large_gap` (negative, based on evidence that idle gaps occur far more often
*inside* a process than at real transitions) — are combined into a score, thresholded at 0.50
(chosen via a sweep, not guessed). v2 replaced exact text-inequality with a similarity
comparison (`difflib.SequenceMatcher`, threshold 0.85) to cut false positives from noisy text
extraction. Locked after Dataset A evaluation and applied to Dataset B unchanged, since
Dataset B has no ground truth to tune against.

**Labeling.** Clustering (DBSCAN, then K-Means) was tried first and rejected — DBSCAN
collapsed almost everything into one cluster regardless of parameters; K-Means's best result
(K=15, matching Dataset A's true process count) still mixed unrelated activity in its larger
clusters. A deterministic rule-based labeler (breadcrumb text patterns → ID prefixes → host
application → app-only fallback) was built instead and clearly outperformed both.

**Prioritization.** Candidates were ranked by a first-pass score (frequency × time ×
variation), but the final pick was not the top scorer by that score alone — generic,
non-business fallback labels were excluded, and invoice reconciliation was chosen because it
was the only candidate backed by structured, checkable data in the logs.

**Prototype.** A deterministic Python script, not an AI agent or RPA — chosen because the
underlying decision, once investigated, turned out to be closer to a fixed rule than a
judgment call, and because no live system access was available (only captured logs). The
first rule (exact amount match) was rejected after producing zero approvals; the logs were
then mined for real resolved outcomes, which pointed to invoice type, not amount tolerance, as
the actual driver.

## Known limitations (see `FINAL_REPORT.md` §6–10 for full detail)

- Segmentation still over-segments a meaningful share of sessions (~1.88x) even after fixes.
- Dataset B has no ground truth — its labels and workload counts are directional, not verified.
- The `定常`/`調整` reconciliation rule rests on only 13 confirmed observations and is an
  evidence-based hypothesis, not a confirmed business rule.
- The recovered vendor-master list covers only 5 vendors; most real invoice rows (59/108)
  fall outside this specific rule's scope.
- The prototype performs no production write-back and was not tested against a live system.


## Running the code

```bash
python -m venv venv && source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# reproduce Step 1 evaluation on Dataset A
python src/exploration/gt_overview.py
python src/segmentation/rule_labeler.py --dataset data/dataset_a --evaluate

# apply the locked segmenter + labeler to Dataset B
python src/segmentation/rule_labeler.py --dataset data/dataset_b --out outputs/segments.jsonl

# run the Step 3 prototype
python src/exploration/invoice_reconciliation_prototype.py --dataset data/dataset_b
```

(Exact script names/flags are as committed in `src/`; see each file's top-level docstring for
current usage — some were exploration/one-off scripts rather than reusable CLIs.)
