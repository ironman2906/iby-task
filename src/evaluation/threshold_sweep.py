import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "exploration"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import list_sessions, load_session_events, load_gt_manifest, extract_true_segments
from gt_imputation import impute_missing_end_ts
import boundary_detection as bd
from evaluator import evaluate_session

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"


def evaluate_with_threshold(sessions, threshold):
    metrics_list = []
    for session_dir in sessions:
        gt_manifest = load_gt_manifest(session_dir)
        if gt_manifest is None:
            continue
        true_segments = impute_missing_end_ts(extract_true_segments(gt_manifest))
        if not true_segments:
            continue
        events = load_session_events(session_dir)
        predicted = bd.run_segmentation(events, score_threshold=threshold)
        metrics_list.append(evaluate_session(true_segments, predicted))
    avg_f1 = sum(m["boundary_f1"] for m in metrics_list) / len(metrics_list)
    avg_over_seg = sum(m["over_segmentation_ratio"] for m in metrics_list) / len(metrics_list)
    avg_iou = sum(m["avg_iou"] for m in metrics_list) / len(metrics_list)
    return avg_f1, avg_over_seg, avg_iou


def main():
    sessions = list_sessions(DATA_A)[:20]  # subset for speed during sweep
    print(f"{'Threshold':10s} {'F1':8s} {'AvgIoU':8s} {'OverSeg':8s}")
    for threshold in [0.30, 0.40, 0.45, 0.50, 0.60, 0.70, 0.80, 0.90]:
        f1, over_seg, iou = evaluate_with_threshold(sessions, threshold)
        print(f"{threshold:<10.2f} {f1:<8.3f} {iou:<8.3f} {over_seg:<8.2f}")


if __name__ == "__main__":
    main()