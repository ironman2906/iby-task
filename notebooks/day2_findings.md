# Day 2 Findings — Segmentation Baseline and Evaluation

## 1. Segmentation Approach

A first-pass rule-based boundary detector was implemented using four signals:

* `url_change`
* `text_change`
* `app_switch`
* `large_gap`

The initial signal weights were:

| Signal          | Weight |
| --------------- | -----: |
| URL change      |  +0.50 |
| Text change     |  +0.50 |
| App switch      |  +0.45 |
| Large gap (>5s) |  -0.35 |

A predicted boundary is produced when the weighted boundary score reaches the selected threshold.

The `large_gap` signal was given a negative weight because Day 1 analysis showed that large gaps were more common in controls than at true boundaries. Therefore, a large gap alone was not treated as positive evidence for a process transition.

The detector also applies app-switch persistence logic requiring the switched application to persist for at least 3 events.

---

## 2. Threshold Sweep

A threshold sweep was performed over values from 0.30 to 0.90.

| Threshold | Boundary F1 |   Avg IoU | Over-segmentation |
| --------: | ----------: | --------: | ----------------: |
|      0.30 |       0.813 |     0.561 |             2.16x |
|      0.40 |       0.813 |     0.561 |             2.16x |
|      0.45 |       0.813 |     0.561 |             2.16x |
|      0.50 |   **0.852** | **0.573** |         **2.06x** |
|      0.60 |       0.344 |     0.192 |             0.54x |
|      0.70 |       0.316 |     0.172 |             0.45x |
|      0.80 |       0.316 |     0.172 |             0.45x |
|      0.90 |       0.316 |     0.172 |             0.45x |

The score is discrete because the detector uses fixed signal weights. This creates plateaus where changing the threshold does not change which boundaries are triggered.

A sharp performance drop occurs above 0.50. At thresholds above 0.50, a single URL or text change with score 0.50 is no longer sufficient to trigger a boundary, so multiple positive signals must coincide. This substantially reduces boundary recall.

Threshold **0.50** was selected for the v1 evaluation because it gave the highest boundary F1 in the sweep.

---

## 3. Full v1 Evaluation

The selected v1 configuration was evaluated on all 63 sessions with available GT and event data.

### Aggregate metrics

* Sessions evaluated: **63**
* Average IoU: **0.552**
* Match rate at IoU ≥ 0.5: **0.625**
* Boundary precision (10s): **0.753**
* Boundary recall (10s): **0.961**
* Boundary F1: **0.842**
* Over-segmentation ratio: **2.08x**

### Error breakdown

| Error type      | Count | Percentage |
| --------------- | ----: | ---------: |
| Good            |  1262 |      62.8% |
| Over-segmented  |   642 |      32.0% |
| Boundary shift  |    61 |       3.0% |
| Missed          |    26 |       1.3% |
| Under-segmented |    18 |       0.9% |

The baseline achieves high boundary recall, but the relatively high over-segmentation rate shows that the detector tends to create too many predicted segments.

---

## 4. Threshold Trade-off

Although threshold 0.50 gives the best boundary F1, the comparison with threshold 0.45 shows a metric trade-off.

At threshold 0.45:

* Boundary F1: **0.812**
* Boundary precision: **0.711**
* Boundary recall: **0.953**
* Average IoU: **0.556**
* Match rate at IoU ≥ 0.5: **0.663**
* Over-segmentation ratio: **2.08x**

At threshold 0.50:

* Boundary F1: **0.842**
* Boundary precision: **0.753**
* Boundary recall: **0.961**
* Average IoU: **0.552**
* Match rate at IoU ≥ 0.5: **0.625**
* Over-segmentation ratio: **2.08x**

Therefore, threshold 0.50 improves boundary-level precision and F1, but does not improve all segment-level metrics. In particular, the IoU match rate decreases from 0.663 to 0.625 and average IoU decreases slightly.

For v1, 0.50 is retained because the planned threshold sweep selected it by boundary F1, while the segment-level trade-off is recorded as a limitation rather than hidden.

---

## 5. Worst-session Error Analysis

The worst-performing session at the selected threshold was:

