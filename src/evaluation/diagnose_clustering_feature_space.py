"""
diagnose_clustering_feature_space.py
DIAGNOSTIC ONLY. Inspects the ACTUAL feature matrix that DBSCAN receives
inside cluster_segments (text TF-IDF + normalized numeric features,
concatenated exactly as clustering_labeling.py does it) — not just the
text portion in isolation. No changes to boundary_detection.py, v2
weights/threshold, or clustering_labeling.py itself.
"""

import sys
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_distances
from sklearn.neighbors import NearestNeighbors
from collections import Counter

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "exploration"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import list_sessions, load_session_events, get_active_app_name
from boundary_detection import run_segmentation
from clustering_labeling import segment_text_blob, segment_numeric_features

DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"


def build_matrix_exactly_like_cluster_segments(segments):
    """Replicates cluster_segments's matrix-building EXACTLY, for inspection only."""
    blobs = [segment_text_blob(s) for s in segments]
    numeric = [segment_numeric_features(s) for s in segments]

    vectorizer = TfidfVectorizer(max_features=300, analyzer="char_wb", ngram_range=(2, 4))
    non_empty_blobs = [b if b.strip() else " " for b in blobs]
    X_text = vectorizer.fit_transform(non_empty_blobs).toarray()

    durations = np.array([n["duration_s"] for n in numeric]).reshape(-1, 1)
    n_events = np.array([n["n_events"] for n in numeric]).reshape(-1, 1)
    unique_apps = np.array([n["unique_apps"] for n in numeric]).reshape(-1, 1)

    def normalize(col):
        std = col.std()
        return (col - col.mean()) / std if std > 0 else col * 0

    numeric_matrix = np.hstack([normalize(durations), normalize(n_events), normalize(unique_apps)])
    X = np.hstack([X_text, numeric_matrix * 0.3])

    return X, X_text, numeric_matrix, vectorizer, blobs, numeric


def main():
    sessions = list_sessions(DATA_A)[:10]
    all_segments = []
    for session_dir in sessions:
        events = load_session_events(session_dir)
        if not events:
            continue
        all_segments.extend(run_segmentation(events))

    X, X_text, numeric_matrix, vectorizer, blobs, numeric = \
        build_matrix_exactly_like_cluster_segments(all_segments)

    print(f"Total segments: {len(all_segments)}")
    print(f"Text feature matrix shape: {X_text.shape}")
    print(f"Numeric feature matrix shape: {numeric_matrix.shape}")
    print(f"Combined matrix shape: {X.shape}")

    # 1. Check if text vectors themselves are degenerate (all near-identical, or all-zero)
    text_norms = np.linalg.norm(X_text, axis=1)
    print(f"\n--- Text vector norms (before combining with numeric) ---")
    print(f"  min={text_norms.min():.4f}  median={np.median(text_norms):.4f}  max={text_norms.max():.4f}")
    print(f"  Segments with near-zero text vector (empty/boilerplate-only after TF-IDF): "
          f"{(text_norms < 0.01).sum()} / {len(text_norms)}")

    # 2. Check numeric feature spread
    print(f"\n--- Numeric feature (normalized) stats ---")
    print(f"  duration: min={numeric_matrix[:,0].min():.2f} max={numeric_matrix[:,0].max():.2f} std={numeric_matrix[:,0].std():.2f}")
    print(f"  n_events: min={numeric_matrix[:,1].min():.2f} max={numeric_matrix[:,1].max():.2f} std={numeric_matrix[:,1].std():.2f}")
    print(f"  unique_apps: min={numeric_matrix[:,2].min():.2f} max={numeric_matrix[:,2].max():.2f} std={numeric_matrix[:,2].std():.2f}")

    # 3. Pairwise distance distribution on the ACTUAL combined matrix
    dist_matrix = cosine_distances(X)
    n = dist_matrix.shape[0]
    upper_tri = dist_matrix[np.triu_indices(n, k=1)]
    print(f"\n--- Pairwise cosine distance on COMBINED matrix (n={len(upper_tri)} pairs) ---")
    print(f"  min={upper_tri.min():.4f}  5th={np.percentile(upper_tri,5):.4f}  "
          f"25th={np.percentile(upper_tri,25):.4f}  median={np.percentile(upper_tri,50):.4f}  "
          f"75th={np.percentile(upper_tri,75):.4f}  max={upper_tri.max():.4f}")

    # 4. k-distance plot data for principled eps selection (standard DBSCAN method)
    min_samples = 2
    nbrs = NearestNeighbors(n_neighbors=min_samples, metric="cosine").fit(X)
    distances, _ = nbrs.kneighbors(X)
    kth_distances = np.sort(distances[:, -1])  # distance to k-th nearest neighbor, sorted ascending
    print(f"\n--- k-distance (k={min_samples}) plot data, for eps elbow selection ---")
    for pct in [10, 25, 50, 75, 90, 95, 99]:
        idx = int(len(kth_distances) * pct / 100)
        print(f"  {pct}th percentile of sorted k-distances: {kth_distances[min(idx, len(kth_distances)-1)]:.4f}")
    print("\n--- Largest k-distances ---")
    for value in kth_distances[-30:]:
        print(f"  {value:.4f}")
    print(f"  (Look for the 'elbow' -- the point where k-distance sharply increases -- "
          f"that value is a principled eps candidate, not an arbitrary percentile choice)")

    # 5. Top n-grams by corpus-wide TF-IDF weight (potential boilerplate check, evidence not assumption)
    sums = X_text.sum(axis=0)
    feature_names = vectorizer.get_feature_names_out()
    top_idx = np.argsort(sums)[::-1][:20]
    print(f"\n--- Top 20 highest-weight n-grams (candidates for boilerplate, NOT yet confirmed) ---")
    for i in top_idx:
        print(f"  '{feature_names[i]}': {sums[i]:.2f}")

    # 6. Same-app vs different-app distance comparison (does dominant_app correlate with distance at all?)
    apps = [n["dominant_app"] for n in numeric]
    same_app_dists, diff_app_dists = [], []
    for i in range(len(apps)):
        for j in range(i+1, len(apps)):
            if apps[i] == apps[j]:
                same_app_dists.append(dist_matrix[i, j])
            else:
                diff_app_dists.append(dist_matrix[i, j])
    print(f"\n--- Same-app vs different-app distance (sanity check) ---")
    print(f"  Same app pairs (n={len(same_app_dists)}): median dist = {np.median(same_app_dists):.4f}")
    print(f"  Diff app pairs (n={len(diff_app_dists)}): median dist = {np.median(diff_app_dists):.4f}")
    print(f"  (If these are nearly equal, distance isn't even separating by app -- a stronger red flag)")


if __name__ == "__main__":
    main()