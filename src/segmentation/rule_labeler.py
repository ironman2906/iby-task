"""
rule_labeler.py

Deterministic, evidence-based labeler to replace/complement the K-Means
cluster labels for Dataset B. Built directly from patterns confirmed in
manual Day 3 cluster inspection:

  1. breadcrumb text   ("dashboard / order_management" -> "order_management")
  2. record-ID prefix  ("P6-07010448-001" -> "id_P6", "INV-..." matches too)
  3. host:port + dominant app  (fallback when no text signal fires)
  4. "non_business"    (session-startup / terminal / browser-chrome-only)

This does NOT change the locked Day 2 segmentation -- it only changes how
an already-produced segment (with its "events" list, as returned by
run_segmentation) is labeled. Drop-in replacement for
clustering_kmeans_experiment.cluster_segments_kmeans in the Day 3 pipeline.

VALIDATE ON DATASET A FIRST using the same purity/inverse-purity harness
you used for K-Means before trusting this on Dataset B.
"""
import re
import sys
from pathlib import Path
from collections import Counter
from urllib.parse import urlparse

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import get_active_app_name, get_extracted_text, get_url

# Matches "ダッシュボード / 発注管理" -> captures "発注管理"
BREADCRUMB_RE = re.compile(r"ダッシュボード\s*/\s*([^\s/]+)")

# Matches record IDs like "P6-07010448-001", "EXP-111912-001", "INV-2026-7344"
ID_PREFIX_RE = re.compile(r"\b([A-Z]{1,4}\d{0,3})-\d{4,}-?\d*\b")

# Lines that show up across many different business processes -- chrome,
# not content. Extend this list from a document-frequency scan on Dataset A
# (any line appearing in >40% of segments in a system) before trusting it.
BOILERPLATE_SUBSTRINGS = [
    "favorites bar", "Address and search bar", "Translate page from Japanese",
    "New tab", "Copyright (C) Microsoft", "Install the latest PowerShell",
]

NON_BUSINESS_APPS = {"WindowsTerminal", "OpenWith", "Notepad"}


def _clean_lines(text):
    if not text:
        return []
    lines = re.split(r"[\r\n]+", text)
    return [
        line.strip() for line in lines
        if line.strip() and not any(b in line for b in BOILERPLATE_SUBSTRINGS)
    ]


def label_segment(segment):
    """Returns (label, method) for one segment (dict with an 'events' list)."""
    texts, urls, apps = [], [], []
    for e in segment["events"]:
        t = get_extracted_text(e)
        if t:
            texts.append(t)
        u = get_url(e)
        if u:
            urls.append(u)
        a = get_active_app_name(e)
        if a:
            apps.append(a)

    joined_text = " ".join(texts)
    dominant_app = Counter(apps).most_common(1)[0][0] if apps else None

    # Non-business apps short-circuit everything else.
    if dominant_app in NON_BUSINESS_APPS:
        return "non_business", "app_blocklist"

    # 1. breadcrumb (most specific, human-readable)
    m = BREADCRUMB_RE.search(joined_text)
    if m:
        return m.group(1), "breadcrumb"

    # 2. record-ID prefix (majority vote across events in the segment)
    prefixes = ID_PREFIX_RE.findall(joined_text)
    if prefixes:
        top = Counter(prefixes).most_common(1)[0][0]
        return f"id_{top}", "id_prefix"

    # 3. host:port + dominant app fallback
    hosts = [urlparse(u).netloc for u in urls if u]
    if hosts:
        host = Counter(hosts).most_common(1)[0][0]
        return f"{host}__{dominant_app or 'unknown'}", "host_app"

    # 4. nothing usable left after stripping boilerplate -> not business work
    if not _clean_lines(joined_text) and not urls:
        return "non_business", "no_signal"

    return f"app__{dominant_app or 'unknown'}", "app_only"


def label_all(segments):
    """Mutates each segment in place with 'label' and 'label_method'."""
    method_counts = Counter()
    for seg in segments:
        label, method = label_segment(seg)
        seg["label"] = label
        seg["label_method"] = method
        method_counts[method] += 1
    return segments, method_counts


if __name__ == "__main__":
    # Quick smoke test with a synthetic segment shaped like a real one.
    fake_segment = {
        "events": [
            {
                "context": {
                    "extracted_text": (
                        "財務 財務会計システム 2026年度 ダッシュボード / "
                        "発注管理 発注管理 12 件 一覧 ID ... P10-07054374-001"
                    ),
                    "active_app": {"app_name": "Microsoft Edge"},
                    "active_browser_tab": {"url": "http://127.0.0.1:5133/#/purchase-orders"},
                }
            }
        ]
    }
    label, method = label_segment(fake_segment)
    print(f"label={label!r} method={method!r}")