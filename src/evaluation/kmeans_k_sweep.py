import sys
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "exploration"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import list_sessions, load_session_events, load_gt_manifest, extract_true_segments
from gt_imputation import impute_missing_end_ts
from boundary_detection import run_segmentation
from clustering_kmeans_experiment import build_feature_matrix
from evaluator import match_one_to_one

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"


def evaluate_k(all_segments, session_boundaries, X, k, random_state=42):
    km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    cluster_ids = km.fit_predict(X)

    for seg, cid in zip(all_segments, cluster_ids):
        seg["label"] = f"cluster_{cid}"

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
    for label, code_counts in label_to_true_codes.items():
        most_common_count = code_counts.most_common(1)[0][1]
        correct += most_common_count
        total += sum(code_counts.values())
    purity = correct / total if total else 0

    sil = silhouette_score(X, cluster_ids) if k > 1 and k < len(X) else float("nan")

    return purity, len(label_to_true_codes), sil, total


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

    X, _ = build_feature_matrix(all_segments)

    print(f"{'k':4s} {'purity':8s} {'n_clusters':11s} {'silhouette':11s} {'matched_n':10s}")
    for k in [10, 12, 15, 18]:
        purity, n_clusters, sil, matched_n = evaluate_k(all_segments, session_boundaries, X, k)
        print(f"{k:<4d} {purity:<8.3f} {n_clusters:<11d} {sil:<11.3f} {matched_n:<10d}")


if __name__ == "__main__":
    main()