## 1. Dataset B Structural Sanity Check

Dataset B contains 15 sessions and 20,477 events.

### Coverage comparison

| Metric | Dataset A | Dataset B |
|---|---:|---:|
| Sessions | 63 | 15 |
| Total events | 162,768 | 20,477 |
| URL present | 52.6% | 46.5% |
| extracted_text present | 4.5% | 4.6% |

URL coverage in Dataset B is somewhat lower than Dataset A (46.5% vs 52.6%), but extracted-text coverage is almost identical (4.6% vs 4.5%). The overall coverage is therefore sufficiently comparable to use the locked Day 2 v2 segmentation configuration as the starting point.

### Dataset B event/layer structure

The most frequent event types were:
- `screenshot_smart`: 4,759 (23.2%)
- `keystroke`: 4,678 (22.8%)
- `mouse_click`: 2,133 (10.4%)
- `browser_click`: 1,914 (9.3%)
- `mouse_scroll`: 1,724 (8.4%)
- `app_switch`: 1,654 (8.1%)

Layer distribution:
- L2: 12,831 (62.7%)
- L1: 4,759 (23.2%)
- L3: 2,764 (13.5%)
- SYSTEM: 123 (0.6%)

The most-used applications were Microsoft Edge, Microsoft Word, and Microsoft Excel.

### Decision

No segmentation weights were changed based on this sanity check. Dataset B has no ground-truth boundary labels for independent weight tuning, so the Day 2 v2 configuration is retained unchanged:

- `url_change = 0.50`
- `text_change = 0.50`
- `app_switch = 0.45`
- `large_gap = -0.35`
- `TEXT_SIMILARITY_THRESHOLD = 0.85`

The lower URL coverage in Dataset B is recorded as a limitation/risk, but it is not sufficient by itself to justify changing the locked configuration.

## 2. Dataset B Segmentation

The locked Day 2 v2 segmenter was applied unchanged to all 15 Dataset B sessions.

- Total events: 20,477
- Total predicted segments: 589
- Sessions processed: 15/15
- Sessions with missing events: 0
- Average segments/session: 39.27
- Median segments/session: 36
- Minimum segments/session: 29
- Maximum segments/session: 62

The observed total of 589 segments is above the initial rough sanity range of 150–400. However, the per-session distribution is relatively consistent (29–62 segments/session), with an average of 39.27 and median of 36 segments/session. No session showed an event-loading failure.

No segmentation weights or thresholds were changed in response to this result. The 589-segment count is treated as an observation to be further assessed during clustering and manual inspection rather than as sufficient evidence for arbitrary retuning of the locked v2 segmenter.
### Extension lifecycle check

Dataset B explicitly records `extension_connected` and
`extension_disconnected` events. Fourteen of the 15 sessions contain
three connect events near session start and three disconnect events near
session end. The repeated events occur within milliseconds of each other,
suggesting duplicate/parallel lifecycle records rather than separate
connection cycles.

No session showed an observed `extension_disconnected` event followed by
a continued session without a subsequent reconnect. One session
(`ses_20260701-192455-NEELA9BAF`) contained no extension lifecycle events.

Therefore, this check did not identify an extension-disconnection
pattern requiring a change to the locked v2 segmentation configuration.
### Segment duration sanity check

The 589 predicted segments were further checked for duration distribution.

- Median duration: 13.12 s
- Mean duration: 16.43 s
- Segments under 10 s: 35.3%
- Segments under 5 s: 9.7%

The presence of short segments indicates some fragmentation, consistent
with the residual over-segmentation limitation observed during Day 2
evaluation on Dataset A. However, only 9.7% of segments are shorter than
5 seconds, and there was no evidence of an event-loading failure across
the 15 Dataset B sessions.

The observed 589 segments therefore remain a sanity-check deviation from
the initial rough estimate of 150–400 rather than evidence of a specific
Dataset B failure. The locked v2 segmentation configuration was retained
without further threshold or weight tuning.

### Step 2 limitations

Dataset B produced more predicted segments than the initial rough
150–400 estimate. The duration distribution and per-session counts do
not indicate an event-loading failure, but they do show some short-segment
fragmentation. This is consistent with the residual over-segmentation
already observed during Day 2 evaluation on Dataset A.

Because Dataset B has no ground-truth segment boundaries, no additional
threshold or weight tuning was performed on Dataset B. The locked v2
segmenter is retained for the clustering and labeling stages.

## Step 3: Clustering-Based Segment Labeling

### 3.1 Motivation

The Day 2 `labeling.py` implementation uses a naive dominant-application labeler. This was sufficient as a smoke test but does not provide semantic task labels when multiple tasks occur within the same application.

For Day 3, a clustering-based labeler was therefore investigated using the locked Day 2 v2 segmentation output.

