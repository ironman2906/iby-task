from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent / "loading"))

from loaders import list_sessions, load_gt_manifest, extract_true_segments
from gt_imputation import impute_missing_end_ts, imputation_summary


DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"


def main():
    total_raw = 0
    total_imputed = 0
    total_still_missing = 0

    for session_dir in list_sessions(DATA_A):
        manifest = load_gt_manifest(session_dir)

        if manifest is None:
            continue

        raw_segments = extract_true_segments(manifest)
        segments = impute_missing_end_ts(raw_segments)

        summary = imputation_summary(segments)

        total_raw += summary["total"]
        total_imputed += summary["imputed"]
        total_still_missing += summary["still_missing_after_imputation"]

    print(f"Total executions: {total_raw}")
    print(f"Imputed ends: {total_imputed}")
    print(f"Still missing: {total_still_missing}")
    print(
        f"Imputation rate: "
        f"{100 * total_imputed / total_raw:.1f}%"
    )


if __name__ == "__main__":
    main()

print("\nChecking start/end ordering...")

for session_dir in list_sessions(DATA_A):
    gt_manifest = load_gt_manifest(session_dir)
    raw_segments = extract_true_segments(gt_manifest)
    segments = impute_missing_end_ts(raw_segments)

    for seg in segments:
        if (
            seg["end_dt"]
            and seg["start_dt"]
            and seg["end_dt"] < seg["start_dt"]
        ):
            print(
                f"BAD: {session_dir.name} [{seg['process_code']}] "
                f"start={seg['start']} end={seg['end']} "
                f"(imputed={seg.get('end_imputed')})"
            )

print("Check complete.")