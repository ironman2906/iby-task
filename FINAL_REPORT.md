# Final Report — From Operation Logs to an Automation Proposal

## 1. Executive Summary

This project analyzed operation logs from a company's back-office systems to identify which business processes would be worth automating, and to build a working prototype for the most promising candidate.

Dataset A (63 sessions, ~162,768 events, with ground truth) was used to build and evaluate a segmentation approach that recovers individual business-process executions from raw event streams. This segmenter was then applied, without retuning, to Dataset B (15 sessions, 20,477 events, no ground truth), which was labeled and analyzed to identify automation candidates. Invoice reconciliation was selected as the Step 3 candidate, and a deterministic Python prototype was built that classified 28 of 108 real invoice rows from Dataset B as eligible for automatic resolution under the prototype rule, while holding the rest for human review.

The most important limitation is that the segmentation still over-segments a meaningful share of sessions (roughly 1.88x more predicted segments than true segments on Dataset A), and the invoice reconciliation decision rule used in the prototype (`定常` invoices approve, `調整` invoices hold) is based on only 13 resolved logged outcomes found in the data. It is an evidence-based hypothesis, not a confirmed production business rule. The 28/108 resolution rate is an observation from this test data, not a measured production time saving.

## 2. Problem and Objective

The operation logs record raw keystrokes, clicks, and application switches for back-office staff, with no markers indicating where one business process ends and another begins. The task had three parts: (1) recover coherent units of work from Dataset A's raw logs and evaluate the approach against its ground truth, (2) apply the same approach to Dataset B, analyze what work is being done and how often, and identify automation candidates, and (3) build a working prototype for the highest-impact candidate and explain the reasoning behind the choice, its scope, its limitations, and the risks of deploying it.

## 3. Step 1 — Recovering Units of Work

### 3.1 Dataset A

Dataset A contains 63 sessions, about 162,768 raw events, and 2,009 ground-truth process executions across 15 distinct process types. It was used because it is the only dataset with ground truth, which made it possible to measure segmentation accuracy directly rather than guessing.

Before building anything, the ground truth itself needed checking. 257 of the 2,009 executions (12.8%) had a missing end timestamp. Checking whether this was related to executions spanning chunk boundaries (`continues_to_next`) showed it was not — almost all affected executions had `continues_to_next=False`. A likely cause was incomplete start/end pairing during ground-truth generation, consistent with a documented warning that `process_switched_out` does not always pair with every `process_started`. Rather than silently repairing the raw ground truth, a separate imputation step was built that fills a missing end using the next execution's start time, with every imputed row explicitly flagged. This preserved the raw data-quality issue as a finding while still allowing duration-based analysis downstream.

Field coverage was also checked before designing the segmentation signals: `active_app` and `window_title` were present on ~99.7% and ~99.6% of events, browser URL on 52.6%, and `extracted_text` on only 4.5%. All 118 `text_input_complete` events had missing content and could not be used.

### 3.2 Segmentation Approach

The first step was checking which signals actually correlate with a real process boundary, rather than assuming one. A natural first guess — that a long pause in activity means a new task started — turned out to be wrong: comparing 20 true boundaries against 10 control (non-boundary) points showed large gaps (>5 seconds) occurred at only 10% of true boundaries but 80% of control points. Gaps, if anything, happen more inside a process than between processes, since 94.9% of actual transitions between processes had a gap under 1 second. Based on this, large gaps were treated as negative evidence rather than a positive boundary signal.

App switches, URL changes, and text changes all showed more promising separation in the same small sample (55%, 50%, and 60% at true boundaries vs. 10%, 0%, and 10% at controls). None of these were treated as hard rules on their own — an app switch, for example, can happen within a single process (e.g. switching to Excel and back) — so the segmentation combined all four signals into a single weighted score, with a threshold above which a boundary is declared.