`ses_20260701-152030-CHAITANYA0BCF`

Its evaluation results were:

* True segments: **32**
* Predicted segments: **29**
* Boundary F1: **0.494**
* Average IoU: **0.162**

The initial output showed 21 unmatched GT segments. Inspection of the raw event data showed that the session contains **945 events**, but all available events end at **15:29:59.864**.

The chunk manifest confirms:

* Chunk start: **15:20:30.551**
* Chunk end: **15:29:59.864**
* Total events: **945**
* `is_session_end`: **false**
* `next_chunk_id`: `null`

In contrast, the GT continues until **15:46:02.467** and contains 32 true segments.

The 21 unmatched GT segments begin at approximately **15:30:02.953**, after the available event coverage ends.

Therefore, the poor CHAITANYA score is primarily explained by **incomplete event coverage**, rather than a failure of the boundary-detection rules. The session should be treated as a data-coverage anomaly during evaluation rather than as evidence that the segmentation rules need to be changed.

---

## 6. Current Interpretation

The v1 baseline demonstrates that the selected signals can identify process boundaries effectively at the boundary level, with approximately **96% boundary recall** and **84% boundary F1** at the selected threshold.

However, the high over-segmentation ratio (**2.08x**) and lower IoU-based match rate indicate that the predicted segments are often fragmented or shorter than the GT segments.

The threshold sweep also shows that simply increasing the threshold is not a reliable solution. Above 0.50, requiring multiple signals to coincide causes a large drop in recall.

The CHAITANYA worst-session analysis additionally shows that evaluation quality depends on complete event coverage. Missing chunks can create apparent segmentation failures even when the detector has no events available for the corresponding GT interval.

These observations motivate more targeted error analysis before changing the segmentation rules.

## 7. Extension-disconnect investigation
- Confirmed via L3-event/browser_navigation check on ses_20260701-054901-LAPTOP-R36BQBTE:
  0 L3 events, 0 browser_navigation events -> extension never connected for this session
  (consistent with "Extension disconnected" status visible in the ProcMine Agent UI screenshot)
