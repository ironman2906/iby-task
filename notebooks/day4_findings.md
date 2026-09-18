# Day 4 Findings

## 1. Segment Count Reconciliation

A reconciliation check was performed on the first 20 Dataset A sessions using
the same locked Day 2 `run_segmentation()` implementation.

Results:

- Sessions checked: 20
- Total events: 51,210
- Total predicted segments: 1,169

Per-session segment counts:

65, 65, 46, 47, 58, 53, 65, 62, 50, 74,
64, 49, 48, 48, 58, 75, 64, 57, 59, 62

The previously observed `585` count came from the clustering feature-space
diagnostic and was not confirmed to represent a segmentation discrepancy.
Therefore, no further investigation of the 585/589 difference was pursued.

## 2. Deterministic Rule-Based Labeler

A deterministic rule-based labeler was tested as an alternative to the K-Means
cluster labels.

The labeler uses available evidence such as:

- breadcrumb text;
- record-ID prefixes;
- URL host and dominant application;
- non-business application identification;
- application-only fallback.

The implementation is located at:

`src/segmentation/rule_labeler.py`

A smoke test successfully produced:

`label='発注管理' method='breadcrumb'`

## 3. Rule-Based Labeler Validation

The rule-based labeler was evaluated on the same first 20 Dataset A sessions
used for the K-Means validation.

The evaluation used the locked Day 2 segmentation, the original ground truth,
the same Day 1 end-timestamp imputation procedure, and the existing one-to-one
matching and purity calculation.

Results:

| Metric | Result |
|---|---:|
| Sessions checked | 20 |
| Total predicted segments | 1,169 |
| Matched segments | 580 |
| Rule-labeler purity | 0.786 |
| K-Means purity | 0.372 |

The rule-based labeler achieved substantially higher purity than the K-Means
baseline on this validation subset.

## 4. Rule Labeling Methods

The 1,169 predicted segments were labeled using the following methods:

| Method | Segments |
|---|---:|
| `id_prefix` | 372 |
| `breadcrumb` | 360 |
| `host_app` | 207 |
| `app_blocklist` | 190 |
| `app_only` | 40 |

The largest sources of labels were record-ID prefixes and breadcrumb text.

## 5. Decision

Based on the Dataset A validation:

Rule-labeler purity = 0.786  
K-Means purity = 0.372

The deterministic rule-based labeler was selected for use on Dataset B.
Further K-Means tuning was stopped.

This preserves the locked Day 2 segmentation while replacing the K-Means
labeling step with the deterministic rule-based approach.

## 6. Dataset B Candidate Inspection

The rule-labeled Dataset B segments were inspected for several business-process labels identified by the Step 2 aggregation.

The main candidates examined were:

- `請求書承認・経費精算`
- `入社手続き`
- `経費精算・給与変更`
- `id_INV`

The inspection showed that `経費精算・給与変更` contains some contamination, including segments associated with social-insurance processing, so it was not treated as a clean standalone workflow.

The `入社手続き` segments contain onboarding-related activity such as employee information, start dates, departments, and checklist-style verification, but also contain some noisy text.

The invoice-related labels showed more directly observable and deterministic behavior. In particular, `id_INV` segments contained explicit invoice reconciliation outcomes, including:

- `差異あり要確認` — discrepancy requiring review
- `差異なし承認` — no discrepancy and approval

The `請求書承認・経費精算` segments contained corresponding invoice records with invoice number, vendor, amount, and processing status.

## 7. Invoice Workflow Investigation

The two invoice-related labels were compared using the actual Dataset B event logs rather than only the segment labels.

There were 44 invoice-related target segments across 9 sessions:

| Label | Segments |
|---|---:|
| `id_INV` | 17 |
| `請求書承認・経費精算` | 27 |
| **Total** | **44** |

All 9 sessions contained at least one of the two invoice-related labels, and 8 of the 9 sessions contained both.

The labels also repeatedly alternated within the same sessions. This indicates that they should not be treated as two completely independent automation candidates. Instead, they appear to represent closely related stages or subtasks within a broader invoice-processing workflow.

For example, observed invoice records included:

- `INV-2026-7345` — ¥455,128 — discrepancy requiring review
- `INV-2026-7352` — ¥393,384 — no discrepancy, approved
- `INV-2026-7353` — ¥437,452 — no discrepancy, approved
- `INV-2026-7355` — ¥1,685,384 — no discrepancy, approved