The segment representation combines:

- window titles
- extracted text
- URLs
- segment duration
- number of events
- number of unique applications

The text features use character-level TF-IDF:

- `analyzer="char_wb"`
- `ngram_range=(2,4)`
- `max_features=300`

Numeric features are standardized and given a weight of `0.3` before being concatenated with the TF-IDF representation.

---

### 3.2 Initial DBSCAN Approach

The initial clustering implementation used DBSCAN with cosine distance.

Initial configuration:

- `eps = 0.6`
- `min_samples = 2`

The clustering approach was first validated on the first 20 Dataset A sessions using the locked Day 2 v2 segmenter.

The validation compared cluster labels against the ground-truth `process_code` using one-to-one segment matching.

#### Initial DBSCAN result

| Configuration | Purity | Labels represented |
|---|---:|---:|
| DBSCAN, eps=0.6, min_samples=2 | 0.097 | 1 |

All 15 process codes were mixed into a single cluster.

This indicated that the initial DBSCAN configuration was not separating the task/process structure adequately.

---

### 3.3 DBSCAN Feature-Space Diagnosis

Because DBSCAN produced one large cluster, the feature space was inspected before changing the segmentation algorithm.

Using the same feature construction as the clustering implementation:

- Total segments: `585`
- TF-IDF matrix: `(585, 300)`
- Numeric features: `(585, 3)`
- Combined feature matrix: `(585, 303)`

The TF-IDF vectors were non-degenerate:

- minimum norm: `1.0`
- median norm: `1.0`
- maximum norm: `1.0`
- near-zero vectors: `0/585`

Normalized numeric features also had non-zero variation:

- duration: min `-0.76`, max `11.87`
- event count: min `-1.48`, max `5.56`
- unique applications: min `-0.72`, max `4.92`

The combined feature-space cosine-distance distribution was:

| Percentile | Cosine distance |
|---|---:|
| Minimum | 0.0000 |
| 5th | 0.1119 |
| 25th | 0.4332 |
| 50th | 0.6701 |
| 75th | 0.8983 |
| Maximum | 1.3788 |

The 2-nearest-neighbour distance distribution had:

| Percentile | k-distance |
|---|---:|
| 10th | 0.0003 |
| 25th | 0.0022 |
| 50th | 0.0078 |
| 75th | 0.0327 |
| 90th | 0.0910 |
| 95th | 0.1461 |
| 99th | 0.2400 |

The largest observed k-distances extended to approximately `0.38`.

The median distance between segments with the same dominant application was approximately `0.514`, compared with `0.894` for segments with different dominant applications.

### Interpretation

The feature representation was not degenerate: the TF-IDF vectors contained variation and the numeric features also varied.

There was also evidence of application-level structure in the feature space.

However, the initial DBSCAN failure could not be attributed conclusively to one specific feature or to boilerplate text. The feature-space diagnosis therefore did not justify changing the feature representation solely on that hypothesis.

---

### 3.4 DBSCAN Parameter Checks

A small parameter check was performed without changing the segmentation algorithm.

#### `eps = 0.4`

Result remained effectively unchanged:

- Purity: `0.097`
- One cluster containing all 15 process codes.

#### `eps = 0.5`

Result remained effectively unchanged:

- Purity: `0.097`
- One cluster containing all 15 process codes.

#### `eps = 0.3, min_samples = 2`

Result:

- Purity: `0.097`
- One cluster.

#### `eps = 0.3, min_samples = 5`

Result:

- Purity: `0.098`
- Two labels represented.
- One large mixed cluster.
- One `unclustered_Microsoft Excel` group.

The small DBSCAN parameter sweep did not produce useful process separation.

### Decision

DBSCAN was not selected for the Dataset B labeling pipeline.

Further DBSCAN tuning was stopped to avoid excessive parameter searching without evidence that it would produce useful semantic separation.

---

## 3.5 K-Means Alternative

Since the Dataset A validation contains approximately 15 distinct process codes, a fixed-cluster-count K-Means experiment was tested as an alternative.

The K-Means implementation uses the **same feature construction** as the DBSCAN experiment:

- character-level TF-IDF over segment text
- window titles
- extracted text
- URLs
- normalized duration
- normalized event count
- normalized unique-app count
- numeric feature weight of `0.3`

The only change was the clustering algorithm.

K-Means was tested with:

```text
random_state = 42
n_init = 10
```

---

### 3.6 K-Means Validation

K-Means was evaluated on the same first 20 Dataset A sessions using the locked Day 2 v2 segmenter.

A small cluster-count sweep was performed.

