"""
evaluator.py
One-to-one matching (greedy, highest IoU first) between true and predicted
segments — prevents one predicted segment from claiming credit for multiple
true segments. Uses IMPUTED ground truth (via gt_imputation.py) so all 2009
executions have valid durations, not just the 1752 with original end_ts.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import parse_iso


def seg_to_seconds(seg, start_key="start_iso", end_key="end_iso"):
    start_dt = parse_iso(seg[start_key])
    end_dt = parse_iso(seg[end_key])
    return start_dt.timestamp(), end_dt.timestamp() + 0.001  # epsilon for zero-duration segs


def overlap_seconds(s1, e1, s2, e2):
    return max(0.0, min(e1, e2) - max(s1, s2))


def compute_iou(s1, e1, s2, e2):
    overlap = overlap_seconds(s1, e1, s2, e2)
    union = (e1 - s1) + (e2 - s2) - overlap
    return overlap / union if union > 0 else 0.0


def match_one_to_one(true_segments, predicted_segments):
    """
    true_segments here are IMPUTED (have valid start_dt/end_dt for all).
    Greedy one-to-one: sort all (true,pred) pairs by IoU desc, assign,
    each segment used at most once.
    """
    pred_ranges = [seg_to_seconds(p) for p in predicted_segments]
    true_ranges = [(t["start_dt"].timestamp(), t["end_dt"].timestamp() + 0.001) for t in true_segments]

    candidates = []
    for ti, (ts, te) in enumerate(true_ranges):
        for pi, (ps, pe) in enumerate(pred_ranges):
            iou = compute_iou(ts, te, ps, pe)
            if iou > 0:
                candidates.append((iou, ti, pi))
    candidates.sort(key=lambda c: c[0], reverse=True)

    used_true, used_pred = set(), set()
    match_map = {}
    for iou, ti, pi in candidates:
        if ti in used_true or pi in used_pred:
            continue
        match_map[ti] = (pi, iou)
        used_true.add(ti)
        used_pred.add(pi)

    results = []
    for ti, t in enumerate(true_segments):
        if ti in match_map:
            pi, iou = match_map[ti]
            results.append((t, predicted_segments[pi], iou))
        else:
            results.append((t, None, 0.0))
    return results, used_pred


def boundary_precision_recall_f1(true_segments, predicted_segments, tolerance_s=10):
    true_boundaries = [t["start_dt"].timestamp() for t in true_segments]
    pred_boundaries = [parse_iso(p["start_iso"]).timestamp() for p in predicted_segments]

    matched_true = sum(1 for tb in true_boundaries
                        if any(abs(tb - pb) <= tolerance_s for pb in pred_boundaries))
    matched_pred = sum(1 for pb in pred_boundaries
                        if any(abs(tb - pb) <= tolerance_s for tb in true_boundaries))

    recall = matched_true / len(true_boundaries) if true_boundaries else 0.0
    precision = matched_pred / len(pred_boundaries) if pred_boundaries else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def classify_error_type(true_seg, matched_pred, iou):
    if matched_pred is None:
        return "missed"
    if iou >= 0.5:
        return "good"
    true_dur = (true_seg["end_dt"] - true_seg["start_dt"]).total_seconds()
    pred_dur = (parse_iso(matched_pred["end_iso"]) - parse_iso(matched_pred["start_iso"])).total_seconds()
    if pred_dur < true_dur * 0.6:
        return "over_segmented"
    elif pred_dur > true_dur * 1.6:
        return "under_segmented"
    return "boundary_shift"


def evaluate_session(true_segments, predicted_segments, iou_threshold=0.5, tolerance_s=10):
    """
    true_segments: pass IMPUTED segments here (see run_full_evaluation.py).
    """
    matches, used_pred = match_one_to_one(true_segments, predicted_segments)

    ious = [m[2] for m in matches]
    avg_iou = sum(ious) / len(ious) if ious else 0.0
    match_rate = sum(1 for iou in ious if iou >= iou_threshold) / len(true_segments) if true_segments else 0.0

    precision, recall, f1 = boundary_precision_recall_f1(true_segments, predicted_segments, tolerance_s)

    from collections import Counter
    error_types = [classify_error_type(t, p, iou) for t, p, iou in matches]
    error_type_counts = Counter(error_types)

    over_seg_ratio = len(predicted_segments) / len(true_segments) if true_segments else 0.0

    return {
        "n_true_segments": len(true_segments),
        "n_predicted_segments": len(predicted_segments),
        "n_predicted_matched": len(used_pred),
        "avg_iou": avg_iou,
        "match_rate_at_iou_0.5": match_rate,
        "boundary_precision": precision,
        "boundary_recall": recall,
        "boundary_f1": f1,
        "over_segmentation_ratio": over_seg_ratio,
        "error_type_counts": dict(error_type_counts),
        "matches": matches,
    }