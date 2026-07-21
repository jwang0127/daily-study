from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ROOT / "config" / "topics.json"
OUT = ROOT / "docs" / "data" / "today.json"


def main() -> None:
    today = dt.date.today()
    topics = json.loads(TOPICS.read_text(encoding="utf-8"))
    topic = topics[today.toordinal() % len(topics)]
    payload = {
        "date": today.isoformat(),
        "date_display": today.strftime("%Y年%m月%d日"),
        "topic_index": today.toordinal() % len(topics),
        "topic_count": len(topics),
        **topic,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {OUT} · {payload['date']} · {payload['title']}")


if __name__ == "__main__":
    main()
