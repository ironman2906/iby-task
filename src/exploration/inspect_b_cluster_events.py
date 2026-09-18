"""
Day 3 - Step 5

Manual QA for Dataset B clustering.

Dataset B has no ground-truth process labels, so this script selects the
largest K-Means clusters and prints representative raw-event information
for manual inspection.

It does not modify segmentation, clustering, or the generated segments.
"""

import sys
import json
from pathlib import Path
from collections import Counter

# Allow imports from src/loading
sys.path.append(str(Path(__file__).parent.parent / "loading"))

from loaders import (
    list_sessions,
    load_session_events,
    get_event_dt,
    get_active_app_name,
    get_url,
    get_extracted_text,
)


DATA_B = (
    Path(__file__).parent.parent.parent
    / "data"
    / "dataset_b"
)

SEGMENTS_PATH = (
    Path(__file__).parent.parent.parent
    / "outputs"
    / "segments.jsonl"
)

OUTPUT_PATH = (
    Path(__file__).parent.parent.parent
    / "outputs"
    / "day3_b_cluster_event_inspection.txt"
)

TOP_N_CLUSTERS = 5
SAMPLES_PER_CLUSTER = 3


def parse_segment_timestamp(timestamp):
    """Parse ISO timestamps used by segments.jsonl."""
    from datetime import datetime

    return datetime.fromisoformat(
        timestamp.replace("Z", "+00:00")
    )


def load_segments():
    """Load all generated Dataset B segments."""
    with open(SEGMENTS_PATH, "r", encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip()
        ]


def get_events_for_segment(events, start_dt, end_dt):
    """Return raw events whose timestamps fall inside the segment."""
    matched = []

    for event in events:
        event_dt = get_event_dt(event)

        if event_dt is None:
            continue

        if start_dt <= event_dt <= end_dt:
            matched.append(event)

    return matched


def write_segment_summary(
    output,
    segment,
    events,
    sample_number,
):
    """Write information about one sampled segment."""

    output.write(
        f"\n  SAMPLE {sample_number}\n"
    )
    output.write(
        f"  Session: {segment['session_id']}\n"
    )
    output.write(
        f"  Segment: {segment['start']} -> {segment['end']}\n"
    )
    output.write(
        f"  Event count: {len(events)}\n"
    )

    # Event types
    event_types = Counter(
        event.get("event_type", "unknown")
        for event in events
    )

    output.write("  Event types:\n")

    if event_types:
        for event_type, count in event_types.most_common():
            output.write(
                f"    {event_type}: {count}\n"
            )
    else:
        output.write("    None\n")

    # Active applications
    apps = []

    for event in events:
        app = get_active_app_name(event)

        if app:
            apps.append(app)

    output.write("  Active apps:\n")

    if apps:
        for app, count in Counter(apps).most_common():
            output.write(
                f"    {app}: {count}\n"
            )
    else:
        output.write("    None\n")

    # Window titles
    titles = []

    for event in events:
        context = event.get("context", {}) or {}
        active_app = context.get("active_app", {}) or {}
        title = active_app.get("window_title")

        if title and title not in titles:
            titles.append(title)

    output.write("  Window titles:\n")

    if titles:
        for title in titles[:5]:
            output.write(
                f"    {title[:250]}\n"
            )
    else:
        output.write("    None\n")

    # URLs
    urls = []

    for event in events:
        url = get_url(event)

        if url and url not in urls:
            urls.append(url)

    output.write("  URLs:\n")

    if urls:
        for url in urls[:5]:
            output.write(
                f"    {url[:300]}\n"
            )
    else:
        output.write("    None\n")

    # Extracted text
    texts = []

    for event in events:
        text = get_extracted_text(event)

        if isinstance(text, str):
            text = text.strip()

            if text and text not in texts:
                texts.append(text)

    output.write("  Extracted text samples:\n")

    if texts:
        for text in texts[:3]:
            cleaned = text.replace("\n", " ")
            output.write(
                f"    {cleaned[:300]}\n"
            )
    else:
        output.write("    None\n")


def main():

    segments = load_segments()

    print(f"Loaded {len(segments)} segments.")

    # Count segments belonging to each cluster
    label_counts = Counter(
        segment["label"]
        for segment in segments
    )

    top_clusters = [
        label
        for label, _ in label_counts.most_common(
            TOP_N_CLUSTERS
        )
    ]

    print("Top clusters:")

    for label in top_clusters:
        print(
            f"  {label}: {label_counts[label]}"
        )

    # Build a map from session ID to session directory.
    session_dirs = list_sessions(DATA_B)

    session_dir_map = {
        session_dir.name: session_dir
        for session_dir in session_dirs
    }

    # Cache raw events so each session is loaded only once.
    session_event_cache = {}

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8",
    ) as output:

        output.write(
            "DATASET B - CLUSTER EVENT INSPECTION\n"
        )
        output.write("=" * 80 + "\n")
        output.write(
            f"Total segments: {len(segments)}\n"
        )
        output.write(
            f"Total distinct labels: {len(label_counts)}\n"
        )
        output.write(
            f"Top {TOP_N_CLUSTERS} clusters: "
            f"{top_clusters}\n"
        )

        for label in top_clusters:

            output.write("\n")
            output.write("=" * 80 + "\n")
            output.write(
                f"CLUSTER: {label} "
                f"(total segments: {label_counts[label]})\n"
            )
            output.write("=" * 80 + "\n")

            # Take the first 3 segments belonging to this cluster.
            samples = [
                segment
                for segment in segments
                if segment["label"] == label
            ][:SAMPLES_PER_CLUSTER]

            for sample_number, segment in enumerate(
                samples,
                start=1,
            ):

                session_id = segment["session_id"]

                session_dir = session_dir_map.get(
                    session_id
                )

                if session_dir is None:
                    output.write(
                        f"\n  SAMPLE {sample_number}\n"
                    )
                    output.write(
                        f"  ERROR: Dataset B session "
                        f"{session_id} not found.\n"
                    )
                    continue

                # Load each session only once.
                if session_id not in session_event_cache:
                    session_event_cache[session_id] = (
                        load_session_events(session_dir)
                    )

                session_events = session_event_cache[
                    session_id
                ]

                start_dt = parse_segment_timestamp(
                    segment["start"]
                )

                end_dt = parse_segment_timestamp(
                    segment["end"]
                )

                matched_events = get_events_for_segment(
                    session_events,
                    start_dt,
                    end_dt,
                )

                write_segment_summary(
                    output,
                    segment,
                    matched_events,
                    sample_number,
                )

    print()
    print(
        f"Wrote inspection output to:"
    )
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()