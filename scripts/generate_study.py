"""Generate one substantial daily knowledge article.

DeepSeek is required for publication: the script fetches real web sources,
asks the model to write from them, and fails loudly (keeping the previous
day's page) instead of publishing a template article when anything is
missing. Tencent TTS narration, the Atom feed and audio pruning run after
the article is generated.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import json
import os
import random
import re
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ROOT / "config" / "topics.json"
DATA = ROOT / "docs" / "data"
TODAY = DATA / "today.json"
HISTORY = DATA / "history.json"
ARCHIVE = DATA / "archive"
AUDIO = ROOT / "docs" / "audio"
FEED = ROOT / "docs" / "feed.xml"
BASE_URL = os.environ.get("SITE_BASE_URL", "https://jwang0127.github.io/daily-study/")
AUDIO_KEEP_DAYS = int(os.environ.get("AUDIO_KEEP_DAYS", "14"))
HOT_SOURCES = {"百度热搜": "https://top.baidu.com/board?tab=realtime", "知乎热榜": "https://www.zhihu.com/hot", "微博热搜": "https://s.weibo.com/top/summary"}
API_STATUS = "not_checked"

try:
    SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    # Windows Python installations may not include the optional tzdata package.
    SHANGHAI_TZ = dt.timezone(dt.timedelta(hours=8), name="Asia/Shanghai")


def decode_bytes(raw: bytes, content_type: str = "") -> str:
    """Decode a fetched page, honouring declared charsets before guessing.

    Chinese government and finance sites still commonly serve GBK; decoding
    them as UTF-8 with errors ignored silently produces mojibake that would
    poison the research excerpts handed to the model.
    """
    declared = re.search(r"charset=[\"']?([\w-]+)", content_type or "", re.I)
    if not declared:
        head = raw[:4096].decode("ascii", errors="ignore")
        declared = re.search(r"charset=[\"']?([\w-]+)", head, re.I)
    candidates = ([declared.group(1)] if declared else []) + ["utf-8", "gb18030"]
    for name in candidates:
        try:
            return raw.decode(name)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="ignore")


def http_get(url: str, timeout: int = 10, limit: int = 1_000_000, agent: str = "Mozilla/5.0 DailyStudy/1.0") -> str:
    req = Request(url, headers={"User-Agent": agent})
    with urlopen(req, timeout=timeout) as response:
        raw = response.read(limit)
        return decode_bytes(raw, response.headers.get("Content-Type", ""))


def fetch_titles() -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for source, url in HOT_SOURCES.items():
        print(f"Checking {source}...", flush=True)
        try:
            raw = http_get(url, timeout=8)
        except Exception as exc:
            print(f"Skipped {source}: {exc}")
            continue
        text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)))
        for title in re.findall(r"[^\s<>]{2,28}", text):
            if any(x in title for x in ("热搜", "登录", "首页", "知乎", "微博", "百度", "margin", "padding", "color", "font", "gap", "display")):
                continue
            if not re.search(r"[一-鿿]", title) or re.search(r"[{};:#.]", title):
                continue
            if title in seen:
                continue
            seen.add(title)
            found.append({"source": source, "title": title[:80]})
    return found[:30]


def choose_topic(topics: list[dict], history: list[dict], hot: list[dict], today: dt.date | None = None) -> tuple[dict, str, list[dict]]:
    # Use the publication timezone, not the runner's local date, so the
    # scheduled-topic check and the published date can never disagree.
    day = (today or dt.datetime.now(SHANGHAI_TZ).date()).isoformat()
    scheduled = [t for t in topics if t.get("publish_date") == day]
    if scheduled:
        return scheduled[0], f"按主题库安排发布：{scheduled[0]['title']}", hot
    # A rerun on the same day must not replace an already published article
    # with a different random topic (for example after a workflow retry).
    published_today = next((item for item in history if item.get("date") == day), None)
    if published_today:
        existing = next((t for t in topics if t.get("id") == published_today.get("topic_id")), None)
        if existing:
            return existing, f"保持当日已发布主题：{existing['title']}", hot
    recent = {item.get("topic_id") for item in history[:7]}
    seed = int(hashlib.sha256(day.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    available = [t for t in topics if t["id"] not in recent] or topics
    for candidate in hot:
        matches = [t for t in available if any(term in candidate["title"] for term in t.get("hot_terms", []))]
        if matches:
            return rng.choice(matches), f"来自{candidate['source']}的相关热搜：{candidate['title']}", hot
    return rng.choice(available), "今日热点未匹配到合适的背景主题，已从广泛主题库随机选择。", hot


def fetch_research(topic: dict) -> list[dict[str, str]]:
    """Fetch readable source material before asking the model to write.

    Search links are useful to readers but are not evidence for the article,
    so only stable, direct HTTP sources are fetched here.
    """
    research: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in topic.get("resources", []):
        if len(research) >= 6 or len(item) < 3:
            break
        url = item[2]
        if not url.startswith(("https://", "http://")) or any(x in url for x in ("search?", "search/", "baidu.com/s?", "bilibili.com/all?")):
            continue
        if url in seen:
            continue
        seen.add(url)
        raw = ""
        for attempt in range(2):
            try:
                raw = http_get(url, timeout=15, agent="Mozilla/5.0 DailyStudyResearch/1.0")
                break
            except Exception as exc:
                if attempt == 0:
                    time.sleep(2)
                else:
                    print(f"Source skipped: {url} · {exc}")
        if not raw:
            continue
        page_title = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
        text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<noscript[\s\S]*?</noscript>", " ", raw, flags=re.I)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 300:
            continue
        research.append({"title": html.unescape(page_title.group(1)).strip() if page_title else item[1], "url": url, "excerpt": text[:6000]})
        print(f"Fetched source: {url}", flush=True)
    if not research:
        raise RuntimeError(f"No readable web sources were fetched for {topic['title']}")
    return research


def strip_code_fences(content: str) -> str:
    """Unwrap ```json fences some models add despite the JSON response format."""
    content = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, re.S)
    return match.group(1) if match else content


def call_deepseek(topic: dict, reason: str, hot: list[dict], research: list[dict[str, str]]) -> dict | None:
    global API_STATUS
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        API_STATUS = "missing_key"
        print("DEEPSEEK_API_KEY is not present; refusing to publish a template article")
        return None
    prompt = f"""你是中文调查型编辑。请基于下方今天实际抓取的网页资料，为普通读者写一篇有判断、有证据、有具体细节的文章，主题是“{topic['title']}”。文章不是课程、提纲、读书笔记或链接清单，也不要套用固定的‘概念—历史—参与者—争议’顺序。请根据材料本身决定叙事结构：可以从一个案例、一个矛盾、一组数据或一条新闻切入，再解释背景和因果。\n\n只写资料能够支持的内容；每个关键事实后尽量标注[来源：来源标题]，数字必须能在抓取材料中找到，材料不足就明确说没有可靠数字。若主题涉及宣传或营销费用，必须拆解预算科目与计费口径（如创意制作、媒介采买、达人/赛事、联名、渠道和效果指标），明确区分公开披露、行业报告、媒体估算与无法确认的单款数字，绝不补写看似精确但没有来源的金额。区分事实、作者分析和未解决问题，不要编造人物、公司、案例、网址或统计数字，不要使用‘影响深远、值得关注、赋能、全面升级’等空话。文章要回答：这件事到底发生了什么，谁在做什么，为什么这样做，实际结果或代价是什么，读者应该如何理解。正文目标为 5000-8000 字，但只能用资料支持的事实、案例、比较、因果和费用口径来达到；不要为了凑字数重复观点。结构、章节数量和叙事顺序由证据决定，不套固定模型或固定栏目。每一段都应推进论证，资料不足就明确说明，不要用空泛形容词、口号或水词填充。\n\n严格返回 JSON，不要 Markdown 代码围栏，字段为：overview（1-3段）；sections（若干项，每项有 heading 和 paragraphs 数组，标题和段落要根据文章内容自然生成，不要使用固定栏目名）；key_takeaways（可选，3-6条具体结论）；sources_used（实际使用的 URL 数组）。不要强行生成 history、timeline 或 chart。\n\n主题资料：{json.dumps(topic, ensure_ascii=False)}\n选题线索：{reason}\n实时热点：{json.dumps(hot[:10], ensure_ascii=False)}\n网页抓取资料：{json.dumps(research, ensure_ascii=False)}"""
    body = {"model": "deepseek-v4-flash", "messages": [{"role": "system", "content": "你是严谨、清晰、偏中文的知识编辑。"}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 16000, "response_format": {"type": "json_object"}}
    for attempt in range(3):
        try:
            print(f"Calling DeepSeek API (attempt {attempt + 1}/3); this may take a few minutes...", flush=True)
            req = Request("https://api.deepseek.com/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
            result = json.loads(urlopen(req, timeout=240).read().decode("utf-8"))
            content = strip_code_fences(result["choices"][0]["message"]["content"])
            parsed = json.loads(content)
            if parsed.get("sections") and parsed.get("overview"):
                API_STATUS = "success"
                print("DeepSeek article generated successfully")
                return parsed
            API_STATUS = "invalid_json"
            print("DeepSeek returned JSON without the required fields")
        except Exception as exc:
            API_STATUS = f"failed_{type(exc).__name__}"
            print(f"DeepSeek attempt {attempt + 1}/3 failed: {exc}")
        if attempt < 2:
            time.sleep(10 * (attempt + 1))
    return None


def build_media(topic: dict) -> list[list[str]]:
    print("Looking for a concrete Bilibili link...", flush=True)
    resources = [list(item) for item in topic.get("resources", [])]
    title = topic["title"]
    query_items = [
        ["中文视频搜索", f"B站搜索：{title} 深度讲解", f"https://search.bilibili.com/all?keyword={quote(title + ' 深度讲解')}", "优先筛选 20 分钟以上、大学课程、纪录片或专业机构账号。"],
        ["中文视频搜索", f"B站搜索：{title} 历史 发展", f"https://search.bilibili.com/all?keyword={quote(title + ' 历史 发展')}", "适合补充时间线和关键转折。"],
        ["中文播客搜索", f"小宇宙搜索：{title}", f"https://www.xiaoyuzhoufm.com/search?keyword={quote(title)}", "如果找不到具体单集，按主题和节目名称筛选 30 分钟以上内容。"],
        ["数据入口", f"百度搜索：{title} 数据 图表", f"https://www.baidu.com/s?wd={quote(title + ' 数据 图表')}", "优先使用政府、大学、研究机构或上市公司年报数据。"],
    ]
    existing_urls = {item[2] for item in resources}
    resources.extend(item for item in query_items if item[2] not in existing_urls)
    # Bilibili search pages are often accessible even when the result page is
    # not. When possible, preserve the search fallback and add a concrete BV
    # video URL found today.
    direct: list[str] | None = None
    for item in resources:
        if item[0] not in {"Bilibili", "视频"} or "search.bilibili.com" not in item[2]:
            continue
        try:
            page = http_get(item[2], timeout=10)
            ids = list(dict.fromkeys(re.findall(r"(?:www\.bilibili\.com/video/|b23\.tv/)(BV[a-zA-Z0-9]+)", page)))
            if ids:
                direct = ["Bilibili 单集", f"B站具体视频：{ids[0]}", f"https://www.bilibili.com/video/{ids[0]}", "程序今天从对应主题的 Bilibili 结果页找到的具体单集；如果页面失效，请使用下面的搜索入口。"]
        except Exception as exc:
            print(f"Bilibili direct-link lookup skipped: {exc}")
        break
    if direct:
        resources.insert(0, direct)
    return resources


def narration_text(topic: dict, article: dict) -> str:
    """Build a clean reading script from the structured article payload."""
    parts: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str):
            if value.strip():
                parts.append(value.strip())
        elif isinstance(value, list):
            for item in value:
                add(item)

    add(topic.get("title", ""))
    add(topic.get("subtitle", ""))
    add(article.get("overview", ""))
    add(article.get("history", ""))
    for section in article.get("sections", []):
        add(section.get("heading", ""))
        add(section.get("paragraphs", []))
    return re.sub(r"\s+", " ", "。".join(parts).strip())


def split_tts_text(text: str, limit: int = 145) -> list[str]:
    """Keep each basic TTS request below Tencent's 150-Chinese-character limit."""
    chunks: list[str] = []
    remaining = text
    punctuation = "。！？；：，、,.!?;:"
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = max(remaining.rfind(mark, 0, limit) for mark in punctuation)
        if cut < limit // 2:
            cut = limit - 1
        chunks.append(remaining[: cut + 1])
        remaining = remaining[cut + 1 :].lstrip()
    return chunks


def merge_mp3_chunks(parts: list[bytes]) -> bytes:
    """Concatenate MP3 responses, keeping only the first chunk's ID3 header.

    Later chunks may carry their own ID3v2 tag; its size field is four
    synchsafe bytes (7 data bits each, big-endian) at offsets 6-9.
    """
    merged = bytearray(parts[0])
    for part in parts[1:]:
        if part.startswith(b"ID3") and len(part) >= 10:
            tag_size = sum((part[i] & 0x7F) << (7 * (9 - i)) for i in range(6, 10))
            part = part[10 + tag_size :]
        merged.extend(part)
    return bytes(merged)


def generate_audio(payload: dict) -> dict:
    """Generate the day's MP3 with Tencent Cloud's basic TextToVoice API."""
    # Copy/paste from Tencent Cloud can leave a trailing newline or space in a
    # GitHub secret. Strip only the outside whitespace; never alter the key.
    secret_id = os.environ.get("TENCENTCLOUD_SECRET_ID", "").strip()
    secret_key = os.environ.get("TENCENTCLOUD_SECRET_KEY", "").strip()
    if not secret_id and not secret_key:
        print("Tencent TTS credentials are not present; skipping audio locally")
        return {"status": "skipped", "url": "", "characters": 0, "chunks": 0}
    if not secret_id or not secret_key:
        raise RuntimeError("Both TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY are required")
    if re.search(r"\s", secret_id) or re.search(r"\s", secret_key):
        raise RuntimeError("Tencent Cloud credentials contain internal whitespace; copy the values without spaces")

    try:
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.tts.v20190823 import models, tts_client
    except ImportError as exc:
        raise RuntimeError("Tencent TTS SDK is missing; install tencentcloud-sdk-python-tts") from exc

    voice_type = int(os.environ.get("TENCENT_TTS_VOICE_TYPE", "1001"))
    speed = float(os.environ.get("TENCENT_TTS_SPEED", "0"))
    text = narration_text(payload, payload)
    chunks = split_tts_text(text)
    http_profile = HttpProfile()
    http_profile.endpoint = "tts.tencentcloudapi.com"
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    client = tts_client.TtsClient(credential.Credential(secret_id, secret_key), "ap-beijing", client_profile)
    audio_parts: list[bytes] = []

    for index, chunk in enumerate(chunks, start=1):
        request = models.TextToVoiceRequest()
        request.from_json_string(json.dumps({
            "Text": chunk,
            "SessionId": f"daily-study-{payload['date']}-{index}",
            "Volume": 0,
            "Speed": speed,
            "VoiceType": voice_type,
            "PrimaryLanguage": 1,
            "SampleRate": 16000,
            "Codec": "mp3",
        }))
        last_error = None
        for attempt in range(3):
            try:
                response = client.TextToVoice(request)
                audio = getattr(response, "Audio", "")
                if not audio:
                    raise RuntimeError("Tencent TTS returned no audio data")
                audio_parts.append(base64.b64decode(audio))
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2)
        if last_error is not None:
            raise RuntimeError(f"Tencent TTS failed on chunk {index}/{len(chunks)}: {last_error}") from last_error
        print(f"Generated TTS chunk {index}/{len(chunks)}", flush=True)

    AUDIO.mkdir(parents=True, exist_ok=True)
    audio_path = AUDIO / f"{payload['date']}.mp3"
    audio_path.write_bytes(merge_mp3_chunks(audio_parts))
    print(f"Generated audio {audio_path} ({len(text)} characters)", flush=True)
    return {"status": "generated", "url": f"audio/{audio_path.name}", "characters": len(text), "chunks": len(chunks), "voice_type": voice_type}


def prune_old_audio(today: dt.date, keep_days: int = AUDIO_KEEP_DAYS) -> list[str]:
    """Delete daily MP3s past the retention window so the repo stays small.

    Archive JSON keeps its audio reference; the page hides the player when
    the file is no longer served.
    """
    removed: list[str] = []
    if not AUDIO.exists():
        return removed
    for path in sorted(AUDIO.glob("*.mp3")):
        try:
            file_date = dt.date.fromisoformat(path.stem)
        except ValueError:
            continue
        if (today - file_date).days > keep_days:
            path.unlink()
            removed.append(path.name)
            print(f"Pruned old audio {path.name}")
    return removed


def build_feed(history: list[dict], updated: str, base_url: str = BASE_URL) -> str:
    """Render an Atom feed so readers can subscribe to the daily article."""

    def x(value: object) -> str:
        return html.escape(str(value or ""), quote=True)

    entries = []
    for item in history[:60]:
        date = x(item.get("date"))
        link = f"{x(base_url)}index.html?date={date}"
        entries.append(
            "<entry>"
            f"<title>{x(item.get('title'))}</title>"
            f'<link href="{link}"/>'
            f"<id>{link}</id>"
            f"<updated>{date}T00:00:00+08:00</updated>"
            f"<summary>{x(item.get('subtitle'))}</summary>"
            f'<category term="{x(item.get("category"))}"/>'
            "</entry>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        "<title>每日认识一个主题</title>\n"
        f'<link href="{x(base_url)}"/>\n'
        f'<link rel="self" href="{x(base_url)}feed.xml"/>\n'
        f"<id>{x(base_url)}</id>\n"
        f"<updated>{x(updated)}</updated>\n"
        "<author><name>Daily Study</name></author>\n" + "\n".join(entries) + "\n</feed>\n"
    )


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc).astimezone(SHANGHAI_TZ)
    topics = json.loads(TOPICS.read_text(encoding="utf-8"))
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
    hot = fetch_titles()
    topic, reason, observed = choose_topic(topics, history, hot, today=now.date())
    media = build_media(topic)
    research = fetch_research(topic)
    prompt_topic = {**topic, "resources": media}
    generated = call_deepseek(prompt_topic, reason, observed, research)
    if not generated:
        raise RuntimeError("DeepSeek article generation failed; no template fallback was published")
    # Archive files live forever; keep where the research came from, but not
    # the multi-KB excerpts that were only needed for the one-off model call.
    research_refs = [{"title": r["title"], "url": r["url"], "excerpt_chars": len(r["excerpt"])} for r in research]
    payload = {"date": now.date().isoformat(), "date_display": now.strftime("%Y年%m月%d日"), "generated_at": now.isoformat(timespec="seconds"), "article_mode": "deepseek", "api_status": API_STATUS, "selection_reason": reason, "hot_observed": observed[:10], "research": research_refs, **topic, **generated, "resources": media}
    payload["audio"] = generate_audio(payload)
    DATA.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    TODAY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ARCHIVE / f"{payload['date']}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    history = [x for x in history if x.get("date") != payload["date"]]
    history.insert(0, {"date": payload["date"], "date_display": payload["date_display"], "topic_id": payload["id"], "category": payload["category"], "title": payload["title"], "subtitle": payload["subtitle"], "article_mode": payload["article_mode"]})
    history = history[:365]
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    FEED.write_text(build_feed(history, now.isoformat(timespec="seconds")), encoding="utf-8")
    prune_old_audio(now.date())
    print(f"Generated {TODAY} · {payload['date']} · {payload['title']} · {payload['article_mode']}")


if __name__ == "__main__":
    main()
