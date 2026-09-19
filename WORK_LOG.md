# WORK_LOG.md

## Day 1 — Setup, Data Familiarization, and Initial Dataset A Exploration

### Goal
I started by understanding what I was actually working with: the assignment, the folder structure of Dataset A and Dataset B, the event/JSONL format, and what the ground truth in Dataset A actually looked like. I did this before moving into the main analysis and segmentation work

### What I did
I set up my project folder and Python virtual environment, downloaded and extracted the datasets, and looked through the Dataset A and Dataset B directory structures (sessions, chunks, events.jsonl, gt.jsonl, gt_manifest.json). I read through the event schema to understand event types, layers (L1/L2/L3/SYSTEM), and what fields were available on each event.

Once I had a basic picture, I started building the actual loading code: `src/loading/loaders.py`, with functions to parse JSONL, parse timestamps, find chunk directories, merge session events, load `gt_manifest.json`, extract ground-truth executions, and pull out things like active app, event gaps, and browser URLs. I wrote `src/loading/test_load.py` to check that this actually worked, and confirmed it found 63 sessions in Dataset A and could load and sort events correctly.

From there I moved into exploring Dataset A itself. I wrote `src/exploration/gt_overview.py` to look at execution counts, durations, overlaps, duplicate starts, and gaps in the ground truth. I found:
- 63 sessions, 2,009 ground-truth executions, 162,768 raw events, 15 distinct processes
- Domains: Finance 679, HR 671, Ops 659
- 0 zero/negative-duration executions, 0 overlaps, 0 duplicate start timestamps
- 63 executions (3.1%) spanning chunk boundaries

The main problem I found was missing `end_ts` values: 257 out of 2,009 executions (12.8%) had no end timestamp. I wrote `src/exploration/check_none_ends.py` to look into this. I checked whether this was related to executions spanning chunk boundaries (`continues_to_next`), and found that almost all of the affected executions had `continues_to_next=False`, so that didn't explain it. I did not manage to prove the exact root cause — the best explanation I had was that this was likely incomplete start/end pairing during `gt.jsonl` generation, which matches a warning in the spec that `process_switched_out` doesn't always pair with every `process_started`.

Rather than quietly fixing this inside the loader, I created a separate module, `src/exploration/gt_imputation.py`, with a function `impute_missing_end_ts()` that fills in a missing end using the next execution's start time (or the session end for the last execution), and flags every imputed row with `end_imputed=True`. I tested this with `src/exploration/test_gt_imputation.py` and got 257 imputed, 0 still missing, and no cases where an imputed end came before its start.

With the imputed data, I looked at gaps between consecutive processes and found the median gap was 0 seconds, and 94.9% of gaps were under 1 second. I also compared event-level gaps at true boundaries vs inside processes, and the difference was small (median 56ms vs 34ms), and the biggest gap I found inside a process (about 16 minutes) was actually much bigger than the biggest gap at any boundary (about 2.4 minutes).

I then wrote `src/exploration/data_quality.py` to check event type distribution, layer distribution, and field availability. `active_app` and `window_title` were populated on almost every event (99.7% / 99.6%), `extracted_text` was only present on 4.5% of events, and all 118 `text_input_complete` events had missing content, so that field wasn't usable.

Finally, I wrote `src/exploration/boundary_inspection.py` to directly check what was different at true process boundaries vs random midpoints. I checked 20 true boundaries and 10 control points for app switches, large gaps (>5000ms), URL changes, and text changes. While writing this I hit a `TypeError: unhashable type: 'dict'` because `extracted_text` could be a dictionary — I fixed this by comparing string representations instead. Once that was fixed, I got:

| Signal | True boundary | Control |
|---|---|---|
| app_switch | 55% | 10% |
| url_change | 50% | 0% |
| text_change | 60% | 10% |
| large_gap | 10% | 80% |

