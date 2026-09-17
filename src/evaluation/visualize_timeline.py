"""
visualize_timeline.py
Simple text-based timeline comparing TRUE vs PREDICTED segments for a
session — makes over/under-segmentation visually obvious.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "exploration"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import load_session_events, load_gt_manifest, extract_true_segments, parse_iso
from gt_imputation import impute_missing_end_ts
from boundary_detection import run_segmentation

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"
WIDTH = 100


def render_bar(intervals, session_start_ts, session_end_ts):
    total_span = session_end_ts - session_start_ts
    if total_span <= 0:
        return "." * WIDTH
    line = ["."] * WIDTH
    for (s, e) in intervals:
        start_pos = int((s - session_start_ts) / total_span * WIDTH)
        end_pos = int((e - session_start_ts) / total_span * WIDTH)
        start_pos, end_pos = max(0, start_pos), min(WIDTH - 1, max(start_pos, end_pos))
        for i in range(start_pos, end_pos + 1):
            line[i] = "="
    return "".join(line)


def visualize_session(session_name):
    session_dir = DATA_A / session_name
    gt_manifest = load_gt_manifest(session_dir)
    true_segments = impute_missing_end_ts(extract_true_segments(gt_manifest))
    events = load_session_events(session_dir)
    predicted_segments = run_segmentation(events)

    session_start_ts = events[0]["timestamp_ms"] / 1000
    session_end_ts = events[-1]["timestamp_ms"] / 1000

    true_intervals = [(t["start_dt"].timestamp(), t["end_dt"].timestamp()) for t in true_segments]
    pred_intervals = [(parse_iso(p["start_iso"]).timestamp(), parse_iso(p["end_iso"]).timestamp())
                       for p in predicted_segments]

    print(f"\n{'='*100}\nSession: {session_name}\n{'='*100}")
    print(f"TRUE: {render_bar(true_intervals, session_start_ts, session_end_ts)}")
    print(f"PRED: {render_bar(pred_intervals, session_start_ts, session_end_ts)}")
    print(f"(n_true={len(true_segments)}, n_pred={len(predicted_segments)})")


if __name__ == "__main__":
    sessions_to_check = [
        "ses_20260701-054901-LAPTOP-R36BQBTE",   # previously over-segmented, now fixed
        "ses_20260701-152030-CHAITANYA0BCF",      # coverage anomaly — confirm visually
        "ses_20260630-121953-LAPTOP-R36BQBTE",    # known session from Day 1
    ]
    for s in sessions_to_check:
        visualize_session(s)