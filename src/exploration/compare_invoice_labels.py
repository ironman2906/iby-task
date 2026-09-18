import argparse
import json
from pathlib import Path
from collections import Counter
from datetime import datetime


TARGET_LABELS = {
    "id_INV",
    "請求書承認・経費精算",
}


def parse_iso(ts):
    if not ts:
        return None

    try:
        return datetime.fromisoformat(
            ts.replace("Z", "+00:00")
        )
    except Exception:
        return None


def load_segments(path):
    segments = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            seg = json.loads(line)

            if seg.get("label") in TARGET_LABELS:
                segments.append(seg)

    return segments


def load_events(session_dir):
    """
    Load Dataset B events from all chunk-level events.jsonl files.
    """

    events = []

    event_files = sorted(
        session_dir.rglob("events.jsonl")
    )

    for events_file in event_files:

        with open(
            events_file,
            "r",
            encoding="utf-8"
        ) as f:

            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError:
                    continue

    # Dataset B uses timestamp_iso
    events.sort(
        key=lambda e: parse_iso(
            e.get("timestamp_iso")
        ) or datetime.min.replace(
            tzinfo=None
        )
    )

    return events


def event_timestamp(event):
    return event.get("timestamp_iso")


def get_event_type(event):
    return event.get(
        "event_type",
        "UNKNOWN"
    )


def get_event_app(event):
    """
    Dataset B stores active_app inside context.
    """

    context = event.get(
        "context",
        {}
    )

    app = context.get(
        "active_app"
    )

    if isinstance(app, str) and app.strip():
        return app.strip()

    return None


def get_event_url(event):
    """
    Try common locations for URL information.
    """

    context = event.get(
        "context",
        {}
    )

    # Browser tab information may contain URL.
    active_tab = context.get(
        "active_browser_tab"
    )

    if isinstance(active_tab, str):
        return active_tab

    if isinstance(active_tab, dict):
        for key in [
            "url",
            "href",
            "uri"
        ]:
            value = active_tab.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

    payload = event.get(
        "payload",
        {}
    )

    if isinstance(payload, dict):
        for key in [
            "url",
            "href",
            "uri"
        ]:
            value = payload.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

    return None


def get_text_values(event):
    """
    Recursively collect useful text-like values from
    payload/context while avoiding huge structural dumps.
    """

    values = []

    def walk(obj, depth=0):

        if depth > 4:
            return

        if isinstance(obj, str):

            text = obj.strip()

            if not text:
                return

            # Avoid obvious IDs / technical metadata.
            if len(text) <= 1000:
                values.append(text)

            return

        if isinstance(obj, dict):

            for key, value in obj.items():

                key_lower = key.lower()

                # Focus on fields likely to contain user-visible text.
                if key_lower in {
                    "text",
                    "extracted_text",
                    "window_title",
                    "title",
                    "content",
                    "value",
                    "input_text",
                    "ocr_text",
                    "visible_text",
                }:

                    if isinstance(value, str):
                        text = value.strip()

                        if text:
                            values.append(text)

                    elif isinstance(value, dict):
                        walk(value, depth + 1)

                elif isinstance(value, (dict, list)):
                    walk(value, depth + 1)

        elif isinstance(obj, list):

            for item in obj:
                walk(item, depth + 1)

    # Search payload and context.
    walk(
        event.get("payload", {})
    )

    walk(
        event.get("context", {})
    )

    # Remove duplicates while preserving order.
    unique = []
    seen = set()

    for value in values:

        if value not in seen:
            seen.add(value)
            unique.append(value)

    return unique


def events_for_segment(events, segment):

    start = parse_iso(
        segment.get("start")
        or segment.get("start_iso")
    )

    end = parse_iso(
        segment.get("end")
        or segment.get("end_iso")
    )

    if start is None or end is None:
        return []

    selected = []

    for event in events:

        ts = parse_iso(
            event_timestamp(event)
        )

        if ts is None:
            continue

        if start <= ts <= end:
            selected.append(event)

    return selected