I also looked at suspend/resume behavior in the raw `gt.jsonl` for a couple of sessions, and noticed `process_resumed` events for the same process code (rather than a fresh `process_started`), and also saw `process_started` fire twice in a row for the same process. Because of this, I decided to use `gt_manifest.json`'s cleaner `executions[]` structure as the main source for segmentation work, and only use raw `gt.jsonl` for reading through things qualitatively.

### What I found
The most important and surprising finding was that large time gaps were NOT a good positive signal for a process boundary — they showed up far more often in the middle of a process (80% of controls) than at actual transitions (10% of true boundaries). This directly contradicted my first instinct, which was that a pause probably means someone switched tasks.

App switches, URL changes, and text changes all looked more promising, but with only 20 boundaries and 10 controls checked, I treated this as exploratory evidence, not a finished model.

### What did not work / problems
- Assuming a large gap = new task turned out to be wrong based on the data.
- `extracted_text` being sometimes a plain string and sometimes a dict caused a crash in my first version of the boundary comparison code.
- Running an output redirect on Windows failed the first time because Japanese text didn't fit the default console encoding — fixed by setting `PYTHONIOENCODING=utf-8` before running the script.
- `text_input_complete` couldn't be used at all — every single one of the 118 events had missing content.

### Decisions
- Keep the raw ground truth untouched in `loaders.py` and do imputation as a separate, explicit, opt-in step, so the missing-end issue itself stays visible as a finding rather than getting silently patched.
- Don't treat a large gap as positive evidence for a boundary — either ignore it or treat it as negative evidence.
- Don't treat an app switch alone as a hard boundary rule, since apps can change within one process (e.g. Chrome → Excel → Chrome could still be one execution).
- Use `gt_manifest.json` as the main ground-truth source rather than raw `gt.jsonl`, because of the duplicate/suspend-resume complications in the raw file.
- Combine multiple signals into a weighted score rather than relying on any single rule. Starting weights I planned to try on Day 2: `app_switch: 0.45, url_change: 0.50, text_change: 0.50, large_gap: -0.30` (later adjusted slightly to -0.35).

### End-of-day state
By the end of the day I had a working data-loading pipeline, a clear picture of Dataset A's structure and quality issues, an explicit way to handle the missing-end problem, and boundary evidence pointing toward a multi-signal approach rather than a single rule. Nothing had actually been segmented or evaluated yet — that was the plan for the next stage. I committed this work as `95787ab` ("Day 1: data exploration, quality checks, evidence-based boundary signal analysis") and pushed it to GitHub.

---

## Day 2 — Segmentation Implementation and Initial Evaluation

### Goal
Turn the boundary evidence from the previous stage into an actual working segmenter, run it against Dataset A's ground truth, and see how good (or bad) it actually was.

### What I did
I built the segmentation detector using the four signals from before: `url_change`, `text_change`, `app_switch` (all positive), and `large_gap` (negative). I used `GAP_THRESHOLD_MS = 5000`, required an app switch to persist for at least 3 events before counting it (to avoid counting quick flickers), and needed a way to pick a good score threshold for actually declaring a boundary.

Rather than guessing a threshold, I ran a sweep from 0.30 to 0.90:

| Threshold | F1 | Avg IoU | Over-seg |
|---|---|---|---|
| 0.30–0.45 | 0.813 | 0.561 | 2.16x |
| 0.50 | 0.852 | 0.573 | 2.06x |
| 0.60+ | ~0.32 | ~0.18 | ~0.5x |

There was a plateau from 0.30–0.45 (because the weights are fixed, so the score only takes a few discrete values), then 0.50 gave the best result, then a sharp drop above that because multiple signals suddenly had to line up at once. I picked 0.50 for the full evaluation.

I built an evaluator that does one-to-one matching between predicted and true segments (based on IoU) and computes precision, recall, F1, average IoU, and an over-segmentation ratio (predicted segments ÷ true segments). Running this across all 63 sessions gave:

- Average IoU: 0.552
- Match rate (IoU ≥ 0.5): 0.625
- Boundary precision: 0.753
- Boundary recall: 0.961
- Boundary F1: 0.842
- Over-segmentation: 2.08x