The threshold was chosen with a sweep from 0.30 to 0.90 rather than picked arbitrarily. In the threshold sweep, 0.50 produced the highest tested F1 of 0.852. I therefore used 0.50 for v1. When v1 was evaluated across all 63 sessions, its overall F1 was 0.842. (The sweep and the full evaluation are separate measurements — the sweep was run to select a threshold, and the full evaluation reports the resulting v1 performance across the whole dataset.)

Evaluating v1 against all 63 sessions showed strong recall (0.961) but heavy over-segmentation (2.08x predicted segments per true segment), with signal attribution on one problem session showing `text_change` alone was responsible for 97 of 112 raw boundary firings (86.6%). This pointed to raw text comparison being too sensitive to small differences in extracted text (e.g. OCR/extraction noise).

v2 addressed this with a text-similarity comparison (`difflib.SequenceMatcher`, threshold 0.85) instead of exact-text inequality, plus a fix to merge a very short leading segment forward into the next one. Before building this, URL coverage was also checked: 6 of 63 sessions (9.5%) had zero URL coverage, all on the same machine, but this was below a predefined 15% threshold for justifying an OCR-based URL fallback, so that fallback was not built.

### 3.3 Evaluation

| Metric | v1 | v2 |
|---|---|---|
| Average IoU | 0.552 | 0.562 |
| Match rate (IoU ≥ 0.5) | 0.625 | 0.667 |
| Boundary precision | 0.753 | 0.755 |
| Boundary recall | 0.961 | 0.929 |
| Boundary F1 | 0.842 | 0.829 |
| Over-segmentation ratio | 2.08x | 1.88x |

v2 reduced over-segmentation and improved average IoU and match rate, but boundary recall and F1 both decreased slightly. This was a genuine trade-off, not an improvement on every metric, and it is presented as such rather than only reporting the metrics that improved.

Signal attribution on the same problem session after the fix showed raw boundary firings dropped from 112 to 91, and `text_change`-alone firings dropped from 97 (86.6%) to 76 (83.5%) — a real but modest reduction. Manually classifying the 76 remaining `text_change`-alone boundaries found roughly 70% looked like genuine content changes and 22% looked like short-lived jitter, so the fix reduced the problem without eliminating it.

### 3.4 Limitations and Decisions

Over-segmentation remains a real limitation after v2 — some individual sessions still showed substantial over-segmentation (e.g. 28 true segments vs. 53 predicted, and 32 true vs. 65 predicted in two sessions inspected closely). URL coverage is incomplete on one specific machine (`LAPTOP-R36BQBTE`). One session (`ses_20260701-152030-CHAITANYA0BCF`) showed a ~962.6 second gap between the last recorded event and the end of its ground truth — this was treated as a recording/coverage anomaly rather than a segmentation failure, and results are reported both including and excluding it.

Tuning was stopped after v2 because further changes risked over-fitting to a small number of specific sessions rather than producing a genuine improvement, and the text-change diagnostic suggested most of the remaining boundary volume was not simply noise. v2 was locked and carried forward to Dataset B unchanged.

## 4. Step 2 — Dataset B Analysis

### 4.1 Dataset B Overview

Dataset B contains 15 sessions and 20,477 events, with no ground truth. Its application mix differs from Dataset A, with Microsoft Edge, Word, and Excel accounting for a large share of the recorded activity. Field coverage is similar to Dataset A (URL: 46.5% vs. 52.6%; extracted text: 4.6% vs. 4.5%). Because there is no ground truth for Dataset B, it was not appropriate to tune the segmentation algorithm against it — the locked v2 configuration was applied as-is.

### 4.2 Dataset B Segmentation

Applying v2 without retuning produced 589 total segments across the 15 sessions (mean duration 16.43s, median 13.12s; 35.3% of segments under 10 seconds, 9.7% under 5 seconds). This was more than a rough initial estimate of 150–400 segments. Rather than adjust thresholds to force this number down without evidence, this was treated as consistent with the over-segmentation limitation already documented on Dataset A.