def segment_duration(segment):

    start = parse_iso(
        segment.get("start")
        or segment.get("start_iso")
    )

    end = parse_iso(
        segment.get("end")
        or segment.get("end_iso")
    )

    if start is None or end is None:
        return None

    return (
        end - start
    ).total_seconds()


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--segments",
        required=True
    )

    parser.add_argument(
        "--dataset-b-dir",
        required=True
    )

    parser.add_argument(
        "--out",
        required=True
    )

    args = parser.parse_args()

    segments_path = Path(
        args.segments
    )

    dataset_b_dir = Path(
        args.dataset_b_dir
    )

    output_path = Path(
        args.out
    )

    segments = load_segments(
        segments_path
    )

    segments.sort(
        key=lambda s: (
            s.get("session_id", ""),
            parse_iso(
                s.get("start")
                or s.get("start_iso")
            ) or datetime.min
        )
    )

    label_counts = Counter(
        seg.get("label")
        for seg in segments
    )

    session_labels = {}

    for seg in segments:

        session_id = seg.get(
            "session_id",
            "UNKNOWN"
        )

        session_labels.setdefault(
            session_id,
            []
        ).append(
            seg.get("label")
        )

    # Cache raw events by session.
    session_cache = {}

    lines = []

    lines.append(
        "=" * 100
    )

    lines.append(
        "INVOICE LABEL COMPARISON"
    )

    lines.append(
        "=" * 100
    )

    lines.append("")

    lines.append(
        f"Target segments: {len(segments)}"
    )

    lines.append(
        f"id_INV: "
        f"{label_counts.get('id_INV', 0)}"
    )

    lines.append(
        "請求書承認・経費精算: "
        f"{label_counts.get('請求書承認・経費精算', 0)}"
    )

    lines.append(
        f"Sessions containing either label: "
        f"{len(session_labels)}"
    )

    lines.append("")

    lines.append(
        "-" * 100
    )

    lines.append(
        "SESSION-LEVEL OVERVIEW"
    )

    lines.append(
        "-" * 100
    )

    lines.append("")

    for session_id in sorted(
        session_labels
    ):

        counts = Counter(
            session_labels[session_id]
        )

        lines.append(
            session_id
        )

        lines.append(
            f"  id_INV="
            f"{counts.get('id_INV', 0)}, "
            f"請求書承認・経費精算="
            f"{counts.get('請求書承認・経費精算', 0)}"
        )

    lines.append("")

    lines.append(
        "=" * 100
    )

    lines.append(
        "DETAILED CHRONOLOGICAL INSPECTION"
    )

    lines.append(
        "=" * 100
    )

    lines.append("")

    current_session = None

    for index, segment in enumerate(
        segments,
        start=1
    ):

        session_id = segment.get(
            "session_id",
            "UNKNOWN"
        )

        if session_id != current_session:

            current_session = session_id

            lines.append("")

            lines.append(
                "#" * 100
            )

            lines.append(
                f"SESSION: {session_id}"
            )

            lines.append(
                "#" * 100
            )

            lines.append("")

        if session_id not in session_cache:

            session_dir = (
                dataset_b_dir /
                session_id
            )

            if session_dir.exists():

                session_cache[
                    session_id
                ] = load_events(
                    session_dir
                )

            else:

                session_cache[
                    session_id
                ] = []

        events = session_cache[
            session_id
        ]

        segment_events = (
            events_for_segment(
                events,
                segment
            )
        )

        duration = segment_duration(
            segment
        )

        lines.append(
            f"SEGMENT {index}"
        )

        lines.append(
            f"  label: "
            f"{segment.get('label')}"
        )

        lines.append(
            f"  start: "
            f"{segment.get('start') or segment.get('start_iso')}"
        )

        lines.append(
            f"  end: "
            f"{segment.get('end') or segment.get('end_iso')}"
        )

        if duration is not None:

            lines.append(
                f"  duration_s: "
                f"{duration:.3f}"
            )

        lines.append(
            f"  events_in_segment: "
            f"{len(segment_events)}"
        )

        apps = sorted(
            {
                app
                for event in segment_events
                for app in [
                    get_event_app(event)
                ]
                if app
            }
        )

        urls = sorted(
            {
                url
                for event in segment_events
                for url in [
                    get_event_url(event)
                ]
                if url
            }
        )

        event_types = Counter(
            get_event_type(event)
            for event in segment_events
        )

        lines.append(
            "  apps:"
        )

        if apps:

            for app in apps:
                lines.append(
                    f"    - {app}"
                )

        else:

            lines.append(
                "    - NONE"
            )

        lines.append(
            "  urls:"
        )

        if urls:

            for url in urls[:20]:

                lines.append(
                    f"    - {url}"
                )

        else:

            lines.append(
                "    - NONE"
            )

        lines.append(
            "  event_types:"
        )

        if event_types:

            for event_type, count in (
                event_types.most_common()
            ):

                lines.append(
                    f"    - "
                    f"{event_type}: "
                    f"{count}"
                )

        else:

            lines.append(
                "    - NONE"
            )

        lines.append(
            "  extracted/useful text:"
        )

        all_text = []

        seen_text = set()

        for event in segment_events:

            for text_value in (
                get_text_values(event)
            ):

                if text_value in seen_text:
                    continue

                seen_text.add(
                    text_value
                )

                all_text.append(
                    text_value
                )

        if all_text:

            for text_value in all_text:

                if len(text_value) > 500:

                    text_value = (
                        text_value[:500]
                        + "..."
                    )

                lines.append(
                    f"    - {text_value}"
                )

        else:

            lines.append(
                "    - NONE"
            )

        lines.append("")

    lines.append(
        "=" * 100
    )

    lines.append(
        "END OF REPORT"
    )

    lines.append(
        "=" * 100
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "\n".join(lines)
        )

    print(
        f"Wrote comparison report to: "
        f"{output_path}"
    )

    print(
        f"Total target segments: "
        f"{len(segments)}"
    )

    print(
        f"id_INV: "
        f"{label_counts.get('id_INV', 0)}"
    )

    print(
        "請求書承認・経費精算: "
        f"{label_counts.get('請求書承認・経費精算', 0)}"
    )


if __name__ == "__main__":
    main()