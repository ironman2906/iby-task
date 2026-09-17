"""
text_change_diagnostic.py
DIAGNOSTIC ONLY — does not modify or re-tune boundary_detection.py.
For each text_change-alone boundary already fired by the locked v2
detector, classify it using simple structural heuristics to distinguish
likely genuine content transitions from likely transient/jitter firings.
"""

import sys
import re
import difflib
from pathlib import Path
from collections import Counter

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import (load_session_events, get_active_app_name, get_gap_ms,
                      get_url, get_extracted_text)
import boundary_detection as bd

# Heuristic: a case/record ID pattern (letters+digits, e.g. EXP-111912-001, RT-111912-001)
ID_PATTERN = re.compile(r'[A-Z]{1,4}-\d{4,}-\d{2,}')


def classify_text_pair(prev_text, curr_text, similarity):
    """Lightweight, non-tuning classification of a text_change firing."""
    prev_ids = set(ID_PATTERN.findall(prev_text or ""))
    curr_ids = set(ID_PATTERN.findall(curr_text or ""))
    ids_changed = bool(prev_ids) and bool(curr_ids) and prev_ids != curr_ids

    len_prev = len(prev_text or "")
    len_curr = len(curr_text or "")
    len_ratio = min(len_prev, len_curr) / max(len_prev, len_curr) if max(len_prev, len_curr) > 0 else 1.0
    is_short_blip = min(len_prev, len_curr) < 50  # one side is a very short fragment

    if ids_changed:
        return "likely_genuine (case/record ID changed)"
    if is_short_blip and len_ratio < 0.3:
        return "likely_jitter (short transient text)"
    if similarity < 0.3:
        return "likely_genuine (large content change)"
    return "ambiguous"


def diagnose_session(session_name):
    session_dir = Path(__file__).parent.parent.parent / "data" / "dataset_a" / session_name
    events = load_session_events(session_dir)

    state = {
        "app": get_active_app_name(events[0]),
        "url": get_url(events[0]),
        "text": get_extracted_text(events[0]),
    }

    results = []

    for i in range(1, len(events)):
        e = events[i]
        lookahead = events[i:i + bd.MIN_APP_SWITCH_PERSISTENCE]
        score, new_state = bd.compute_boundary_score(state, e, lookahead)

        curr_text = get_extracted_text(e)
        curr_app = get_active_app_name(e)
        curr_url = get_url(e)

        # was this boundary fired, and was text_change the ONLY contributing signal?
        text_fired = bool(curr_text and state.get("text") and
                           not bd.texts_are_similar(curr_text, state.get("text")))
        app_fired = curr_app is not None and curr_app != state.get("app")
        url_fired = curr_url is not None and state.get("url") is not None and curr_url != state.get("url")
        gap_fired = get_gap_ms(e) > bd.GAP_THRESHOLD_MS

        is_boundary = score >= bd.BOUNDARY_SCORE_THRESHOLD
        text_alone = is_boundary and text_fired and not app_fired and not url_fired and not gap_fired

        if text_alone:
            similarity = difflib.SequenceMatcher(None, state.get("text"), curr_text).ratio()
            classification = classify_text_pair(state.get("text"), curr_text, similarity)
            results.append({
                "timestamp": e["timestamp_iso"],
                "similarity": similarity,
                "classification": classification,
            })

        state = new_state

    return results


def main():
    session_name = "ses_20260701-054901-LAPTOP-R36BQBTE"
    results = diagnose_session(session_name)

    print(f"Session: {session_name}")
    print(f"Total text_change-alone boundaries: {len(results)}\n")

    classification_counts = Counter(r["classification"] for r in results)
    print(f"{'Classification':45s} {'Count':6s} {'%':6s}")
    for cls, count in classification_counts.most_common():
        print(f"{cls:45s} {count:6d} {100*count/len(results):5.1f}%")

    print(f"\nSimilarity score distribution for these firings:")
    sims = sorted(r["similarity"] for r in results)
    n = len(sims)
    if n:
        print(f"  min={sims[0]:.3f}  median={sims[n//2]:.3f}  "
              f"75th={sims[int(n*0.75)]:.3f}  max={sims[-1]:.3f}")
        print(f"  (threshold is 0.85 — all these are below it by definition)")


if __name__ == "__main__":
    main()