### 4.3 Process Labeling

Two clustering approaches were tried before settling on a rule-based labeler.

DBSCAN, using character n-gram TF-IDF text features plus duration/event-count/app-count features, was validated against the first 20 Dataset A sessions and gave very poor results — purity around 0.097–0.098 across multiple parameter combinations (eps 0.3–0.6), essentially collapsing everything into one cluster. A feature diagnosis showed this wasn't because the underlying feature representation was degenerate (text vectors were non-zero, and same-app pairs had noticeably smaller distances than different-app pairs), so the DBSCAN failure appeared to be about the clustering method itself with the parameters tried, not a broken input. Rather than continue sweeping DBSCAN parameters indefinitely, this line of investigation was stopped.

K-Means was tried next across several K values, with K=15 (matching Dataset A's actual process count) giving the best tested purity of 0.372. Manual inspection of the resulting clusters showed some genuine coherence (e.g. one cluster strongly HR-related, another Word/contract-related), but many larger clusters mixed unrelated activity together. A purity of 0.372 with visibly mixed clusters was not considered reliable enough to use as the basis for identifying automation candidates.

A deterministic rule-based labeler was built instead, checking (in order) a non-business application blocklist, Japanese breadcrumb text patterns, ID prefixes (such as invoice numbers), the host application, and finally an app-only fallback. Validated on the same 20 Dataset A sessions, this gave a purity of 0.786 against 580 matched segments (IoU > 0.3), substantially better than K-Means's 0.372 on the same sessions. This supported using the rule-based labeler for Dataset B rather than continuing to pursue clustering.

### 4.4 Workload Analysis

Applying the rule-based labeler to Dataset B (still 589 segments) produced `outputs/segments.jsonl`. Aggregating by label showed some of the highest-scoring entries by raw frequency/time were generic fallback labels tied to a bare host+application combination (e.g. `127.0.0.1:5132__Microsoft Edge`), rather than meaningful business processes — these were not treated as automation candidates just because they scored highly.

Among labels that did look like real business processes, a few stood out: `請求書承認・経費精算` (invoice approval / expense settlement, 27 occurrences across 9 sessions and 4 machines), `入社手続き` (onboarding, 34 occurrences), `経費精算・給与変更` (expense/payroll change, 30 occurrences), and `id_INV` (17 occurrences, ID-prefix matched invoice activity). The heuristic priority score used in this aggregation is a first-pass ranking based on frequency, time, and variation — it was not treated as proof of which process has the highest ROI, and each candidate was inspected manually before deciding anything further.

### 4.5 Candidate Prioritization

Invoice reconciliation was selected for the Step 3 prototype. The main reason was that, on inspection, the invoice-related labels contained explicit structured evidence: invoice numbers, vendor names, amounts, and visible outcome text (e.g. "差異なし承認" / "差異あり要確認") already present in the extracted text, along with a written reconciliation procedure captured in the logged text. This gave a realistic basis for building and testing a deterministic decision rule within the available time, unlike candidates where the underlying decision logic would have to be guessed.

This selection comes with real caveats: Dataset B has no ground truth, so the labels themselves are not verified against a true process taxonomy; segmentation still has residual fragmentation, which affects how cleanly individual invoice-related segments are separated; the vendor-master list only covers 5 vendors, so many invoice rows fall outside its scope; and the specific decision rule used in the prototype (described in Section 5.4) rests on a small number of confirmed observations. Invoice reconciliation is not presented as objectively proven to have the highest ROI — it is the candidate for which the available evidence supported building something concrete and testable.

## 5. Step 3 — Invoice Reconciliation Prototype

### 5.1 Selected Scope

The prototype implements the reconciliation decision on captured Dataset B invoice records: given a real invoice row (vendor, invoice number, amount, and type field), it checks the vendor against the fixed-amount vendor list, determines the invoice type, and returns either "approve" or "hold_for_review" with a machine-readable reason and full provenance (session ID and timestamp).

The prototype does **not** perform production-system write-back, does not submit an actual approval anywhere, is not an RPA or AI agent, does not run its own OCR pipeline (it reads the extracted text already captured in Dataset B), and does not handle the full invoice lifecycle beyond this one reconciliation step.

### 5.2 Why This Process

The decision to prototype invoice reconciliation specifically (rather than, say, onboarding or general expense/payroll changes) came from the fact that the underlying decision appeared to follow an explicit written procedure, and the logs contained enough structured data (vendor, amount, invoice ID) to actually test a rule against real captured outcomes — not just plausible-sounding text.

### 5.3 Why Deterministic Python

A deterministic Python script was chosen over the alternatives considered:

- **AI agent**: the underlying decision, once understood, is closer to a fixed rule than a judgment call requiring language understanding; using an AI agent would introduce unnecessary variability and cost for a task the evidence suggested was rule-based.
- **RPA**: RPA would require live integration with a production UI or system, which was not available in this project — only captured logs.
- **OCR**: not needed, since the relevant invoice text was already present in Dataset B's `extracted_text` field; building an OCR pipeline would have added complexity without new capability.
- **Desktop/web application**: building a full application was unnecessary overhead for demonstrating the core decision logic within the prototype's scope.

A deterministic script is reproducible, easy to test against synthetic edge cases, and easy to inspect line-by-line — appropriate given the evidence available and the goal of demonstrating a working decision process rather than a production system.

### 5.4 Initial Rule and Investigation

The first version of the prototype implemented the reconciliation procedure literally: compare the invoice amount to the vendor's fixed monthly amount from the master list, approve on an exact match, hold otherwise. Running this against real Dataset B data (939 events with non-empty extracted text, 5 vendor-master entries, 108 deduplicated invoice rows) produced **0 approvals and 108 holds** (59 vendor_not_found, 49 amount_mismatch).

Getting zero approvals out of 108 rows was a strong signal that the exact-match assumption was probably wrong, so this was investigated further rather than accepted. A diagnostic script searched the extracted text for actual logged reconciliation outcomes already present in the data (lines like "請求書照合完了。INV-XXX　金額：Y円。差異なし承認/差異あり要確認"). This found 29 unique logged outcomes, of which 13 could be reliably tied (via the exact same table row) to one of the 5 fixed-amount vendors.

Of those 13 resolved cases: 7 were logged as approved (差異なし承認), with the invoice amount differing from the master amount by 0.39% to 9.80% (median 2.18%); 6 were logged as held (差異あり要確認), differing by 0.46% to 5.53% (median 4.57%). These ranges overlap directly — for example, a 5.03% difference was held while a 5.82% difference was approved, and a 0.46% difference was held while a 1.04% difference was approved. This ruled out any simple percentage-tolerance rule, and no tolerance was invented to force a cleaner result.

Checking the invoice's `種別` (type) field — `定常` ("routine") vs. `調整` ("adjustment") — against the same 13 resolved outcomes showed a clean separation: **all 7 `定常` invoices were approved, and all 6 `調整` invoices were held**, regardless of the amount difference. This is treated as an evidence-based prototype hypothesis, based on 13 resolved observations — it is explicitly **not** presented as a confirmed production business rule.

### 5.5 Prototype Results

The prototype was updated to use vendor scope plus invoice type as the decision driver, with the amount difference retained only as a logged/provenance field:

- Unknown vendor → hold
- Ambiguous or malformed master amount → hold
- `定常` → approve
- `調整` → hold
- Unclear/missing type → hold

Running this on the full real Dataset B data (108 invoice rows: 68 `定常`, 40 `調整`) produced **28 approvals and 80 holds** (59 vendor_not_found, 21 type-based holds for `調整`).

| | Old rule (exact amount match) | New rule (vendor + type) |
|---|---|---|
| Approve | 0 | 28 |
| Hold | 108 | 80 |

28 of 108 rows changed decision between the two rules. This 28/108 figure is an observation from this test data about how many logged cases the new rule resolves automatically — it is **not** a time-savings estimate, a productivity figure, or a production ROI number.

### 5.6 Edge Cases and Safety

The prototype was tested against synthetic edge cases covering: known vendor + `定常` + exact amount (approve), known vendor + `調整` + exact amount (hold, to confirm type overrides amount matching), known vendor with unclear type (hold), unknown vendor marked `定常` (hold), a malformed amount field (hold), and a duplicate invoice number (second occurrence held). The key safety principle is that the vendor-scope check runs before the type-based approval check, so an invoice from a vendor not in the fixed-amount list cannot be approved just because it happens to carry a `定常` label.

## 6. Manual Work Remaining and Realistic Impact

Even with this prototype in place, humans would still need to: review every invoice from a vendor not on the fixed-amount list (59 of 108 in this sample); review every `調整`-type invoice (40 of 108); investigate any case with an ambiguous or malformed vendor-master amount; validate that the `定常`/`調整` rule actually reflects company policy rather than a pattern that happened to hold in a small sample; confirm exceptions manually; and, until real system integration exists, perform the actual approval action in the production system themselves, since this prototype makes no write-back.

The 28/108 automatic-resolution result in this test data shows that some logged reconciliation cases can, in principle, be resolved by a rule matching what was actually observed in the logs. It does not establish a production time saving. The assignment's own data notes that wait times in this test environment are shorter than production, so any real productivity impact would need to be measured against actual production workflow timings, not estimated from this figure.

## 7. Implementation Feasibility

Before any production deployment, several things would be needed that weren't available in this project: direct access to the production reconciliation system (only captured logs were available here, not a live API or database); confirmation from Finance or the process owner that the `定常`/`調整` distinction is actually the intended rule, not just a pattern in 13 observations; a complete, current vendor-master list, since the one recovered from the logs covers only 5 vendors; a defined process for the vendors and invoice types the prototype holds for review; an audit trail suitable for a financial approval process; and a validation phase comparing the rule's automatic decisions against a much larger set of confirmed human decisions before trusting it unsupervised.

## 8. Risks and Mitigations

| Risk | Evidence | Impact | Mitigation |
|---|---|---|---|
| Dataset B has no ground truth | No `gt.jsonl`/`gt_manifest.json` provided for Dataset B | Labels and segment boundaries cannot be independently verified | Treat Dataset B analysis as directional; validate against real process definitions before relying on it operationally |
| Residual over-segmentation | v2 over-segmentation ratio 1.88x on Dataset A; 589 segments on Dataset B vs. a rough 150–400 estimate | Frequency/time counts per label may be inflated or fragmented | Report frequency/time as approximate; consider further segmentation validation before using counts for precise ROI calculations |
| Incomplete URL coverage | 6/63 Dataset A sessions (9.5%), all on one machine, had zero URL coverage | URL-based boundary evidence unavailable on some machines | Monitor per-machine extension health in any real deployment; the affected fraction here was below the 15% threshold set for building a fallback |
| Vendor master covers only 5 vendors | 59/108 real invoice rows in Dataset B could not be matched to a fixed-amount vendor | Most invoices fall outside this specific reconciliation rule's scope | Confirm with the business whether these vendors are handled by a separate, different process, and scope automation accordingly |
| `定常`/`調整` rule based on 13 resolved cases | Only 13 of 29 logged outcomes could be tied to a known vendor via the row-tied extraction method | Rule may not generalize to a larger population of real invoices | Treat as a hypothesis requiring validation against a much larger confirmed sample before production use |
| Extracted text can be incomplete or inconsistent | `extracted_text` present on only ~4.5–4.6% of events in both datasets; text similarity fix in segmentation needed to handle representation variation | Some real invoice rows or master entries may be missed or misread | Keep vendor-not-found and malformed-amount cases as explicit hold reasons rather than guessing |
| No production write-back tested | Prototype scope explicitly excludes write-back (Section 5.1) | Any real automation would still require a human to act on the "approve" decision until integration exists | Build and test write-back separately once system access and governance approval are available |
| Automatic approval creates audit/governance risk | Prototype currently would auto-approve `定常` invoices with amount differences up to at least 9.80% in the observed sample | Financial approvals without human review carry compliance risk | Keep human-in-the-loop for the initial deployment period; log every automatic decision with full provenance for audit |

## 9. Seven-Day Allocation

The work was organized into five major working stages within the available time:

- **Day 1** — Set up the project, loaded and explored Dataset A, investigated ground-truth quality (including the missing end-timestamp issue and its imputation), and ran the initial boundary-signal investigation that shaped the segmentation design.
- **Day 2** — Implemented and evaluated the v1 segmenter across all of Dataset A, ran a threshold sweep, and identified over-segmentation (driven largely by text-change sensitivity) as the main problem to solve.
- **Day 3** — Investigated and partially fixed the over-segmentation problem (text-similarity comparison, forward-merge fix), re-evaluated as v2, and documented the resulting trade-offs and remaining limitations before locking the segmenter.
- **Day 4** — Applied the locked segmenter to Dataset B, tried and rejected DBSCAN and K-Means clustering for labeling, and moved to a validated deterministic rule-based labeler.
- **Day 5** — Used the rule-based labels to run the Step 2 workload analysis, selected invoice reconciliation as the automation candidate, investigated the actual invoice workflow, built and revised the Step 3 prototype based on real logged outcomes, tested it against real data and synthetic edge cases, and prepared the final report and repository for submission.

This reflects the actual chronology of the work as documented; no additional activity was added to pad the schedule beyond what was genuinely done.

## 10. Limitations and Next Steps

**Limitations of the analysis:** Dataset B has no ground truth, so labeling accuracy could only be validated indirectly via Dataset A. Segmentation still over-segments a meaningful fraction of sessions even after the v2 fix. The rule-based labeler, while much better validated than clustering (0.786 vs. 0.372 purity on Dataset A), is still a heuristic, not verified ground truth for Dataset B specifically.

**Limitations of the prototype:** The `定常`/`調整` decision rule rests on only 13 confirmed observations. The vendor-master list covers only 5 vendors, leaving most real invoice rows (59/108 in this sample) out of scope for this specific check. No production system integration or write-back was built or tested.

**Before production:** the invoice rule would need validation against a much larger set of confirmed decisions; the vendor-master list would need to be confirmed as complete and current; real system integration and audit logging would need to be built; and a human-review workflow would need to be defined for every case this prototype holds.

**Possible next steps:** validate the `定常`/`調整` rule against a larger confirmed dataset; check vendor-master completeness with the actual finance team; integrate with the real reconciliation system; add audit logging for every automatic decision; establish a formal human-review process for held cases; and revisit segmentation/labeling accuracy if Dataset B analysis needs to support more precise ROI estimates in the future.

## 11. Conclusion

This project showed that meaningful process information can be recovered from raw, unlabeled operation logs, but only with careful, evidence-driven work at every stage — checking assumptions against the data rather than assuming an intuitive rule (like "gaps mean new tasks") would hold, and rejecting an invented tolerance rule for invoice reconciliation once the real logged outcomes contradicted it. Segmentation was improved but not solved; clustering was tried and rejected in favor of a validated rule-based labeler; and the invoice reconciliation prototype demonstrates a working, evidence-based decision process, not a finished production system. What remains uncertain — the true generality of the `定常`/`調整` rule, the completeness of the vendor list, and the real production impact — is exactly what would need to be resolved before anything here could be deployed.