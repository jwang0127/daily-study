"""Generate one daily, broad-topic knowledge guide without an AI API."""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import random
import re
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ROOT / "config" / "topics.json"
DATA = ROOT / "docs" / "data"
TODAY = DATA / "today.json"
HISTORY = DATA / "history.json"
ARCHIVE = DATA / "archive"

HOT_SOURCES = {
    "百度热搜": "https://top.baidu.com/board?tab=realtime",
    "知乎热榜": "https://www.zhihu.com/hot",
    "微博热搜": "https://s.weibo.com/top/summary",
}


def fetch_titles() -> list[dict[str, str]]:
    """Best-effort domestic trend probe; the local topic library is the fallback."""
    found: list[dict[str, str]] = []
    for source, url in HOT_SOURCES.items():
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 DailyStudy/1.0"})
            raw = urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
            text = re.sub(r"<[^>]+>", " ", raw)
            text = html.unescape(re.sub(r"\s+", " ", text))
            for title in re.findall(r"[^\s<>]{2,28}", text):
                if any(x in title for x in ("热搜", "登录", "首页", "知乎", "微博", "百度")):
                    continue
                found.append({"source": source, "title": title[:80]})
        except Exception as exc:  # Network access is optional by design.
            print(f"Skipped {source}: {exc}")
    return found[:30]


def choose_topic(topics: list[dict], history: list[dict], hot: list[dict]) -> tuple[dict, str, list[dict]]:
    recent = {item.get("topic_id") for item in history[:7]}
    seed = int(hashlib.sha256(dt.date.today().isoformat().encode()).hexdigest(), 16)
    rng = random.Random(seed)
    available = [t for t in topics if t["id"] not in recent] or topics
    # A live domestic headline can nudge the choice, but never blocks the random fallback.
    for candidate in hot:
        words = set(candidate["title"])
        matches = [t for t in available if any(term in candidate["title"] for term in t.get("hot_terms", []))]
        if matches:
            return rng.choice(matches), f"来自{candidate['source']}的相关热搜：{candidate['title']}", hot
    return rng.choice(available), "今日国内热点未匹配到合适的背景主题，已从广泛主题库随机选择。", hot


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
    date = now.date()
    topics = json.loads(TOPICS.read_text(encoding="utf-8"))
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
    hot = fetch_titles()
    topic, reason, observed = choose_topic(topics, history, hot)
    payload = {
        "date": date.isoformat(),
        "date_display": date.strftime("%Y年%m月%d日"),
        "generated_at": now.isoformat(timespec="seconds"),
        "selection_reason": reason,
        "hot_observed": observed[:10],
        **topic,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    TODAY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ARCHIVE / f"{date.isoformat()}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    history = [item for item in history if item.get("date") != payload["date"]]
    history.insert(0, {"date": payload["date"], "date_display": payload["date_display"], "topic_id": payload["id"], "category": payload["category"], "title": payload["title"], "subtitle": payload["subtitle"]})
    HISTORY.write_text(json.dumps(history[:365], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {TODAY} · {payload['date']} · {payload['title']}")


if __name__ == "__main__":
    main()
