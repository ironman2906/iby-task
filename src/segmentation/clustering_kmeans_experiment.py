"""
clustering_kmeans_experiment.py
Controlled test: does K-Means(k=15) on the SAME feature matrix used for
DBSCAN produce meaningfully better purity? If yes -> DBSCAN was the
unsuitable component. If no -> the feature representation needs work.
"""

import sys
from pathlib import Path
from collections import Counter
import numpy as np
from sklearn.cluster import KMeans

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from clustering_labeling import segment_text_blob, segment_numeric_features
from sklearn.feature_extraction.text import TfidfVectorizer


def build_feature_matrix(segments):
    """Identical construction to clustering_labeling.cluster_segments,
    extracted here so we can swap the clustering algorithm only."""
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
    return X, numeric


def cluster_segments_kmeans(segments, k=15, random_state=42):
    X, numeric = build_feature_matrix(segments)
    km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
    cluster_ids = km.fit_predict(X)

    for seg, cid, feat in zip(segments, cluster_ids, numeric):
        seg["label"] = f"cluster_{cid}"
        seg["dominant_app"] = feat["dominant_app"]

    return segments