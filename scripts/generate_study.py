"""Generate one substantial daily knowledge article.

DeepSeek is optional. Without DEEPSEEK_API_KEY the script publishes a local
fallback article, so scheduled updates never depend on an API being healthy.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import random
import re
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
HOT_SOURCES = {"百度热搜": "https://top.baidu.com/board?tab=realtime", "知乎热榜": "https://www.zhihu.com/hot", "微博热搜": "https://s.weibo.com/top/summary"}


def fetch_titles() -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for source, url in HOT_SOURCES.items():
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 DailyStudy/1.0"})
            raw = urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
            text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)))
            for title in re.findall(r"[^\s<>]{2,28}", text):
                if any(x in title for x in ("热搜", "登录", "首页", "知乎", "微博", "百度")):
                    continue
                found.append({"source": source, "title": title[:80]})
        except Exception as exc:
            print(f"Skipped {source}: {exc}")
    return found[:30]


def choose_topic(topics: list[dict], history: list[dict], hot: list[dict]) -> tuple[dict, str, list[dict]]:
    recent = {item.get("topic_id") for item in history[:7]}
    seed = int(hashlib.sha256(dt.date.today().isoformat().encode()).hexdigest(), 16)
    rng = random.Random(seed)
    available = [t for t in topics if t["id"] not in recent] or topics
    for candidate in hot:
        matches = [t for t in available if any(term in candidate["title"] for term in t.get("hot_terms", []))]
        if matches:
            return rng.choice(matches), f"来自{candidate['source']}的相关热搜：{candidate['title']}", hot
    return rng.choice(available), "今日热点未匹配到合适的背景主题，已从广泛主题库随机选择。", hot


def fallback_article(topic: dict) -> dict:
    points = topic.get("points", [])
    article = {
        "overview": topic["overview"],
        "history": topic["history"],
        "sections": [
            {"heading": "先建立一个整体认识", "paragraphs": [topic["overview"], f"可以先把这个主题拆成几个互相关联的部分：{ '、'.join(points) }。这样阅读后面的历史与案例时，不会只记住名词，而能知道每个名词在整个系统中的位置。"]},
            {"heading": "它是怎么发展到今天的", "paragraphs": [topic["history"], "历史变化通常不是由单一人物或单一技术造成的。制度、资本、技术、人口、战争、市场和文化会互相推动，也会互相限制。把这些因素放到时间线上，才能理解为什么今天的讨论会出现，而不是把当下的热点看成突然发生。"]},
            {"heading": "它内部有哪些关键部分", "paragraphs": [f"理解这个领域，可以围绕以下几个问题展开：{'；'.join(points)}。它们往往分别对应不同的参与者、资源和利益。普通人不需要马上掌握专业细节，但知道这些部分之间怎样连接，就已经能够读懂大多数基础报道。", "在现实世界中，一个概念很少只存在于书本里。它通常会进入企业、政府、研究机构、媒体和普通人的生活，形成一条从知识到产品、从政策到社会影响的链条。"]},
            {"heading": "现实中的观察角度", "paragraphs": [f"看新闻或视频时，可以留意谁在定义问题、谁在提供解决方案、谁承担成本、谁获得收益。对于“{topic['title']}”，同一个变化可能被企业看成机会，被监管者看成风险，被普通人看成生活变化。不同立场不一定意味着谁在撒谎，但需要区分数据、判断和宣传。", "如果资料只讲成功案例，要主动寻找失败、限制条件和反例；如果资料只讲风险，也要看看它解决了什么真实问题。这样得到的理解会比单一叙事更接近真实情况。"]},
            {"heading": "争议与仍未解决的问题", "paragraphs": ["这类主题往往存在事实、解释和价值判断的混合。事实可以通过公开资料核对，解释需要比较多个来源，价值判断则与不同群体的利益和立场有关。阅读时不必急着选边，先把各方在争论什么、使用了什么证据、遗漏了什么条件看清楚。", "如果当天的热搜触发了这个主题，它更适合作为入口，而不是结论。热点会快速变化，真正值得保留的是背后的历史脉络、制度安排和长期问题。"]},
            {"heading": "看完今天的材料后", "paragraphs": [f"今天不要求你成为“{topic['title']}”的专家。完成文字阅读，再选择一段视频和一集播客，目标只是能用自己的话说明：它是什么、从哪里来、现在有哪些主要参与者、为什么会出现在公共讨论中。"]},
        ],
        "timeline": [{"label": "起点", "text": "形成早期问题或基础条件"}, {"label": "扩展", "text": "技术、制度或社会需求推动领域扩大"}, {"label": "转折", "text": "关键事件改变参与者与发展路径"}, {"label": "今天", "text": "进入现实生活并产生新的机会与争议"}],
        "chart": {"type": "flow", "title": "理解这个主题的四个入口", "items": ["概念：它是什么", "历史：怎么走到今天", "参与者：谁在推动", "争议：还没有共识什么"]},
    }
    # Keep the no-API path useful for a real reading session instead of a link list.
    current_chars = sum(len(p) for section in article["sections"] for p in section["paragraphs"])
    if current_chars < 1800:
        article["sections"].insert(-1, {"heading": "继续观察它的现实影响", "paragraphs": [f"围绕“{topic['title']}”，还可以从个人、组织和社会三个尺度来观察。个人层面是日常生活、工作和信息选择；组织层面是企业、学校、政府和媒体如何做决定；社会层面则是规则、资源和机会如何分配。三个尺度经常互相影响，单独看其中一个容易得到片面的结论。", "接下来浏览材料时，可以把具体例子放回这三个尺度。一个新产品可能先改变少数人的工作方式，再影响企业的成本，最后促使监管和教育制度调整。一个历史事件也可能先发生在局部地区，却因为交通、能源、贸易或信息传播而产生更广泛的后果。", "这也是为什么今天的主题不需要一次学到专业深度。先形成一套能够容纳新信息的框架，之后再遇到新闻、视频或播客时，就能知道它是在讲定义、历史、利益关系，还是在表达一种观点。"]})
        article["sections"][-2]["paragraphs"].append("阅读时还可以留意几个经常被忽略的条件：时间尺度、地理范围、参与者之间的信息差，以及一个方案从纸面走向现实需要付出的成本。很多争论表面上是在比较两个观点，实际上是在比较不同的目标、不同的时间范围和不同的承担风险的人。把这些条件说出来，往往比简单判断对错更能解释事情为什么会这样发展。")
        while sum(len(p) for section in article["sections"] for p in section["paragraphs"]) < 1800:
            article["sections"][-2]["paragraphs"].append("最后，可以把今天看到的内容与自己的生活经验连接起来：它是否影响了你使用的产品、获取的信息、工作的方式或对某个公共问题的看法？这种连接不是为了得出一个立即可执行的结论，而是为了让抽象概念有现实参照，也方便以后遇到新材料时判断它是在补充背景，还是只是在重复一个醒目的观点。")
    return article


def call_deepseek(topic: dict, reason: str, hot: list[dict]) -> dict | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    prompt = f"""你是中文知识编辑。请为普通读者写一篇关于“{topic['title']}”的背景导览，不是课程，不布置作业，也不要鼓励读者投资或进行医疗/政治行动。正文必须是中文，目标 5000-8000 个汉字，可以更长。\n\n必须覆盖：它是什么、历史发展、内部结构或主要参与者、现实案例、当前讨论、争议与不同观点。‘为什么重要’只能用一小段带过。\n\n请严格返回 JSON，不要 Markdown 代码围栏，字段为：overview（2-4段）、history（3-6段）、sections（6-8项，每项有 heading 和 paragraphs 数组）、timeline（4-8项，每项有 label 和 text）、chart（type 为 flow/timeline/compare 之一，title 和 items 数组）、disputes（可选字符串数组）。不要编造具体视频 URL；推荐材料只能使用下方已给出的 URL。\n\n主题资料：{json.dumps(topic, ensure_ascii=False)}\n选题线索：{reason}\n实时观察到的热点：{json.dumps(hot[:10], ensure_ascii=False)}"""
    body = {"model": "deepseek-v4-flash", "messages": [{"role": "system", "content": "你是严谨、清晰、偏中文的知识编辑。"}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 16000, "response_format": {"type": "json_object"}}
    try:
        req = Request("https://api.deepseek.com/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
        result = json.loads(urlopen(req, timeout=180).read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if parsed.get("sections") and parsed.get("overview") and parsed.get("history"):
            print("DeepSeek article generated successfully")
            return parsed
    except Exception as exc:
        print(f"DeepSeek unavailable, using fallback: {exc}")
    return None


def build_media(topic: dict) -> list[list[str]]:
    return topic.get("resources", [])


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo("Asia/Shanghai"))
    topics = json.loads(TOPICS.read_text(encoding="utf-8"))
    history = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else []
    hot = fetch_titles()
    topic, reason, observed = choose_topic(topics, history, hot)
    article = call_deepseek(topic, reason, observed) or fallback_article(topic)
    payload = {"date": now.date().isoformat(), "date_display": now.strftime("%Y年%m月%d日"), "generated_at": now.isoformat(timespec="seconds"), "article_mode": "deepseek" if os.environ.get("DEEPSEEK_API_KEY") and article.get("sections") != fallback_article(topic).get("sections") else "fallback", "selection_reason": reason, "hot_observed": observed[:10], "resources": build_media(topic), **topic, **article}
    DATA.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    TODAY.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ARCHIVE / f"{payload['date']}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    history = [x for x in history if x.get("date") != payload["date"]]
    history.insert(0, {"date": payload["date"], "date_display": payload["date_display"], "topic_id": payload["id"], "category": payload["category"], "title": payload["title"], "subtitle": payload["subtitle"], "article_mode": payload["article_mode"]})
    HISTORY.write_text(json.dumps(history[:365], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {TODAY} · {payload['date']} · {payload['title']} · {payload['article_mode']}")


if __name__ == "__main__":
    main()
