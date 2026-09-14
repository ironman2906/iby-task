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
        metrics = evaluate_session(true_segments, predicted_segments)
        metrics["session_id"] = session_dir.name
        all_metrics.append(metrics)

    print(f"Evaluated {len(all_metrics)} sessions, skipped {skipped}\n{'='*80}")

    avg_iou = sum(m["avg_iou"] for m in all_metrics) / len(all_metrics)
    avg_match_rate = sum(m["match_rate_at_iou_0.5"] for m in all_metrics) / len(all_metrics)
    avg_precision = sum(m["boundary_precision"] for m in all_metrics) / len(all_metrics)
    avg_recall = sum(m["boundary_recall"] for m in all_metrics) / len(all_metrics)
    avg_f1 = sum(m["boundary_f1"] for m in all_metrics) / len(all_metrics)
    avg_over_seg = sum(m["over_segmentation_ratio"] for m in all_metrics) / len(all_metrics)

    print(f"--- AGGREGATE METRICS (v1, one-to-one matched, imputed GT) ---")
    print(f"Average IoU:                 {avg_iou:.3f}")
    print(f"Match rate (IoU >= 0.5):      {avg_match_rate:.3f}")
    print(f"Boundary precision (10s):     {avg_precision:.3f}")
    print(f"Boundary recall (10s):        {avg_recall:.3f}")
    print(f"Boundary F1:                  {avg_f1:.3f}")
    print(f"Over-segmentation ratio:      {avg_over_seg:.2f}x")

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