The Dataset B logs also contain an explicit workflow instruction:

> Compare the received invoice's INV number, amount, and vendor name against the monthly fixed-vendor list. If there is a discrepancy, mark it for review and hold it.

This provides a deterministic rule that can be implemented directly in a small automation prototype.

## 8. Step 2 Candidate Decision

Based on the aggregation results and subsequent inspection of the actual Dataset B event sequences, the **invoice reconciliation and approval workflow** was selected as the candidate for the Step 3 automation demonstration.

This is treated as a broader workflow rather than selecting either `id_INV` or `請求書承認・経費精算` as independent processes.

The candidate has:

- repeated occurrences across multiple sessions and machines;
- observable invoice number, amount, and vendor information;
- explicit reconciliation outcomes in the recorded text;
- a deterministic reference-data matching rule;
- both discrepancy and non-discrepancy cases in the dataset.

The Step 3 goal is therefore to build a small working prototype that takes invoice information, compares it against reference data, and produces either an approval result or a review/hold result.

The prototype implementation and live-data demonstration are separate from this candidate-selection finding and have not yet been counted as completed here.
## 9. Candidate Prioritization and Selection Rationale

The candidate analysis was not based on frequency alone. Candidate priority was considered using a combination of:

- frequency of observed segments;
- total observed processing time;
- number of sessions;
- number of machines on which the workflow appeared;
- consistency of segment duration and event count;
- availability of identifiable business inputs and outputs;
- presence of an explicit and implementable business rule;
- feasibility of building a working prototype within the remaining time.

The main candidates considered after semantic inspection were:

1. Invoice reconciliation and approval
2. Onboarding (`入社手続き`)
3. Expense/payroll processing (`経費精算・給与変更`)
4. Contract management (`契約管理`)
5. Inventory management (`在庫管理`)
6. Attendance/leave processing (`勤怠・休暇申請`)

The invoice workflow was selected for the Step 3 demonstration because it had both measurable repeated activity and a concrete deterministic rule that could be implemented and demonstrated using the available evidence.

The ordering above should not be interpreted as a claim that the first process has the highest production ROI. The provided data is test-environment data, and the task notes that waiting time is shorter than in real production. Therefore, the observed absolute time should primarily be used for comparison within this dataset rather than as a direct production-time estimate.

The aggregation `priority_score` was treated as a first-pass heuristic rather than a validated ROI model. Candidate selection additionally required semantic inspection of the underlying event logs.

## 10. Evidence and Limitations of Candidate Selection

The available logs do not identify individual employees directly. Therefore, the `n_machines` field was used as an observable measure of how broadly a workflow appeared across recorded machines; it was not interpreted as an exact count of people involved.

Similarly, the segment labels produced by the rule-based labeler are not ground truth for Dataset B. Dataset B has no ground-truth process labels, so candidate identification combines the rule-based labels with direct inspection of the underlying event logs.

Some residual segmentation and labeling contamination remains. For example, some segments assigned to business-process labels contain unrelated application activity or noisy text. Therefore, candidate-level counts should be interpreted as estimates derived from the segmentation pipeline rather than exact business-process counts.

The invoice candidate was selected despite these limitations because its underlying event data contains unusually explicit evidence of the business operation: invoice identifiers, amounts, vendor information, reconciliation outcomes, and a deterministic comparison rule.

## 11. Step 3 Scope Boundary

The selected automation does not attempt to automate the entire invoice lifecycle.

The initial prototype scope is limited to the reconciliation decision:

- identify the invoice number, amount, and vendor;
- compare these values with reference data;
- detect discrepancies;
- return a clear approval or review/hold result.

Actions such as modifying the production finance system, submitting an approval on behalf of an employee, handling all exceptional cases, or replacing human approval are outside the initial prototype scope.

This narrow scope was chosen because the logs provide direct evidence for the reconciliation rule, while they do not provide enough information to safely specify the complete downstream finance-system workflow.


## 12. Step 3 Prototype Implementation and Results

A deterministic invoice reconciliation prototype was implemented in:

`src/exploration/invoice_reconciliation_prototype.py`

The prototype scans the real Dataset B `extracted_text` records, identifies the vendor master and invoice rows, and applies conservative reconciliation logic.

The prototype does not write to a production finance system, submit approvals, or use an AI agent. It only produces an `approve` or `hold_for_review` decision with an explanation and source provenance.

### 12.1 Decision Logic

The implementation uses the following evidence-based decision order:

