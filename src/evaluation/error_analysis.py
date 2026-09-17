import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "exploration"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import load_session_events, load_gt_manifest, extract_true_segments
from gt_imputation import impute_missing_end_ts
from boundary_detection import run_segmentation
from evaluator import evaluate_session

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"


def inspect_session(session_name):
    session_dir = DATA_A / session_name
    gt_manifest = load_gt_manifest(session_dir)
    true_segments = impute_missing_end_ts(extract_true_segments(gt_manifest))
    events = load_session_events(session_dir)
    predicted_segments = run_segmentation(events)

    metrics = evaluate_session(true_segments, predicted_segments)

    print(f"\nSession: {session_name}")
    print(f"True: {len(true_segments)}  Predicted: {len(predicted_segments)}  F1: {metrics['boundary_f1']:.3f}")
    print(f"{'-'*90}")

    for true_seg, pred_seg, iou in metrics["matches"]:
        status = "OK  " if iou >= 0.5 else "POOR" if iou > 0 else "MISS"
        pred_desc = f"{pred_seg['start_iso']} -> {pred_seg['end_iso']}" if pred_seg else "NO MATCH"
        imputed_flag = " [imputed_end]" if true_seg.get("end_imputed") else ""
        print(f"[{status}] iou={iou:.2f}  TRUE=[{true_seg['process_code']}] "
              f"{true_seg['start']} -> {true_seg['end']}{imputed_flag}  | PRED={pred_desc}")


if __name__ == "__main__":
    # paste in real session names from day2_v1_metrics.txt's "WORST 5" list
    worst_sessions = [
    "ses_20260701-152030-CHAITANYA0BCF",
]
    for s in worst_sessions:
        inspect_session(s)