| k | Purity | Number of represented clusters | Silhouette |
|---:|---:|---:|---:|
| 10 | 0.293 | 9 | 0.307 |
| 12 | 0.302 | 11 | 0.276 |
| 15 | **0.372** | 14 | 0.245 |
| 18 | 0.367 | 17 | 0.241 |

All configurations had `580` matched segments for the purity calculation.

### Selection

`k = 15` was selected for the Dataset B pipeline because:

1. Dataset A contains 15 documented process codes.
2. `k=15` produced the highest measured purity among the tested K-Means configurations.
3. The result was close to the `k=18` result rather than showing a sharp fragmentation effect.
4. The silhouette score remained positive, providing supporting evidence that the resulting partition was not completely structureless.

The K-Means result is not treated as highly accurate semantic labeling. The measured purity of `0.372` indicates substantial mixing between process codes.

Therefore, the clustering labels are treated as **candidate task-group labels for downstream analysis**, with manual inspection required before drawing conclusions from them.

---

### 3.7 K-Means Cluster Composition

For `k=15`, 14 cluster labels were represented among the matched segments.

The validation showed that several clusters contained segments from multiple ground-truth process codes.

Examples of mixed cluster composition included:

- `cluster_0`: H, A, C, I, N, D, E, O, J, F, M, B, L, K
- `cluster_1`: O, L, M, K, D, N
- `cluster_10`: M, K, L, N, O, A, H
- `cluster_11`: J, G, H, F
- `cluster_12`: B, E, C, D, A, J
- `cluster_13`: M, C, E, D, A, B, I, K, F
- `cluster_9`: N, C, D, K, H, J, F, L, G

Some smaller clusters were more concentrated, but overall cluster purity remained limited.

This reinforces the decision that the cluster labels should not automatically be interpreted as ground-truth process identities.

---

## 3.8 Day 3 Clustering Decision

The clustering experiments resulted in the following decision:

**Selected labeling method for Dataset B:**

- Day 2 v2 segmentation remains locked.
- Use the K-Means implementation rather than the initial DBSCAN implementation.
- Use `k=15`.
- Keep the existing TF-IDF + numeric feature representation.
- Do not further tune the segmentation weights or threshold.
- Do not continue broad clustering parameter searches.
- Manually inspect representative clusters after Dataset B labeling.

The DBSCAN implementation remains in the repository as an experiment/diagnostic, but it is **not** used to produce the final Dataset B `segments.jsonl`.

The selected K-Means method is considered a practical clustering baseline rather than a validated semantic classifier. Its limitations will be carried into the downstream analysis.

### 3.9 Manual Cluster Inspection on Dataset B

Because Dataset B has no ground-truth process labels, representative clusters were manually inspected using raw events, active applications, window titles, URLs, and extracted text.

The five largest clusters were inspected: `cluster_6`, `cluster_2`, `cluster_7`, `cluster_8`, and `cluster_9`.

#### cluster_6

This cluster contains meaningful HR/payroll activity in the first two samples. Both samples use Microsoft Edge, the HR/payroll system, and the `/payroll-items` URL. However, the third sample contains finance/accounting activity and purchase-order management.

**Assessment:** Mixed cluster. Some contextual similarity exists, but it does not consistently represent one business process.

#### cluster_2

The first two samples are relatively coherent around contract/document processing. Both use Microsoft Word and contain the same contract-related extracted instruction. The third sample is an extremely short transitional segment (~0.1 seconds) with no extracted text.

**Assessment:** Relatively coherent, with a small transitional segment included.

#### cluster_7

The first sample contains PowerShell, browser setup/development-mode activity, and multiple local application URLs. The second and third samples instead contain finance/accounting and invoice-related activity.

**Assessment:** Mixed/suspicious cluster. The grouping does not consistently correspond to one business process.

#### cluster_8

All three inspected samples use Microsoft Edge and the HR system with the same `/social-insurance` URL. The extracted text refers to welfare/social-insurance applications, including maternity leave, housing allowance, and childcare leave.

**Assessment:** Strong contextual coherence. The cluster appears to capture a broader HR/welfare workflow, although the specific requests differ.

#### cluster_9

The first sample contains finance/accounting purchase-order activity. The second contains browser recovery/navigation activity, while the third combines Excel budget analysis with the finance system.

**Assessment:** Mixed cluster. There is broad finance-related context, but the specific activities differ substantially.

### Manual Inspection Conclusion

Manual inspection confirms that the K-Means labels provide useful candidate groupings but do not reliably represent a single business process per cluster.

Some clusters, particularly `cluster_8` and `cluster_2`, show meaningful contextual coherence. Other large clusters contain visibly mixed activities.

Therefore, the Dataset B cluster labels are treated as **candidate task-group labels rather than validated semantic process labels**. Downstream aggregation should preserve this limitation, and individual clusters should not automatically be interpreted as ground-truth business processes.