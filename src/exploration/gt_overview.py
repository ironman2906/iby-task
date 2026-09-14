"""
Ground truth overview + data quality checks for Dataset A.
"""

import sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.append(str(Path(__file__).parent.parent / "loading"))
from loaders import (list_sessions, load_session_events, load_gt_manifest,
                      extract_true_segments, get_active_app_name)
from gt_imputation import impute_missing_end_ts, imputation_summary


DATA_A = Path(__file__).parent.parent.parent / "data" / "dataset_a"
def get_imputed_segments(session_dir, gt_manifest):
    raw_segments = extract_true_segments(gt_manifest)
    return impute_missing_end_ts(raw_segments)


def basic_overview(sessions):
    all_segments = []
    process_names = {}
    domain_counter = Counter()
    variant_counter = Counter()
    executions_per_session = []

    for session_dir in sessions:
        gt_manifest = load_gt_manifest(session_dir)
        if gt_manifest is None:
            continue
        segments = get_imputed_segments(session_dir, gt_manifest)
        executions_per_session.append(len(segments))
        for seg in segments:
            all_segments.append(seg)
            process_names[seg["process_code"]] = seg["family_name"]
            domain_counter[seg["domain"]] += 1
            variant_counter[seg["variant"]] += 1

    print(f"Total sessions with GT: {len([s for s in sessions if load_gt_manifest(s)])}")
    print(f"Total true segments: {len(all_segments)}")
    print(f"Avg executions/session: {sum(executions_per_session)/len(executions_per_session):.1f}")

    print(f"\n--- Distinct processes ({len(process_names)}) ---")
    for code, name in sorted(process_names.items()):
        print(f"  [{code}] {name}")

    print(f"\n--- Domain distribution ---")
    for d, c in domain_counter.most_common():
        print(f"  {d}: {c}")

    print(f"\n--- Variant distribution ---")
    for v, c in variant_counter.most_common():
        print(f"  {v}: {c}")

    return all_segments


def data_quality_checks(sessions):
    print(f"\n{'='*70}")
    print("DATA QUALITY CHECKS (gt_manifest.json)")
    print(f"{'='*70}")

    zero_or_negative = 0
    overlaps = 0
    spans_chunk_boundary = 0
    total_exec = 0
    duplicate_starts = 0

    for session_dir in sessions:
        gt_manifest = load_gt_manifest(session_dir)
        if gt_manifest is None:
            continue
        segments = extract_true_segments(gt_manifest)
        total_exec += len(segments)

        seen_starts = Counter()
        for seg in segments:
            seen_starts[seg["start"]] += 1
            if seg["start_dt"] and seg["end_dt"]:
                dur = (seg["end_dt"] - seg["start_dt"]).total_seconds()
                if dur <= 0:
                    zero_or_negative += 1
                    print(f"  ZERO/NEG DURATION: {session_dir.name} [{seg['process_code']}] dur={dur}s")
            if seg["continues_from_prev"] or seg["continues_to_next"]:
                spans_chunk_boundary += 1

        for start, count in seen_starts.items():
            if count > 1:
                duplicate_starts += 1

        for i in range(len(segments) - 1):
            if segments[i]["end_dt"] and segments[i+1]["start_dt"]:
                if segments[i]["end_dt"] > segments[i+1]["start_dt"]:
                    overlaps += 1
                    print(f"  OVERLAP: {session_dir.name} [{segments[i]['process_code']}] ends "
                          f"{segments[i]['end']}, [{segments[i+1]['process_code']}] starts {segments[i+1]['start']}")

    print(f"\nTotal executions checked: {total_exec}")
    print(f"Zero/negative duration executions: {zero_or_negative}")
    print(f"Overlapping consecutive executions: {overlaps}")
    print(f"Duplicate start timestamps: {duplicate_starts}")
    print(f"Executions spanning a chunk boundary: {spans_chunk_boundary} "
          f"({100*spans_chunk_boundary/total_exec:.1f}%)")


def gap_analysis(sessions):
    print(f"\n{'='*70}")
    print("GAP ANALYSIS: between consecutive true segments")
    print(f"{'='*70}")
    all_gaps = []
    for session_dir in sessions:
        gt_manifest = load_gt_manifest(session_dir)
        if gt_manifest is None:
            continue
        segments = get_imputed_segments(session_dir, gt_manifest)
        for i in range(len(segments) - 1):
            if segments[i]["end_dt"] and segments[i+1]["start_dt"]:
                gap = (segments[i+1]["start_dt"] - segments[i]["end_dt"]).total_seconds()
                all_gaps.append(gap)
    if all_gaps:
        all_gaps.sort()
        n = len(all_gaps)
        print(f"n={n}  min={all_gaps[0]:.1f}s  median={all_gaps[n//2]:.1f}s  max={all_gaps[-1]:.1f}s")
        print(f"gaps <1s: {sum(1 for g in all_gaps if g<1)}   "
              f"1-5s: {sum(1 for g in all_gaps if 1<=g<5)}   "
              f"5-30s: {sum(1 for g in all_gaps if 5<=g<30)}   "
              f">30s: {sum(1 for g in all_gaps if g>=30)}")