Error breakdown: 62.8% "good," 32.0% "over-segmented," 3.0% "boundary shift," 1.3% "missed," 0.9% "under-segmented."

So recall was strong, but the detector was producing roughly twice as many segments as it should for a lot of sessions.

I also added a coverage guard, checking whether a session's recorded events actually extend far enough to cover the ground truth (with a 60-second threshold). Running this flagged one session, `ses_20260701-152030-CHAITANYA0BCF`, where recorded events stopped at 15:29:59 but the ground truth ran until 15:46:02 — a gap of about 962.6 seconds. I decided this was a recording/coverage problem, not something my segmenter could be blamed for, and reported both the raw 63-session numbers and a "coverage-valid" 62-session version separately, rather than just excluding it silently.

### What I found
The over-segmentation problem was the main thing to deal with next. I dug into one particularly bad session, `ses_20260701-054901-LAPTOP-R36BQBTE`, and ran a signal-attribution check to see which signals were actually firing. It had 112 raw boundary firings, and `text_change` alone was responsible for 97 of them (86.6%). That pointed me toward `text_change` being the main driver of the over-segmentation, at least in this session.

### What did not work / problems
Nothing failed outright on Day 2, but the results made clear that the initial detector, while having good recall, was too trigger-happy — mostly because of raw text comparison being too sensitive to small differences in the extracted text.

### Decisions
- Use threshold 0.50, based on the sweep, rather than guessing.
- Add a coverage guard as a diagnostic (not something that automatically removes sessions from the evaluation), so a bad score caused by missing recording data doesn't get mistaken for a segmentation failure.
- Investigate the text-change signal further before touching anything else, since it was clearly the dominant contributor to over-segmentation on the worst session.

### End-of-day state
I had a working, evaluated v1 segmenter with known strengths (recall) and a known weakness (over-segmentation, mainly text-driven). The next step was to actually fix the text-change sensitivity rather than just re-tuning the threshold again.

---

## Day 3 — Segmentation Diagnostics and Improvement (v2)

### Goal
Investigate and try to reduce the over-segmentation problem identified on Day 2, specifically around text_change, and check whether URL coverage gaps needed a fallback fix, without just randomly tweaking numbers.

