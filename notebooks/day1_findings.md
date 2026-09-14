# Day 1 Findings — Operation Log Segmentation (Dataset A)

## 1. Overview of the data

- Sessions with ground truth: 63
- Total true segments (process executions): 2009
- Avg executions per session: 31.9
- Total raw events across all sessions: 162,768

### Distinct processes (15 total)

| Code | Name (Japanese) | Domain (inferred) |
|---|---|---|
| A | 住民税通知確認 (resident tax notification check) | HR |
| B | 給与備考・控除整備 (payroll remarks/deductions maintenance) | HR |
| C | 育児・産休申請確認 (childcare/maternity leave application check) | HR |
| D | 社保・年金補正対応 (social insurance/pension correction handling) | HR |
| E | 入社照合・手当確認 (new-hire verification/allowance check) | HR |
| F | 請求書承認 (invoice approval) | Finance |
| G | 経費精算承認 (expense settlement approval) | Finance |
| H | 銀行勘定照合 (bank account reconciliation) | Finance |
| I | 予算差異分析 (budget variance analysis) | Finance |
| J | 支払処理 (payment processing) | Finance |
| K | 受注処理 (order processing) | Ops |
| L | 在庫調整 (inventory adjustment) | Ops |
| M | 仕入先連絡 (supplier communication) | Ops |
| N | 出荷追跡 (shipment tracking) | Ops |
| O | 返品処理 (returns processing) | Ops |

- Domain distribution: finance=679, hr=671, ops=659 (well balanced)
- Variant distribution: None=1147, std=339, reg=332, exc=116, adj=75

---

## 2. Event type / layer distribution (from data_quality.py, all 162,768 events)

### Top event types
| event_type | count | % |
|---|---|---|
| app_switch | 50,588 | 31.1% |
| keystroke | 38,717 | 23.8% |
| screenshot_smart | 34,580 | 21.2% |
| shortcut | 13,668 | 8.4% |
| mouse_click | 6,177 | 3.8% |
| browser_click | 5,365 | 3.3% |
| clipboard_change | 5,198 | 3.2% |
| mouse_scroll | 3,180 | 2.0% |
| browser_form_input | 1,805 | 1.1% |
| browser_navigation | 1,725 | 1.1% |
| (all others) | — | < 0.3% each |

### Layer distribution
| layer | % |
|---|---|
| L2 (OS-level) | 72.7% |
| L1 (screenshots) | 21.2% |
| L3 (browser) | 5.7% |
| SYSTEM | 0.3% |

**Implication:** L3 (browser-specific) events are rare (5.7%) relative to L2. Any approach relying heavily on browser-specific signals alone (e.g. `browser_click`, `browser_navigation`) will miss most of the timeline. General L2 signals (app_switch, and `context.active_browser_tab.url` which is populated even on non-L3 events) are more broadly usable.

### Field presence / reliability
| Field | % present |
|---|---|
| active_app | 99.7% |
| window_title | 99.6% |
| browser url (active_browser_tab.url) | 52.6% |
| extracted_text | 4.5% |

### text_input_complete reliability check
- 118 total `text_input_complete` events
- **118/118 (100%) missing content** — even worse than the spec's general warning suggested
- **Decision:** fully ignore this field; reconstruct text input from `keystroke`/`clipboard_change` events if ever needed.

---

## 3. Data quality issues found in `gt_manifest.json`

- Zero/negative duration executions: **0**
- Overlapping consecutive executions: **0**
- Duplicate start timestamps: **0**
- Executions spanning a chunk boundary (`continues_from_prev`/`continues_to_next`): **63 (3.1%)**