- Dataset-wide scan: 6/63 sessions (9.5%) have zero url_change coverage
- ALL 6 degraded sessions occur on ONE machine: LAPTOP-R36BQBTE
  (6/7 = 85.7% of that machine's sessions affected, vs 0% on all other machines)
- Only the machine's earliest session (ses_20260630-121953-LAPTOP-R36BQBTE) had a
  working extension -> pattern is consistent with the extension connecting once
  and then failing to reconnect across subsequent sessions on that machine,
  rather than random per-session flakiness
- Decision: dataset-wide rate (9.5%) is below the pre-committed 15% threshold
  -> OCR-based URL fallback NOT built. Documented as a known limitation.
- Risk implication for Step 3 (noted for later): browser-extension connectivity
  failures can be machine-specific and persistent rather than random/transient.
  Any automation relying on L3/browser-layer signals should include monitoring
  for per-machine extension health, not just per-session spot checks, since a
  single machine going dark silently removes an entire signal category from
  all its future sessions.

## 6. Evaluation Data-Coverage Check

A coverage check was performed across all 63 evaluated sessions by comparing the end of the available event log with the end of the GT segment sequence.

Using a 60-second warning threshold, only one session was flagged:

- `ses_20260701-152030-CHAITANYA0BCF`
- GT end: 15:46:02.467
- Event-log end: 15:29:59.864
- Difference: approximately 962.6 seconds

The other four worst-performing sessions checked had event logs extending to or beyond their GT end times. The full 63-session scan therefore indicates that the CHAITANYA coverage problem is an isolated anomaly in this dataset.

The CHAITANYA chunk manifest also reported `is_session_end=false`, `next_chunk_id=null`, and `gaps=[]`, despite the GT continuing for approximately 16 minutes after the available event log ended. This shows that manifest metadata alone may not reliably identify incomplete session coverage.

This motivates an explicit GT-versus-event coverage check in the evaluation pipeline so that incomplete logs are flagged rather than silently treated as segmentation failures.
## Data coverage check

1/63 Dataset A sessions (`ses_20260701-152030-CHAITANYA0BCF`) had a 962.6s gap
between the last recorded event (15:29:59) and the ground-truth session end
(15:46:02). The chunk manifest showed `is_session_end=false`,
`next_chunk_id=null`, `gaps=[]` — the agent's own gap detection did not catch
this. All other sessions, including the other four in the original worst-5,
have event coverage extending past GT end.

Original 63-session metrics are preserved for reproducibility. Coverage-valid
metrics (62 sessions) are reported separately: average IoU 0.558, match rate
0.633, boundary precision 0.753, boundary recall 0.971, boundary F1 0.847,
and over-segmentation ratio 2.10x.

The coverage flag is diagnostic only and was not used to tune thresholds or
weights, since this is an isolated data-coverage anomaly rather than an
algorithmic signal.

## Signal attribution and text-change inspection

For the coverage-valid over-segmentation case
(`ses_20260701-054901-LAPTOP-R36BQBTE`), 112 predicted boundaries fired.
Text change was involved in 109/112 boundaries (97.3%), with 97/112
(86.6%) firing from `text_change` alone. `url_change` did not fire in this
session, while `app_switch` only appeared together with `text_change`.

Inspection of representative text-change pairs shows that `text_change`
contains genuine workflow information: transitions between Finance and HR
portals and changes between individual work items produce substantial text
differences. However, some text changes are also UI-state or extraction
changes within the same workflow, such as a full page changing to a short
status message and then back to a page-level extraction.

Therefore, the evidence does not support disabling or simply down-weighting
`text_change`. The current hypothesis is that raw text inequality is too
sensitive, and that text normalization or a minimum similarity/change
criterion may reduce false boundaries while preserving genuine content
changes. This remains a hypothesis to test; no segmentation weights were
changed based on this inspection.

## 9. v2 results — qualitative confirmation via signal_attribution
Manual inspection of fired text_change boundaries on
ses_20260701-054901-LAPTOP-R36BQBTE post-fix shows the signal now captures
genuine workflow transitions: switches between finance/HR portals, and
between individual case records (e.g. EXP-111912-001 -> EXP-111912-002,
different claimants/amounts). The inspection supports the hypothesis that the similarity-threshold fix
preserves genuine content-change signals while filtering some near-duplicate
text variations, consistent with the improved match rate, IoU, and reduced
over-segmentation observed in the v2 evaluation.
aggregate metrics.
## Timeline visualization — observations and a visualization-method caveat
- CHAITANYA coverage anomaly: confirmed visually — PRED shows clear gaps
  near session end where TRUE continues solid, matching the diagnosed
  event-log truncation.
- Both other sessions show PRED as a near-continuous block while TRUE has
  leading/trailing gaps. Likely cause: session-start/end boilerplate
  (orchestrator launch screen, Chrome restore-pages dialog) is being
  captured as a segment, since it produces real app_switch/text_change
  signal despite not being an actual business process.
- LIMITATION OF THIS VISUALIZATION: at 100-character resolution across a
  ~20-30 min session, individual small predicted segments compress into
  what looks like a solid block, so this method confirms gap-level errors
  (like the CHAITANYA case) well, but cannot visually distinguish accurate
  segmentation from over-segmentation within a continuously-covered region.
  The numeric over-segmentation ratio (1.88x dataset-wide) remains the
  reliable metric for that; the timeline view is a supplementary sanity
  check, not a replacement for it.

## 10. Timeline inspection

Text-based TRUE vs PRED timelines were inspected for three representative
sessions.

- `ses_20260701-054901-LAPTOP-R36BQBTE`: PRED has 53 segments versus 28
  TRUE segments, down from 61 predicted segments in the earlier inspection.
  This indicates reduced over-segmentation after the text-similarity fix,
  although substantial fragmentation remains. The coarse 100-character
  visualization cannot expose internal boundaries when predicted segments
  are adjacent, so a visually continuous PRED bar does not imply accurate
  segmentation. The prediction also begins before the first TRUE activity,
  consistent with session-startup/orchestration activity observed during
  earlier signal inspection.

- `ses_20260701-152030-CHAITANYA0BCF`: TRUE extends across the full displayed
  timeline while PRED contains gaps and is based only on the available event
  coverage. This is consistent with the previously identified ~962.6 s gap
  between the final recorded event and the GT end time, supporting the
  interpretation of this session as a coverage anomaly rather than purely
  an algorithmic segmentation failure.

- `ses_20260630-121953-LAPTOP-R36BQBTE`: PRED has 65 segments versus 32 TRUE
  segments, showing that substantial over-segmentation remains in this
  session. As with the first session, the near-continuous PRED bar does not
  indicate accurate boundaries because the visualization is too coarse to
  display adjacent internal fragments.

Overall, the timeline inspection supports the aggregate v2 results:
over-segmentation has been reduced but remains the dominant error mode, and
the CHAITANYA session has a separate event-coverage problem.

## v2 Evaluation Results

The similarity-threshold fix (0.85) and forward-merge fix were applied without
changing the signal weights. The updated detector was re-evaluated across all
63 sessions.

### Aggregate metrics

| Metric | v1 | v2 | Change |
|---|---:|---:|---:|
| Average IoU | 0.552 | 0.562 | +0.010 |
| Match rate (IoU ≥ 0.5) | 0.625 | 0.667 | +0.042 |
| Boundary precision (10s) | 0.753 | 0.755 | +0.002 |
| Boundary recall (10s) | 0.961 | 0.929 | -0.032 |
| Boundary F1 | 0.842 | 0.829 | -0.013 |
| Over-segmentation ratio | 2.08x | 1.88x | -0.20x |

The v2 changes reduced over-segmentation and improved average IoU and
IoU-based match rate. Boundary precision changed only slightly, while
boundary recall and boundary F1 decreased. Therefore, the fix improved
segment-level quality without improving every boundary-level metric.

### Coverage-valid comparison

For the 62 sessions without the identified coverage anomaly:

| Metric | v1 | v2 |
|---|---:|---:|
| Average IoU | 0.558 | 0.568 |
| Match rate (IoU ≥ 0.5) | 0.633 | 0.674 |
| Boundary precision (10s) | 0.753 | 0.755 |
| Boundary recall (10s) | 0.971 | 0.938 |
| Boundary F1 | 0.847 | 0.835 |
| Over-segmentation ratio | 2.10x | 1.90x |

The same pattern remains after excluding the coverage anomaly: reduced
over-segmentation and improved segment-level metrics, with lower boundary
recall and F1.

### v2 error breakdown

| Error type | Count | Percentage |
|---|---:|---:|
| Good | 1343 | 66.8% |
| Over-segmented | 516 | 25.7% |
| Boundary shift | 73 | 3.6% |
| Missed | 41 | 2.0% |
| Under-segmented | 36 | 1.8% |

## Text-change-alone diagnostic (heuristic classification, no re-tuning)
Of 76 text_change-alone boundaries on ses_20260701-054901-LAPTOP-R36BQBTE:
- likely_genuine (case/record ID changed): 42 (55.3%)
- likely_genuine (large content change): 11 (14.5%)
- likely_jitter (short transient text): 17 (22.4%)
- ambiguous: 6 (7.9%)

Combined ~70% likely genuine vs ~22% likely jitter. Similarity scores for
these firings: median 0.061, 75th percentile 0.371 — well below the 0.85
threshold, confirming these are NOT near-duplicate pairs the threshold
could plausibly have caught. This validates the previously-documented
limitation: a similarity threshold targets near-duplicate OCR jitter
specifically, and cannot address structurally-different-but-still-transient
text (e.g. loading states, status toasts) since those pairs are already
far below any reasonable similarity cutoff.

Conclusion: the majority of surviving text_change-alone firings are
genuine. The ~22% residual jitter is a known, now-quantified limitation
requiring a different fix (e.g. minimum-text-length heuristic or
transient-text pattern filtering) than similarity threshold. Not
addressed today per the Day 2 stopping criterion; revisit only if this
pattern proves material on Dataset B during Day 3/4 analysis.

## Day 2 formally closed.