def boundary_vs_within_gap_comparison(sessions):
    print(f"\n{'='*70}")
    print("BOUNDARY vs WITHIN-PROCESS event gap comparison")
    print(f"{'='*70}")

    from loaders import get_event_dt, get_gap_ms

    boundary_gaps = []
    within_gaps = []

    for session_dir in sessions:
        gt_manifest = load_gt_manifest(session_dir)
        if gt_manifest is None:
            continue
        segments = get_imputed_segments(session_dir, gt_manifest)
        if not segments:
            continue
        events = load_session_events(session_dir)

        for seg in segments:
            if not (seg["start_dt"] and seg["end_dt"]):
                continue
            seg_start_ts = seg["start_dt"].timestamp()
            seg_end_ts = seg["end_dt"].timestamp()

            for e in events:
                e_dt = get_event_dt(e)
                if not e_dt:
                    continue
                e_ts = e_dt.timestamp()
                gap = get_gap_ms(e)

                near_boundary = abs(e_ts - seg_start_ts) <= 2 or abs(e_ts - seg_end_ts) <= 2
                inside_process = seg_start_ts + 2 < e_ts < seg_end_ts - 2

                if near_boundary:
                    boundary_gaps.append(gap)
                elif inside_process:
                    within_gaps.append(gap)

    def pct(vals, p):
        if not vals:
            return 0
        vals = sorted(vals)
        return vals[min(int(len(vals) * p), len(vals) - 1)]

    print(f"{'Metric':15s} {'At boundary':>14s} {'Inside process':>16s}")
    print(f"{'median':15s} {pct(boundary_gaps,0.5):14.0f} {pct(within_gaps,0.5):16.0f}")
    print(f"{'75th pct':15s} {pct(boundary_gaps,0.75):14.0f} {pct(within_gaps,0.75):16.0f}")
    print(f"{'90th pct':15s} {pct(boundary_gaps,0.90):14.0f} {pct(within_gaps,0.90):16.0f}")
    print(f"{'max':15s} {max(boundary_gaps, default=0):14.0f} {max(within_gaps, default=0):16.0f}")
    print(f"\nn(boundary)={len(boundary_gaps)}  n(within)={len(within_gaps)}")


def process_characteristics(sessions):
    print(f"\n{'='*70}")
    print("PER-PROCESS CHARACTERISTICS")
    print(f"{'='*70}")

    stats_by_process = defaultdict(lambda: {
        "durations": [], "n_events": [], "n_app_switches": [],
        "n_clicks": [], "n_keystrokes": [], "family_name": None, "variants": set()
    })

    for session_dir in sessions:
        gt_manifest = load_gt_manifest(session_dir)
        if gt_manifest is None:
            continue
        segments = get_imputed_segments(session_dir, gt_manifest)
        if not segments:
            continue
        events = load_session_events(session_dir)

        for seg in segments:
            if not (seg["start_dt"] and seg["end_dt"]):
                continue
            s_ts, e_ts = seg["start_dt"].timestamp(), seg["end_dt"].timestamp()
            seg_events = [e for e in events if s_ts <= (e["timestamp_ms"] / 1000) <= e_ts]

            key = seg["process_code"]
            st = stats_by_process[key]
            st["family_name"] = seg["family_name"]
            st["variants"].add(seg["variant"])
            st["durations"].append(e_ts - s_ts)
            st["n_events"].append(len(seg_events))

            apps = [get_active_app_name(e) for e in seg_events]
            apps = [a for a in apps if a]
            switches = sum(1 for i in range(1, len(apps)) if apps[i] != apps[i-1])
            st["n_app_switches"].append(switches)

            st["n_clicks"].append(sum(1 for e in seg_events
                                       if e["event_type"] in ("mouse_click", "browser_click")))
            st["n_keystrokes"].append(sum(1 for e in seg_events if e["event_type"] == "keystroke"))

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    print(f"{'Code':6s} {'Name':20s} {'n':4s} {'AvgDur(s)':10s} {'AvgEvts':8s} "
          f"{'AvgSwitch':10s} {'AvgClick':9s} {'AvgKeys':8s} {'#Variants':10s}")
    for code, st in sorted(stats_by_process.items()):
        print(f"{code:6s} {st['family_name'][:20]:20s} {len(st['durations']):4d} "
              f"{avg(st['durations']):10.1f} {avg(st['n_events']):8.1f} "
              f"{avg(st['n_app_switches']):10.1f} {avg(st['n_clicks']):9.1f} "
              f"{avg(st['n_keystrokes']):8.1f} {len(st['variants']):10d}")


def main():
    sessions = list_sessions(DATA_A)

    total_imputed = 0
    total_execs = 0

    for session_dir in sessions:
        gt_manifest = load_gt_manifest(session_dir)

        if gt_manifest is None:
            continue

        segments = get_imputed_segments(session_dir, gt_manifest)
        summary = imputation_summary(segments)

        total_imputed += summary["imputed"]
        total_execs += summary["total"]

    print(f"{'='*70}")
    print("IMPUTATION SUMMARY")
    print(f"{'='*70}")
    print(
        f"Total executions: {total_execs}, "
        f"imputed: {total_imputed} "
        f"({100*total_imputed/total_execs:.1f}%)\n"
    )

    basic_overview(sessions)
    data_quality_checks(sessions)
    gap_analysis(sessions)
    boundary_vs_within_gap_comparison(sessions)
    process_characteristics(sessions)


if __name__ == "__main__":
    main()