### Missing `end_ts` issue (found and resolved)
- **257/2009 executions (12.8%) have `end_ts = None`**
- Checked `continues_to_next` across the affected executions; almost all missing-end executions have `continues_to_next=False`, so chunk-boundary spanning does not explain the missing-end issue.
- Likely cause: incomplete start/end pairing in `gt.jsonl` generation — consistent with the spec's explicit warning that *"process_switched_out does not always pair up with every process_started."*
- **Decision:** left the raw ground truth in `loaders.py` untouched (does not mutate or hide the issue). Built a separate, explicit, opt-in imputation module (`src/exploration/gt_imputation.py`) that:
  - Fills a missing `end_ts` using the **next execution's `start_ts`** within the same session
  - Justified by the gap-analysis finding below (near-zero median gap between transitions)
  - Falls back to the session's own `end_ts` for a final execution with no "next" to borrow from; if that's also unavailable, leaves it `None` and marks `end_imputed=False` (does not falsely claim to have imputed something it didn't)
  - Flags every segment with an explicit `end_imputed` boolean so any consumer can isolate/report on imputed vs. raw segments
- **Verified:** re-ran with imputation and confirmed 257 imputed, 0 still missing, and no imputed `end_dt` fell before its `start_dt`.
- **Impact check:** re-ran gap analysis and per-process characteristics with imputation applied — core conclusions (near-zero transition gaps, per-process averages) did not meaningfully change; the fix mainly restored the 257 previously-silently-dropped executions to the stats rather than altering their shape.
- **Usage convention going forward:** `data_quality_checks()` intentionally uses **raw** (un-imputed) segments since that's the function meant to surface this exact issue. All other analyses (gap stats, per-process characteristics, boundary evidence) use **imputed** segments.

---

## 4. Gap analysis between consecutive true segments (imputed)
- n=1946 min=0.0s median=0.0s max=121.0s
- gaps <1s: 1847 (94.9%)
- gaps 1-5s: 53
- gaps 5-30s: 16
- gaps >30s: 30

**Finding:** the overwhelming majority (~95%) of process-to-process transitions happen with essentially **zero gap** — workers move from one process directly into the next almost instantly. Only a small minority of transitions (about 5%) involve any meaningful pause.

*(Note: since imputed end_ts is set equal to the next segment's start_ts, imputed segments contribute exactly 0-gap transitions by construction — the pre-imputation figure was already 94.1%, so this doesn't change the underlying conclusion.)*

---

## 5. Boundary vs. within-process event-level gap comparison (imputed)

| Metric | At boundary (ms) | Inside process (ms) |
|---|---|---|
| median | 56 | 34 |
| 75th pct | 133 | 89 |
| 90th pct | 919 | 876 |
| max | 144,624 | 983,925 |

- n(boundary) = 42,123 events, n(within) = 137,539 events
- **Conclusion:** gap size at the individual-event level shows only a modest difference between boundary and within-process points (median 56ms vs 34ms), and the 90th-percentile values are nearly identical (919 vs 876). The **maximum gap inside a process (983,925ms ≈ 16 min) is actually larger than the maximum gap at any boundary (144,624ms ≈ 2.4 min)**. Gap size alone is **not reliably discriminative** at the raw event level.

---

## 6. Boundary evidence table (the key Day 1 result)

Built by inspecting **20 TRUE boundaries** (2 per session across 10 sessions) and **10 CONTROL midpoints** (1 per session, taken from the longest segment in each session), checking a ±10s window around each point for: app switch, gap >5000ms, URL change, extracted-text change.

| Signal | Fires at TRUE boundary | Fires at CONTROL point | Separation |
|---|---|---|---|
| app_switch | 11/20 = **55%** | 1/10 = **10%** | +45 pp |
| url_change | 10/20 = **50%** | 0/10 = **0%** | +50 pp (cleanest) |
| text_change | 12/20 = **60%** | 1/10 = **10%** | +50 pp |
| large_gap (>5000ms) | 2/20 = **10%** | 8/10 = **80%** | **−70 pp (inverted!)** |

### Critical, non-obvious finding: gap size is INVERSELY correlated with boundaries

Large time gaps occur far more often **in the middle of a process** (80% of control points) than **at actual process transitions** (only 10% of true boundaries). This directly contradicts the naive assumption that "a pause means a task switch." It's consistent with Section 4's finding that transitions themselves are near-instant — the pauses that do happen are workers reading/waiting/thinking mid-task, not between tasks.

**Practical implication for Day 2:** a boundary detector must NOT treat large gaps as positive evidence of a boundary. If anything, a large gap should be treated as **mild negative evidence** (or excluded entirely from the positive-evidence score).

### app_switch caveat
`app_switch` events are very common overall (31.1% of all events, per Section 2), so a persistence/sustained-switch check (require the new app to hold for several subsequent events) is still necessary to avoid over-firing on trivial flickers (e.g., a quick alt-tab). Confirmed important since app_switch's raw frequency is much higher than its 55% true-boundary hit rate alone would suggest is "clean."

### text_change and sparse data
The boundary inspection suggests that windowed aggregation can make sparse `extracted_text` observations useful: `text_change` fired at 60% of inspected true boundaries versus 10% of controls. This is notable given `extracted_text` is present on only 4.5% of individual events per Section 2 — the ±10s window evidently accumulates enough sparse observations to be usable as a windowed signal, even though it would not work as a per-event feature.

---

## 7. Suspend/resume behavior (inspected via gt.jsonl)

Observed in `ses_20260630-121953-LAPTOP-R36BQBTE` and `ses_20260630-124826-CHAITANYA0BCF`:

- A `process_suspended` event (e.g., `B → H`) is followed some time later by a `process_resumed` event for the *same* process code (e.g., `process_resumed current=B`), rather than a fresh `process_started`.
- This means: **a resumed process is represented as a continuation of its original execution**, not a brand-new execution in the ground truth's intent — but critically, this "resume" event is still just one line among many `process_started`/`process_switched_out` transitions in the raw stream, and `gt_manifest.json`'s `executions[]` list still needs to be checked for whether resumed segments appear as one execution or two (not fully confirmed from raw `gt.jsonl` alone).
- Also noticed: `process_started` sometimes appears **twice in a row for the same process_code with no switch in between** (e.g., `G` started, then `G` started again 17s later) — this matches the spec's explicit warning that *"gt.jsonl sometimes emits the same process_started twice in a row."* This needs to be de-duplicated or handled carefully if parsing raw `gt.jsonl` directly, rather than relying on `gt_manifest.json`'s cleaner `executions[]` list, which is why we use `gt_manifest.json` as primary and only reference raw `gt.jsonl` for qualitative inspection.

**Decision for Day 2:** since a resumed process re-appears as a `process_resumed` event for the same code, not a new started process, the pragmatic choice for Day 2 v1 is to **treat interruption + resumption as two separate predicted segments** (not attempt to stitch them into one). This is a deliberate scope limitation, not an oversight — will document as a known gap in v1 accuracy.

---

## 8. Per-process characteristics (imputed, n=2009 executions across 15 processes)

| Code | Name | n | AvgDur(s) | AvgEvts | AvgSwitch | AvgClick | AvgKeys | #Variants |
|---|---|---|---|---|---|---|---|---|
| A | 住民税通知確認 | 159 | 32.4 | 80.8 | 0.9 | 5.7 | 21.0 | 2 |
| B | 給与備考・控除整備 | 126 | 41.3 | 68.0 | 0.4 | 5.7 | 17.7 | 2 |
| C | 育児・産休申請確認 | 161 | 50.6 | 80.8 | 1.8 | 5.6 | 17.2 | 1 |
| D | 社保・年金補正対応 | 114 | 48.4 | 71.9 | 2.0 | 5.6 | 11.5 | 1 |
| E | 入社照合・手当確認 | 111 | 31.7 | 83.1 | 1.2 | 5.9 | 22.4 | 1 |
| F | 請求書承認 | 169 | 34.9 | 84.1 | 0.9 | 5.7 | 21.3 | 2 |
| G | 経費精算承認 | 144 | 26.9 | 64.5 | 0.3 | 5.4 | 16.0 | 2 |
| H | 銀行勘定照合 | 147 | 31.2 | 82.3 | 0.8 | 5.6 | 23.1 | 1 |
| I | 予算差異分析 | 117 | 78.8 | 96.4 | 3.0 | 5.7 | 20.9 | 1 |
| J | 支払処理 | 102 | 38.4 | 80.9 | 1.1 | 5.7 | 21.3 | 1 |
| K | 受注処理 | 127 | 38.9 | 81.9 | 0.9 | 5.4 | 21.6 | 2 |
| L | 在庫調整 | 137 | 36.7 | 67.9 | 0.5 | 5.5 | 16.4 | 2 |
| M | 仕入先連絡 | 155 | 53.1 | 84.9 | 1.8 | 5.9 | 18.0 | 1 |
| N | 出荷追跡 | 129 | 49.1 | 79.8 | 2.0 | 5.8 | 13.1 | 1 |
| O | 返品処理 | 111 | 33.5 | 83.3 | 1.0 | 5.7 | 21.9 | 1 |

### Early observations for Step 2 (automation prioritization) — noted now while fresh
- **I (予算差異分析 / budget variance analysis)**: longest duration (78.8s), most events (96.4), most app switches (3.0) → likely most complex/branchy → probably a **weaker** automation candidate initially (high implementation risk)
- **G (経費精算承認 / expense approval)**: shortest duration (26.9s), fewest app switches (0.3), high frequency (144) → simple, fast, linear, frequent → likely a **strong** candidate
- Processes with `#Variants = 1` are more procedurally consistent than those with `#Variants = 2` — worth weighting into automation prioritization later, since fewer variants suggests fewer branches to handle

---

## 9. Final hypothesis for Day 2 (evidence-based signal ranking)

Ranked by exploratory separation in the inspected sample (TRUE-boundary rate minus CONTROL rate):

1. **url_change** — cleanest separation (+50pp, 0% false positive at controls)
2. **text_change** — strong separation (+50pp)
3. **app_switch** — strong separation (+45pp) but high raw frequency (31.1% of all events) → requires a sustained/persistence filter to avoid over-firing on flicker
4. **large_gap** — INVERTED signal (−70pp) → must be treated as counter-evidence (negative weight) or excluded, NOT used as positive evidence of a boundary

**Core design principle carried into Day 2:** combine signals as *weighted evidence*, not a single hard rule — a process can legitimately move Chrome → Excel → Chrome and still be one execution (per the original task brief's explicit warning), so no single signal should unilaterally declare a boundary.

---

## 10. Known difficulties / risks going into Day 2

- **Missing `end_ts` (12.8% of executions)** — handled via explicit, flagged imputation; downstream evaluation should be able to isolate imputed vs. raw segments if results look suspicious.
- **Gap size is actively misleading** — must not be used naively; this is a genuine risk if reusing generic "idle time = new task" heuristics from other domains (e.g. web analytics session splitting), which do not transfer here.
- **app_switch is very frequent** — needs careful persistence filtering, or it will cause heavy over-segmentation.
- **extracted_text is sparse per-event (4.5%)** but appears usable in aggregate over a time window per Section 6 — must not be used as a per-event feature directly.
- **Suspend/resume cycles exist** — v1 will not attempt to stitch these back together; this is a known, deliberate scope limitation that will likely show up as some "boundary_shift" or "over_segmented" errors in Day 2's evaluation for sessions containing suspensions.
- **Duplicate `process_started` events exist in raw `gt.jsonl`** — mitigated by using `gt_manifest.json`'s cleaner `executions[]` structure as the primary ground truth source rather than parsing `gt.jsonl` directly for segmentation evaluation.
- **Sample size caveat:** the boundary evidence table is based on a small exploratory sample — 20 true boundaries / 10 controls across 10 of 63 sessions. This is a reasonably informative first pass, but the signal-strength figures above should be treated as directional rather than statistically robust; Day 2/3 evaluation across all 63 sessions (via the full precision/recall/F1 metrics) provides the larger-sample check on whether these signals hold up.