1. If the vendor is not present in the fixed-amount vendor master, hold for review.
2. If the vendor has an ambiguous or malformed master entry, hold for review.
3. If the invoice type is `定常`, approve.
4. If the invoice type is `調整`, hold for review.
5. If the invoice type cannot be determined, hold for review.

The `定常`/`調整` rule is an evidence-based prototype hypothesis rather than a confirmed production business rule.

The amount difference between the invoice and the master value is retained in the output for provenance and diagnostics, but is not used as an invented tolerance threshold.

### 12.2 Real Dataset B Results

The prototype successfully parsed 108 deduplicated invoice rows from Dataset B:

| Result | Count |
|---|---:|
| Real invoice rows | 108 |
| `定常` | 68 |
| `調整` | 40 |
| Approved | 28 |
| Held for review | 80 |

Under the previous exact-amount rule, all 108 rows were held because the invoice amount did not have to equal the fixed master amount exactly.

The new evidence-based prototype changed 28 of those decisions from `hold_for_review` to `approve`.

Therefore, 28/108 observed invoice rows (25.9%) were automatically resolved by the prototype on this dataset, while 80/108 (74.1%) remained for human review.

This percentage is an observed Dataset B result, not an estimate of production time savings or production automation coverage.

### 12.3 Examples

A known vendor with `定常` type was approved even when the invoice amount differed from the master amount.

For example:

`大和商事株式会社 | INV-2026-7346 | ¥1,237,439 | 定常 -> approve`

The master amount was ¥1,240,000, so the difference was ¥2,561. The difference was reported but did not determine the decision.

A known vendor with `調整` type was held for review even when the amount difference was small.

For example:

`グローバルテック合同会社 | INV-2026-7344 | ¥716,232 | 調整 -> hold_for_review`

This demonstrates why an amount-based tolerance was not introduced without supporting evidence.

Unknown vendors were also conservatively held for review rather than approved solely because their invoice type was `定常`.

### 12.4 Edge-Case Testing

Synthetic tests were added for the main safety conditions:

- known vendor + `定常` → approve;
- known vendor + `調整` → hold;
- known vendor + unclear type → hold;
- unknown vendor + `定常` → hold;
- malformed amount → hold;
- duplicate invoice number → hold.

The prototype passed these dedicated edge-case checks.

### 12.5 Manual Work Remaining

The prototype does not eliminate the complete invoice-processing workflow.

Human review remains necessary for:

- vendors absent from the reference master;
- ambiguous vendor names;
- `調整` invoices;
- unclear or missing invoice type;
- malformed or incomplete invoice fields;
- duplicate invoice numbers;
- exceptions requiring business judgement;
- final approval and production-system submission.

In the observed Dataset B run, 80 of 108 invoice rows remained in the review path. This is intentional: the prototype prioritizes conservative handling of unsupported cases rather than attempting to maximize automatic approval.

### 12.6 Realistic Impact

The prototype demonstrates that a bounded portion of the observed reconciliation work can be converted from manual decision-making into a deterministic check.

The observed result is 28 automatically resolved rows out of 108. However, this should not be interpreted as 25.9% end-to-end time savings.

The remaining manual work, the time required to investigate held cases, production-system interaction, and the fact that Dataset B is test-environment data all limit what can be inferred about production impact.

A production deployment would require validation against real business outcomes before automatic approval is enabled.

### 12.7 Implementation and Rollout Risks

| Risk | Mitigation |
|---|---|
| The `定常`/`調整` rule is supported by a small observed sample | Validate the rule against additional historical outcomes before production use |
| Vendor names may differ from the reference master | Use controlled vendor IDs or an approved alias table; keep uncertain matches in human review |
| Missing or noisy extracted text may cause incorrect parsing | Validate required fields and route incomplete records to review |
| Duplicate invoice numbers may cause unsafe repeated processing | Detect duplicates and hold them |
| Prototype decisions could be mistaken for production approvals | Keep the prototype read-only until formally validated and integrated |
| Dataset B does not provide production-scale timing evidence | Measure impact during a controlled production pilot |
| Business rules may change | Keep decision logic explicit, version-controlled, and auditable |

### 12.8 Prototype Limitation

The current implementation demonstrates the reconciliation decision only. It does not perform OCR, interact with the finance portal, submit approvals, or replace human judgement for exceptions.

The `定常`/`調整` decision rule should therefore be treated as a documented hypothesis derived from the observed logs, not as a confirmed production policy.