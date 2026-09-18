"""
clustering_labeling.py
Real labeling via TF-IDF (character n-grams, handles Japanese without a
tokenizer) over a text blob (window titles + extracted_text + URLs) per
segment, clustered with DBSCAN. Replaces the naive dominant-app labeler.
"""

import sys
from pathlib import Path
from collections import Counter
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import get_active_app_name, get_extracted_text


def segment_text_blob(segment):
    parts = []
    for e in segment["events"]:
        ctx = e.get("context", {}) or {}
        app = ctx.get("active_app") or {}
        title = app.get("window_title")
        if title:
            parts.append(title)
        text = get_extracted_text(e)
        if text:
            parts.append(text)
        tab = ctx.get("active_browser_tab")
        if tab and tab.get("url"):
            parts.append(tab["url"])
    return " ".join(parts)


def segment_numeric_features(segment):
    apps = [get_active_app_name(e) for e in segment["events"]]
    apps = [a for a in apps if a]
    duration = (segment["end_ms"] - segment["start_ms"]) / 1000
    return {
        "duration_s": duration,
        "n_events": len(segment["events"]),
        "unique_apps": len(set(apps)),
        "dominant_app": Counter(apps).most_common(1)[0][0] if apps else "unknown",
    }


def cluster_segments(segments, eps=0.6, min_samples=2):
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

    cluster_ids = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit_predict(X)

    for seg, cid, feat in zip(segments, cluster_ids, numeric):
        seg["label"] = f"unclustered_{feat['dominant_app']}" if cid == -1 else f"cluster_{cid}"
        seg["dominant_app"] = feat["dominant_app"]

    return segments