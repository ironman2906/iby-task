"""
labeling.py
v1 naive labeling: dominant application per segment. Deliberately minimal —
segmentation accuracy matters far more than label quality right now, and
segments.jsonl only needs consistent labels, not semantically perfect ones.
Day 3 replaces this with real clustering (TF-IDF/text-blob + DBSCAN).
"""

from collections import Counter
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import get_active_app_name


def segment_dominant_app(segment):
    apps = [get_active_app_name(e) for e in segment["events"]]
    apps = [a for a in apps if a]
    return Counter(apps).most_common(1)[0][0] if apps else "unknown"


def label_segments_naive(segments):
    for seg in segments:
        seg["label"] = segment_dominant_app(seg)
    return segments
