from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render keyword analytics report")
    parser.add_argument(
        "--summary",
        default="analytics/keyword_summary.json",
        help="Path to keyword summary JSON file",
    )
    parser.add_argument(
        "--events",
        default="analytics/keyword_query_events.jsonl",
        help="Path to keyword events JSONL file",
    )
    parser.add_argument(
        "--output",
        default="analytics/keyword_report.html",
        help="Path to generated HTML report",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of keywords to show per section",
    )
    return parser.parse_args()


def load_summary(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Summary file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.values())


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def duplicate_ratio(item: dict) -> float:
    accepted = item.get("accepted_hit_total", 0) or 0
    duplicates = item.get("duplicate_hit_total", 0) or 0
    return duplicates / accepted if accepted else 0.0


def render_table(title: str, items: list[dict], columns: list[tuple[str, str]]) -> str:
    header = "".join(f"<th>{escape(label)}</th>" for _, label in columns)
    rows = []
    for item in items:
        cells = []
        for key, _ in columns:
            value = item.get(key, "")
            if isinstance(value, float):
                formatted = f"{value:.4f}"
            else:
                formatted = str(value)
            cells.append(f"<td>{escape(formatted)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    body = "\n".join(rows) if rows else '<tr><td colspan="99">No data</td></tr>'
    return f"""
    <section>
      <h2>{escape(title)}</h2>
      <table>
        <thead><tr>{header}</tr></thead>
        <tbody>{body}</tbody>
      </table>
    </section>
    """


def build_report(summary_items: list[dict], events: list[dict], top_n: int) -> str:
    top_keywords = sorted(
        summary_items,
        key=lambda item: (
            item.get("new_unique_hit_total", 0),
            item.get("new_hit_rate", 0),
            item.get("accepted_hit_total", 0),
        ),
        reverse=True,
    )[:top_n]

    zero_value = sorted(
        [item for item in summary_items if item.get("new_unique_hit_total", 0) == 0],
        key=lambda item: (
            -(item.get("executions", 0)),
            -(item.get("raw_chat_total", 0)),
            item.get("keyword", ""),
        ),
    )[:top_n]

    high_dup = sorted(
        [
            {
                **item,
                "duplicate_ratio": duplicate_ratio(item),
            }
            for item in summary_items
            if item.get("accepted_hit_total", 0) >= 5
        ],
        key=lambda item: (
            item.get("duplicate_ratio", 0),
            -item.get("new_unique_hit_total", 0),
        ),
        reverse=True,
    )[:top_n]

    event_modes = Counter(event.get("mode", "unknown") for event in events)
    event_keywords = Counter(event.get("keyword") for event in events if event.get("keyword"))

    generated_at = datetime.now().isoformat(timespec="seconds")
    total_keywords = len(summary_items)
    total_events = len(events)

    sections = [
        render_table(
            "Top keywords by new unique hits",
            top_keywords,
            [
                ("keyword", "Keyword"),
                ("executions", "Executions"),
                ("new_unique_hit_total", "New unique hits"),
                ("new_hit_rate", "New hit rate"),
                ("accepted_hit_total", "Accepted hits"),
                ("duplicate_hit_total", "Duplicate hits"),
            ],
        ),
        render_table(
            "Worst keywords with zero new unique hits",
            zero_value,
            [
                ("keyword", "Keyword"),
                ("executions", "Executions"),
                ("raw_chat_total", "Raw chats"),
                ("accepted_hit_total", "Accepted hits"),
                ("duplicate_hit_total", "Duplicate hits"),
                ("new_hit_rate", "New hit rate"),
            ],
        ),
        render_table(
            "High-duplication keywords",
            high_dup,
            [
                ("keyword", "Keyword"),
                ("duplicate_ratio", "Duplicate ratio"),
                ("accepted_hit_total", "Accepted hits"),
                ("new_unique_hit_total", "New unique hits"),
                ("new_hit_rate", "New hit rate"),
            ],
        ),
    ]

    mode_list = "".join(f"<li><b>{escape(mode)}</b>: {count}</li>" for mode, count in sorted(event_modes.items()))
    keyword_list = "".join(
        f"<li><b>{escape(keyword)}</b>: {count}</li>"
        for keyword, count in event_keywords.most_common(15)
    )

    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Keyword Analytics Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; background: #fafafa; color: #222; }}
    h1, h2 {{ margin-bottom: 12px; }}
    .meta {{ background: #fff; border: 1px solid #ddd; padding: 16px; margin-bottom: 24px; border-radius: 8px; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 28px; background: #fff; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; }}
    th {{ background: #f0f0f0; }}
    tr:nth-child(even) td {{ background: #fbfbfb; }}
    ul {{ margin-top: 8px; }}
    code {{ background: #eee; padding: 2px 6px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Keyword Analytics Report</h1>
  <div class="meta">
    <p><b>Generated at:</b> {escape(generated_at)}</p>
    <p><b>Total keywords:</b> {total_keywords}</p>
    <p><b>Total query events:</b> {total_events}</p>
    <p><b>Modes:</b></p>
    <ul>{mode_list or '<li>No events</li>'}</ul>
    <p><b>Most frequent keywords in events:</b></p>
    <ul>{keyword_list or '<li>No keyword events</li>'}</ul>
  </div>
  {''.join(sections)}
</body>
</html>
"""


def print_console_summary(summary_items: list[dict], top_n: int) -> None:
    best = sorted(summary_items, key=lambda item: item.get("new_unique_hit_total", 0), reverse=True)[:top_n]
    worst = sorted(summary_items, key=lambda item: (item.get("new_unique_hit_total", 0), item.get("new_hit_rate", 0)))[:top_n]

    print("Top keywords by new unique hits:")
    for item in best:
        print(
            f"- {item['keyword']}: new_unique={item['new_unique_hit_total']}, "
            f"new_hit_rate={item['new_hit_rate']}, executions={item['executions']}"
        )

    print("\nWeakest keywords:")
    for item in worst:
        print(
            f"- {item['keyword']}: new_unique={item['new_unique_hit_total']}, "
            f"new_hit_rate={item['new_hit_rate']}, raw={item['raw_chat_total']}"
        )


def main() -> None:
    args = parse_args()
    summary_path = Path(args.summary)
    events_path = Path(args.events)
    output_path = Path(args.output)

    summary_items = load_summary(summary_path)
    events = load_events(events_path)
    report = build_report(summary_items, events, args.top)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print_console_summary(summary_items, args.top)
    print(f"\nHTML report written to: {output_path}")


if __name__ == "__main__":
    main()
