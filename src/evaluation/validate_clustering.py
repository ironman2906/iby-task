import sys
from pathlib import Path
from collections import defaultdict, Counter

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "exploration"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import list_sessions, load_session_events, load_gt_manifest, extract_true_segments
from gt_imputation import impute_missing_end_ts
from boundary_detection import run_segmentation
from clustering_labeling import cluster_segments
from evaluator import match_one_to_one

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"


def main():
    sessions = list_sessions(DATA_A)[:20]

    all_segments = []
    session_boundaries = []
    for session_dir in sessions:
        events = load_session_events(session_dir)
        if not events:
            continue
        segments = run_segmentation(events)
        start_idx = len(all_segments)
        all_segments.extend(segments)
        session_boundaries.append((session_dir, start_idx, len(all_segments)))

    all_segments = cluster_segments(all_segments, eps=0.3 ,min_samples=5)
    
    label_to_true_codes = defaultdict(Counter)
    for session_dir, start_idx, end_idx in session_boundaries:
        gt_manifest = load_gt_manifest(session_dir)
        true_segments = impute_missing_end_ts(extract_true_segments(gt_manifest))
        predicted_segments = all_segments[start_idx:end_idx]

        matches, _ = match_one_to_one(true_segments, predicted_segments)
        for true_seg, pred_seg, iou in matches:
            if pred_seg and iou > 0.3:
                label_to_true_codes[pred_seg["label"]][true_seg["process_code"]] += 1

    total, correct = 0, 0
    print("Cluster label -> true process_code distribution:\n")
    for label, code_counts in sorted(label_to_true_codes.items()):
        print(f"'{label}': {dict(code_counts)}")
        most_common_count = code_counts.most_common(1)[0][1]
        correct += most_common_count
        total += sum(code_counts.values())

    purity = correct / total if total else 0
    print(f"\nOverall cluster purity: {purity:.3f}  (n={total} matched segments)")
    print(f"Number of distinct labels produced: {len(label_to_true_codes)}")
    print(f"(True number of distinct processes in these sessions: up to 15)")


if __name__ == "__main__":
    main()