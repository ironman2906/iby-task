import sys
from pathlib import Path
from collections import Counter

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "exploration"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import list_sessions, load_session_events, load_gt_manifest, extract_true_segments
from gt_imputation import impute_missing_end_ts
from boundary_detection import run_segmentation
from evaluator import evaluate_session

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"
COVERAGE_GAP_THRESHOLD_S = 60

def check_coverage(events, true_segments):
    """Returns (gap_seconds, is_flagged). Does not skip or modify anything."""
    if not events or not true_segments:
        return None, False
    event_end = events[-1]["timestamp_ms"] / 1000
    gt_end = true_segments[-1]["end_dt"].timestamp()
    gap = gt_end - event_end
    return gap, gap > COVERAGE_GAP_THRESHOLD_S


def main():
    sessions = list_sessions(DATA_A)
    all_metrics = []
    skipped = 0

    for session_dir in sessions:
        gt_manifest = load_gt_manifest(session_dir)
        if gt_manifest is None:
            skipped += 1
            continue

        raw_segments = extract_true_segments(gt_manifest)
        true_segments = impute_missing_end_ts(raw_segments)   # <-- IMPUTED, per Day 1 decision
        if not true_segments:
            skipped += 1
            continue

        events = load_session_events(session_dir)
        if not events:
            skipped += 1
            continue
        
        predicted_segments = run_segmentation(events)

        gap, is_flagged = check_coverage(events, true_segments)

        metrics = evaluate_session(true_segments, predicted_segments)
        metrics["session_id"] = session_dir.name
        metrics["coverage_gap_s"] = gap
        metrics["coverage_flagged"] = is_flagged

        all_metrics.append(metrics)
        

    print(f"Evaluated {len(all_metrics)} sessions, skipped {skipped}\n{'='*80}")
    flagged = [m for m in all_metrics if m["coverage_flagged"]]
    coverage_valid = [m for m in all_metrics if not m["coverage_flagged"]]

    print(f"\n--- COVERAGE CHECK (threshold={COVERAGE_GAP_THRESHOLD_S}s) ---")
    print(f"Sessions flagged: {len(flagged)}")
    for m in flagged:
        print(f"  {m['session_id']} (gap={m['coverage_gap_s']:.1f}s)")

    def print_aggregate(metrics_list, label):
        print(f"\n--- {label} ({len(metrics_list)} sessions) ---")

        avg_iou = sum(m["avg_iou"] for m in metrics_list) / len(metrics_list)
        avg_match_rate = sum(m["match_rate_at_iou_0.5"] for m in metrics_list) / len(metrics_list)
        avg_precision = sum(m["boundary_precision"] for m in metrics_list) / len(metrics_list)
        avg_recall = sum(m["boundary_recall"] for m in metrics_list) / len(metrics_list)
        avg_f1 = sum(m["boundary_f1"] for m in metrics_list) / len(metrics_list)
        avg_over_seg = sum(m["over_segmentation_ratio"] for m in metrics_list) / len(metrics_list)

        print(f"Average IoU:                 {avg_iou:.3f}")
        print(f"Match rate (IoU >= 0.5):      {avg_match_rate:.3f}")
        print(f"Boundary precision (10s):     {avg_precision:.3f}")
        print(f"Boundary recall (10s):        {avg_recall:.3f}")
        print(f"Boundary F1:                  {avg_f1:.3f}")
        print(f"Over-segmentation ratio:      {avg_over_seg:.2f}x")

    print_aggregate(all_metrics, "HEADLINE METRICS, ORIGINAL")
    print_aggregate(coverage_valid, "COVERAGE-VALID METRICS")

    total_error_types = Counter()
    for m in all_metrics:
        total_error_types.update(m["error_type_counts"])
    total_segs = sum(total_error_types.values())
    print(f"\n--- ERROR TYPE BREAKDOWN ---")
    for etype, count in total_error_types.most_common():
        print(f"  {etype:18s} {count:5d}  ({100*count/total_segs:.1f}%)")

    worst = sorted(all_metrics, key=lambda m: m["avg_iou"])[:5]
    print(f"\n--- WORST 5 SESSIONS ---")
    for m in worst:
        print(f"  {m['session_id']}: avg_iou={m['avg_iou']:.3f}  f1={m['boundary_f1']:.3f}  "
              f"true={m['n_true_segments']}  pred={m['n_predicted_segments']}  "
              f"errors={m['error_type_counts']}")

    return all_metrics


if __name__ == "__main__":
    main()