### What I did
Before touching the text-change logic, I checked the URL coverage problem, because I didn't want to build something speculative (like an OCR-based URL fallback) without first checking if it was actually needed. I checked the same problem session (`054901`) directly and found 0 non-None URLs, 0 L3 events, and 0 `browser_navigation` events — the browser extension apparently wasn't capturing anything for that session. I then scanned all of Dataset A and found 6 out of 63 sessions (9.5%) had zero URL coverage, and all six were on the same machine, `LAPTOP-R36BQBTE` (6 of that machine's 7 total sessions). I had set a rule for myself beforehand that I'd only build an OCR fallback if the affected fraction was above 15% — since 9.5% was below that, I decided not to build it, and documented this as a known limitation instead.

Then I worked on the text-change problem. Instead of comparing extracted text for exact inequality, I switched to a similarity comparison using `difflib.SequenceMatcher`, with `TEXT_SIMILARITY_THRESHOLD = 0.85`. I also added a `get_extracted_text()` helper in `loaders.py` to safely handle the fact that `extracted_text` could be either a plain string or a dictionary. Separately, I added a small fix so that if the very first segment in a session was too short, it would get merged forward into the next one instead of being left as a tiny, meaningless fragment.

I re-ran the full evaluation with these two changes (v2) across all 63 sessions:

| Metric | v1 | v2 |
|---|---|---|
| Avg IoU | 0.552 | 0.562 |
| Match rate | 0.625 | 0.667 |
| Precision | 0.753 | 0.755 |
| Recall | 0.961 | 0.929 |
| F1 | 0.842 | 0.829 |
| Over-seg | 2.08x | 1.88x |

So over-segmentation improved, average IoU and match rate improved, but recall and F1 actually got slightly worse. This was a trade-off, not a clean win across every metric, and I made sure to write it up that way rather than only reporting the numbers that looked good.

I re-checked signal attribution on the same problem session after the fix: it went from 112 raw boundaries down to 91, and text_change-alone dropped from 97/112 (86.6%) to 76/91 (83.5%). That's only a 3.1 percentage point drop in the proportion, so the fix reduced the volume of boundaries but didn't really change the underlying mix much for this particular session.

I then classified the 76 remaining text_change-alone boundaries by hand into rough categories: 42 (55.3%) looked like a genuine case/record ID change, 11 (14.5%) looked like a genuine larger content change, 17 (22.4%) looked like short transient jitter, and 6 (7.9%) were ambiguous. So roughly 70% looked genuine and 22% looked like jitter — meaning the fix hadn't "solved" the jitter problem, but most of what was left wasn't jitter either.

I also built a timeline visualization for a few sessions (`ses_20260701-054901-LAPTOP-R36BQBTE`, the CHAITANYA session, and `ses_20260630-121953-LAPTOP-R36BQBTE`) to look at things visually. It confirmed the CHAITANYA coverage gap and showed that over-segmentation was still visible in the other sessions (e.g. 32 true vs 65 predicted for `ses_20260630-121953-LAPTOP-R36BQBTE`). The visualization was coarse, though — it could show the general shape but not every small internal fragment.

Lastly, I built a very basic dominant-app labeler as a smoke test for later downstream labeling work. It worked, producing labels like "WindowsTerminal" or "Google Chrome," but this was intentionally minimal — I knew it wasn't a real semantic labeler and planned to replace it with something better once I got to Dataset B.

### What I found
The main finding was that the text-similarity fix genuinely helped (fewer, more accurate segments) but did not fix the underlying issue completely, and it came at a real cost to recall/F1. I did not want to claim I had "solved" text jitter, because the evidence didn't support that — a meaningful chunk of jitter was still there, just smaller than before.

### What did not work / problems
- The similarity fix only reduced the text_change-alone proportion by about 3 percentage points, much less than I would have expected/hoped.
- Over-segmentation was reduced but still significant in some sessions (e.g., 28 true vs 53 predicted, and 32 true vs 65 predicted in two of the problem sessions I looked at closely).
- Recall and F1 both went down slightly, so v2 wasn't a strict improvement over v1.

### Decisions
- Don't build an OCR URL fallback — the affected fraction (9.5%) was below my own predefined threshold (15%).
- Use the similarity-based text comparison (0.85 threshold) since it produced a real, measurable improvement on over-segmentation and IoU, even though it wasn't a complete fix.
- Add the forward-merge fix for trivial short leading segments.
- Stop tuning segmentation after v2. I decided further tuning risked over-fitting to a couple of specific sessions rather than genuinely improving things, and the text-change diagnostic suggested most of what remained wasn't noise anyway. I locked v2 as the version to carry forward into Dataset B.

### End-of-day state
v2 segmentation was locked: url_change/text_change/app_switch (positive) + large_gap (negative), 0.50 threshold, 0.85 text similarity threshold, forward merge for short leading segments, plus a coverage-guard diagnostic. Known limitations going forward: over-segmentation was reduced but not eliminated, some text jitter remained, URL coverage was missing on one machine, and one session had a serious event-coverage gap. None of this was treated as "solved" — it was documented as the state of the segmenter before moving to Dataset B.

---

## Day 4 — Dataset B Analysis and Process Labeling

### Goal
Apply the locked segmenter to Dataset B (without re-tuning it, since Dataset B has no ground truth to tune against), then find a way to label the resulting segments into meaningful process groups.

### What I did
I first did a sanity check on Dataset B before running anything: 15 sessions, 20,477 events. The application mix was very different from Dataset A (mostly Microsoft Edge, Word, Excel, rather than the browser-portal apps in A). Field coverage was fairly close to Dataset A (URL: 46.5% vs 52.6%, extracted text: 4.6% vs 4.5%). Since I had no ground truth to check against, I decided to use the locked v2 weights as-is rather than guess new ones for Dataset B.

I ran the segmenter across all 15 sessions and got 589 total segments (mean duration 16.43s, median 13.12s, 35.3% under 10 seconds, 9.7% under 5 seconds). This was more than the rough estimate of 150-400 segments I'd been expecting going in. Rather than immediately start changing thresholds to force the number down, I treated this as consistent with the over-segmentation limitation I'd already documented on Dataset A, and moved forward with labeling instead of chasing this number further.

For labeling, I first tried DBSCAN clustering using character n-gram TF-IDF (to avoid needing a Japanese tokenizer) combined with duration/event-count/app-count features. I validated this against the first 20 Dataset A sessions (where I do have ground truth) and got terrible results — purity around 0.097-0.098, with almost everything getting dumped into one giant cluster, regardless of whether I tried eps=0.3, 0.4, 0.5, or 0.6, or changed min_samples.

Instead of continuing to blindly sweep DBSCAN parameters, I ran a feature diagnosis to check whether the underlying feature representation itself was broken (e.g., all boilerplate, degenerate vectors). It wasn't: text vectors were non-zero, the combined feature matrix looked reasonable, and same-app pairs had noticeably smaller distances than different-app pairs (median 0.514 vs 0.894). So the representation had real structure — DBSCAN specifically just wasn't finding it well with the settings I tried.

I then tried K-Means with a few different K values:

| K | Purity | Silhouette |
|---|---|---|
| 10 | 0.293 | 0.307 |
| 12 | 0.302 | 0.276 |
| 15 | 0.372 | 0.245 |
| 18 | 0.367 | 0.241 |

K=15 matched the actual number of Dataset A process types and gave the best purity of the ones I tried, so I looked at it more closely. Some individual clusters looked genuinely coherent (e.g. one cluster was strongly HR/social-insurance related, another was Word/contract-document related), but a lot of the bigger clusters mixed finance, browser setup, payroll, and invoice activity together. So even the best K-Means result wasn't something I felt comfortable calling a validated set of semantic process labels — 0.372 purity just isn't good enough to trust for something as important as labeling automation candidates.

### What I found
Clustering (both DBSCAN and K-Means) was not going to give me a reliable, semantically meaningful set of process labels with the time I had. DBSCAN failed outright; K-Means was better but still too mixed to trust.

### What did not work / problems
- DBSCAN gave essentially useless results across every parameter combination I tried (purity ~0.09-0.10, basically one giant cluster).
- K-Means was better but still not good enough — 0.372 purity and clearly mixed clusters on manual inspection.
- The over-segmentation limitation from Dataset A carried over into Dataset B as expected (589 segments vs the rough 150-400 estimate).

### Decisions
- Stop tuning DBSCAN after multiple parameter combinations all gave essentially the same bad result — continuing to sweep parameters wasn't going to fix a problem that wasn't really about the parameters.
- Run the feature diagnosis before assuming the feature representation was the cause, rather than guessing.
- Treat K-Means as a useful experiment, not as a validated labeler — I wasn't willing to build automation-candidate analysis on top of 0.372 purity clusters that were visibly mixed on inspection.
- Move toward a deterministic rule-based labeling approach instead of continuing to try to force clustering to work.

### End-of-day state
Dataset B was segmented (589 segments) but not yet meaningfully labeled. Clustering had been tried and rejected as unreliable. The plan going forward was to build labeling rules directly from observable evidence in the logs (breadcrumbs, ID prefixes, known applications) rather than relying on unsupervised clustering.

---

## Day 5 — Rule-Based Labeling, Candidate Selection, and the Step 3 Prototype

### Goal
Get a labeling approach that actually worked well enough to trust, pick a real automation candidate from Dataset B, and build a working prototype for it.

### What I did
I first double-checked an odd discrepancy — a segment-count mismatch (585 vs 589) that had come up in earlier clustering diagnostics. After re-running the locked segmenter on the first 20 Dataset A sessions and getting 1,169 segments from 51,210 events, I concluded this wasn't a real bug, just a difference between two separate processing runs/contexts, and didn't spend more time chasing it.

I then built `src/segmentation/rule_labeler.py`, a deterministic rule-based labeler. It checks, in order: a blocklist of non-business applications, Japanese breadcrumb patterns in the page text, ID prefixes (like invoice numbers), the host application, and finally falls back to an app-only label if nothing else matches. A quick smoke test correctly labeled a segment as "発注管理" (purchase order management) using the breadcrumb method.

I validated this against the first 20 Dataset A sessions: 1,169 predicted segments, 580 matched against ground truth with IoU > 0.3, and a purity of 0.786 — a big improvement over K-Means's 0.372 on the same sessions. Based on this, I decided to stop pursuing clustering entirely and use the rule-based labeler for Dataset B.

I applied it to all 15 Dataset B sessions (still 589 segments, same segmentation as before, just now labeled), producing `outputs/segments.jsonl` as the Step 1 deliverable for Dataset B. Labeling method breakdown: host_app 297, breadcrumb 189, id_prefix 41, app_only 32, app_blocklist 30.

For Step 2, I aggregated the labeled segments by frequency, total time, sessions, and machines. A few candidates stood out: 請求書承認・経費精算 (invoice approval/expense settlement) with 27 occurrences across 9 sessions and 4 machines, 入社手続き (onboarding) with 34 occurrences, 経費精算・給与変更 (expense/payroll change) with 30 occurrences, and an `id_INV` label with 17 occurrences. I noticed some of the highest-ranked entries by raw score were actually generic host/app fallback labels (like a bare URL + Edge), so I made sure not to just pick the top score blindly — I inspected the actual content of each candidate before deciding anything.

Looking closer at the invoice-related labels, I found they contained real structured data: invoice numbers, vendor names, amounts, and approval/hold outcomes already visible in the logs. This looked like a good candidate because the decision logic seemed explicit enough to actually automate deterministically, so I decided to build the Step 3 prototype around invoice reconciliation.

I found an instruction in the extracted text describing a monthly fixed-amount vendor list and a reconciliation procedure: check the invoice number, amount, and vendor name against the list, and hold for review if there's a discrepancy. I built `src/exploration/invoice_reconciliation_prototype.py` to scan real Dataset B text, build the vendor master list, parse invoice rows, and compare invoice amounts against the master exactly.

Running this on real Dataset B data: 939 events with non-empty extracted text, 5 vendor-master entries, 108 deduplicated invoice rows. Result: 0 approvals, 108 holds (59 vendor_not_found, 49 amount_mismatch). Every single invoice against a known vendor was being held, which made me suspect the exact-match rule was wrong.

I built `src/exploration/diagnose_real_reconciliation_outcomes.py` to look for actual logged reconciliation decisions already present in the text (lines like "請求書照合完了...差異なし承認" / "差異あり要確認"). I found 29 unique logged outcomes, 13 of which could be tied to a known fixed-amount vendor. Of those 13: 7 were approved (差異なし承認), with differences from the master amount ranging 0.39%-9.80% (median 2.18%), and 6 were held (差異あり要確認), with differences ranging 0.46%-5.53% (median 4.57%). These ranges overlapped — for example 5.03% was held but 5.82% was approved, and 0.46% was held but 1.04% was approved. This meant I couldn't justify any clean percentage tolerance from the data, and I made a deliberate decision not to invent one just to make the numbers look better.

I then checked the invoice `種別` (type) field — 定常 ("routine") vs 調整 ("adjustment") — using `src/exploration/diagnose_invoice_type_field.py`. For the same 13 resolved outcomes, the split was completely clean: all 7 定常 invoices were approved, and all 6 調整 invoices were held. This gave me a real, evidence-based signal to use, though I was careful to treat this as a hypothesis based on a small sample (13 cases), not a confirmed production rule.

I updated the prototype to use vendor scope + invoice type instead of exact amount matching: unknown vendor → hold, ambiguous/malformed master → hold, 定常 → approve, 調整 → hold, unclear type → hold. The amount difference was kept in the output for reference, but it no longer drove the decision. I made sure the vendor-scope check happens before the type check, so an invoice from an unknown vendor can't slip through just because it happens to say 定常.

Running the updated prototype on real Dataset B: 108 invoice rows (68 定常, 40 調整), resulting in 28 approvals and 80 holds (59 vendor_not_found, 21 type_chousei_evidence_based). That's a real change from the old rule's 0/108. I was careful in my notes not to describe 28/108 as a production time-saving estimate — it's just what happened on this test data with this rule.

I also ran synthetic edge-case tests: known vendor + 定常 + exact amount → approve; known vendor + 調整 + exact amount → hold (to prove type overrides amount matching); known vendor + unclear type → hold; unknown vendor + 定常 → hold; malformed amount → hold; duplicate invoice → hold.

### What I found
The exact-amount rule I started with simply didn't match how the real system's logged decisions actually worked. The real driver, based on the evidence I could find, was the invoice type field, not the amount itself. This was only visible because I went back and checked the actual logged reconciliation outcomes instead of assuming my first implementation was correct just because it ran without errors.

### What did not work / problems
- The first invoice prototype (exact amount match) produced 0 real approvals out of 108 rows — a strong sign something was wrong with my assumption, not the data.
- I considered adding a percentage tolerance to fix this, but the real logged data directly contradicted any single clean tolerance value (overlapping ranges between approved and held cases), so I dropped that idea.
- Clustering (Day 4 work) had already failed to produce trustworthy labels, which is why I ended up needing the rule-based labeler in the first place.

### Decisions
- Use the deterministic rule-based labeler instead of clustering, based on the clear purity difference (0.786 vs 0.372) on validated Dataset A sessions.
- Select invoice reconciliation as the Step 3 automation candidate, based on the fact that the logs contained clear structured evidence (invoice numbers, vendors, amounts, outcomes) and an explicit written procedure — not simply because it had the highest heuristic aggregation score.
- Reject a percentage-tolerance rule because the real logged outcomes directly contradicted it.
- Use `定常`/`調整` as the decision driver instead, but explicitly documented as an evidence-based hypothesis from only 13 resolved cases, not a proven business rule.
- Keep the prototype scoped to only the reconciliation decision — no production write-back, no RPA, no AI agent, no OCR pipeline.

### End-of-day state
By the end, I had: a validated rule-based labeler and a labeled `segments.jsonl` for Dataset B; a Step 2 aggregation and candidate analysis; and a working Step 3 prototype for invoice reconciliation that uses an evidence-based decision rule (rather than an invented or unverified one) and is tested against both real Dataset B data and synthetic edge cases. The prototype's scope, its assumptions, and its limitations (especially the small sample size behind the 定常/調整 rule, and the vendors not covered by the fixed-amount list) still needed to be written up properly in the final report.

---

## Use of Generative AI

Throughout the project, I used generative AI (ChatGPT) mainly as a supporting tool: for debugging errors when my code crashed or didn't behave as expected, for discussing possible approaches when I was stuck on how to move forward, for help writing or adjusting parts of code, for explaining unfamiliar Python/library concepts, for helping interpret intermediate results and command-line output, and for helping organize my findings and this work log.

However, the actual decisions were mine. I decided what to investigate at each step, which experiments to actually run, how to interpret the results, and when an approach was or wasn't good enough. In particular, I personally decided to reject the large-gap boundary assumption based on the Day 1 evidence, chose to stop tuning DBSCAN after it repeatedly failed, decided K-Means wasn't reliable enough to use for real labeling despite being the best clustering result I got, chose to move to a deterministic rule-based labeler instead, selected invoice reconciliation as the automation candidate, questioned my own initial exact-amount prototype when it produced 0 approvals, investigated the real logged outcomes myself, decided not to invent an unsupported percentage tolerance even though it would have been an easy fix, identified 定常/調整 as the actual signal based on that investigation, and decided the final scope of the prototype (reconciliation decision only, no write-back or broader automation). ChatGPT did not run the analysis or make these calls independently — it helped me work through problems and organize what I'd already found.