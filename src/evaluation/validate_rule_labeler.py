import sys
from pathlib import Path
from collections import defaultdict, Counter

sys.path.append(str(Path(__file__).parent.parent / "loading"))
sys.path.append(str(Path(__file__).parent.parent / "exploration"))
sys.path.append(str(Path(__file__).parent.parent / "segmentation"))

from loaders import (
    list_sessions,
    load_session_events,
    load_gt_manifest,
    extract_true_segments,
)

from gt_imputation import impute_missing_end_ts
from boundary_detection import run_segmentation
from rule_labeler import label_all
from evaluator import match_one_to_one


DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"


def main():

    sessions = list_sessions(DATA_A)[:20]

    all_segments = []
    session_boundaries = []
    method_counts = Counter()

    print(f"Dataset A sessions checked: {len(sessions)}")
    print()

    # ---------------------------------------------------------
    # Segment all 20 sessions using the LOCKED Day 2 segmenter
    # ---------------------------------------------------------
    for session_dir in sessions:

        session_id = session_dir.name

        events = load_session_events(session_dir)

        if not events:
            print(f"{session_id}: no events, skipped")
            continue

        start_idx = len(all_segments)

        segments = run_segmentation(events)

        # Apply Claude's rule-based labeler
        segments, methods = label_all(segments)

        method_counts.update(methods)

        all_segments.extend(segments)

        end_idx = len(all_segments)

        session_boundaries.append(
            (session_dir, start_idx, end_idx)
        )

        print(
            f"{session_id}: "
            f"{len(events)} events -> "
            f"{len(segments)} segments"
        )

    print()

    # ---------------------------------------------------------
    # Evaluate labels against the SAME imputed GT used before
    # ---------------------------------------------------------
    label_to_true_codes = defaultdict(Counter)

    for session_dir, start_idx, end_idx in session_boundaries:

        gt_manifest = load_gt_manifest(session_dir)

        true_segments = impute_missing_end_ts(
            extract_true_segments(gt_manifest)
        )

        predicted_segments = all_segments[
            start_idx:end_idx
        ]

        matches, _ = match_one_to_one(
            true_segments,
            predicted_segments
        )

        for true_seg, pred_seg, iou in matches:

            if pred_seg and iou > 0.3:

                label_to_true_codes[
                    pred_seg["label"]
                ][
                    true_seg["process_code"]
                ] += 1

    # ---------------------------------------------------------
    # Calculate purity
    # ---------------------------------------------------------
    total = 0
    correct = 0

    for label, code_counts in label_to_true_codes.items():

        most_common_count = (
            code_counts.most_common(1)[0][1]
        )

        correct += most_common_count
        total += sum(code_counts.values())

    purity = correct / total if total else 0

    # ---------------------------------------------------------
    # Results
    # ---------------------------------------------------------
    print("=" * 70)
    print("RULE LABELER VALIDATION")
    print("=" * 70)

    print(f"Total segments: {len(all_segments)}")
    print(f"Matched segments (IoU > 0.3): {total}")
    print(f"Purity: {purity:.3f}")

    print()
    print("Labeling methods used:")

    for method, count in method_counts.most_common():

        print(
            f"  {method:<20} {count}"
        )

    print()
    print("Distinct labels:")
    print(
        f"  {len(label_to_true_codes)}"
    )

    print()
    print("Label -> true process_code distribution:")
    print()

    for label, code_counts in sorted(
        label_to_true_codes.items(),
        key=lambda x: -sum(x[1].values())
    ):

        print(
            f"'{label}': {dict(code_counts)}"
        )

    print()
    print(
        f"Baseline K-Means purity: 0.372"
    )

    if purity > 0.372:

        print(
            "Decision: RULE LABELER BEATS K-MEANS"
        )

    else:

        print(
            "Decision: KEEP K-MEANS"
        )


if __name__ == "__main__":
    main()