"""
gt_imputation.py

Explicit, opt-in imputation for missing ground-truth end timestamps.
Raw ground truth returned by loaders.py is never modified.
"""

import copy


def impute_missing_end_ts(segments, session_end_dt=None):
    """
    Return a new list with missing end timestamps explicitly imputed.

    Missing ends are filled using the next execution's start timestamp.
    A final missing end may optionally use the session end timestamp.

    Imputed segments are marked with end_imputed=True.
    """

    segments = copy.deepcopy(segments)

    for i in range(len(segments) - 1):
        if segments[i]["end_dt"] is None:
            next_start = segments[i + 1]["start_dt"]

            if next_start is not None:
                segments[i]["end_dt"] = next_start
                segments[i]["end"] = segments[i + 1]["start"]
                segments[i]["end_imputed"] = True
            else:
                segments[i]["end_imputed"] = False
        else:
            segments[i]["end_imputed"] = False

    if segments:
        if segments[-1]["end_dt"] is None:
            if session_end_dt is not None:
                segments[-1]["end_dt"] = session_end_dt
                segments[-1]["end"] = session_end_dt.isoformat()
                segments[-1]["end_imputed"] = True
            else:
                segments[-1]["end_imputed"] = False
        else:
            segments[-1]["end_imputed"] = False

    return segments


def imputation_summary(segments):
    """Return statistics describing the imputation."""

    total = len(segments)
    imputed = sum(1 for s in segments if s.get("end_imputed", False))
    still_missing = sum(1 for s in segments if s["end_dt"] is None)

    return {
        "total": total,
        "imputed": imputed,
        "still_missing_after_imputation": still_missing,
        "pct_imputed": 100 * imputed / total if total else 0,
    }