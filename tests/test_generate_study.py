"""Offline unit tests for the pure logic in scripts/generate_study.py."""
import datetime as dt
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_study as gs


class SplitTtsTextTest(unittest.TestCase):
    def test_short_text_is_single_chunk(self):
        self.assertEqual(gs.split_tts_text("你好。"), ["你好。"])

    def test_long_text_chunks_stay_within_limit(self):
        text = "这是一个句子。" * 100
        chunks = gs.split_tts_text(text)
        self.assertTrue(all(len(c) <= 145 for c in chunks))
        self.assertEqual("".join(chunks), text)

    def test_cuts_at_punctuation(self):
        text = "甲" * 100 + "。" + "乙" * 100
        chunks = gs.split_tts_text(text)
        self.assertEqual(chunks[0], "甲" * 100 + "。")

    def test_text_without_punctuation_is_hard_cut(self):
        text = "字" * 300
        chunks = gs.split_tts_text(text)
        self.assertTrue(all(len(c) <= 145 for c in chunks))
        self.assertEqual("".join(chunks), text)


class NarrationTextTest(unittest.TestCase):
    def test_joins_topic_and_sections(self):
        topic = {"title": "标题", "subtitle": "副标题"}
        article = {"overview": "概览", "sections": [{"heading": "小节", "paragraphs": ["第一段", " ", "第二段"]}]}
        text = gs.narration_text(topic, article)
        self.assertEqual(text, "标题。副标题。概览。小节。第一段。第二段")

    def test_overview_may_be_a_list(self):
        text = gs.narration_text({"title": "题"}, {"overview": ["段一", "段二"], "sections": []})
        self.assertEqual(text, "题。段一。段二")


class ChooseTopicTest(unittest.TestCase):
    TOPICS = [
        {"id": "a", "title": "主题A", "hot_terms": ["芯片"]},
        {"id": "b", "title": "主题B", "hot_terms": ["利率"]},
        {"id": "c", "title": "主题C", "publish_date": "2026-07-26", "hot_terms": []},
    ]

    def test_scheduled_topic_wins(self):
        topic, reason, _ = gs.choose_topic(self.TOPICS, [], [], today=dt.date(2026, 7, 26))
        self.assertEqual(topic["id"], "c")
        self.assertIn("按主题库安排发布", reason)

    def test_recent_topics_are_excluded(self):
        history = [{"topic_id": "a"}]
        topic, _, _ = gs.choose_topic(self.TOPICS[:2], history, [], today=dt.date(2026, 7, 1))
        self.assertEqual(topic["id"], "b")

    def test_hot_term_match_is_preferred(self):
        hot = [{"source": "测试", "title": "央行调整利率引发讨论"}]
        topic, reason, _ = gs.choose_topic(self.TOPICS[:2], [], hot, today=dt.date(2026, 7, 1))
        self.assertEqual(topic["id"], "b")
        self.assertIn("利率", reason)

    def test_same_day_choice_is_deterministic(self):
        first = gs.choose_topic(self.TOPICS[:2], [], [], today=dt.date(2026, 7, 1))
        second = gs.choose_topic(self.TOPICS[:2], [], [], today=dt.date(2026, 7, 1))
        self.assertEqual(first[0]["id"], second[0]["id"])


class MergeMp3ChunksTest(unittest.TestCase):
    @staticmethod
    def id3(body: bytes) -> bytes:
        size = len(body)
        synchsafe = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
        return b"ID3" + b"\x04\x00\x00" + synchsafe + body

    def test_keeps_first_header_and_strips_later_ones(self):
        first = self.id3(b"tag1") + b"FRAMES-A"
        second = self.id3(b"tag-two") + b"FRAMES-B"
        merged = gs.merge_mp3_chunks([first, second])
        self.assertEqual(merged, first + b"FRAMES-B")

    def test_parts_without_id3_pass_through(self):
        merged = gs.merge_mp3_chunks([b"\xff\xfbAAA", b"\xff\xfbBBB"])
        self.assertEqual(merged, b"\xff\xfbAAA\xff\xfbBBB")

    def test_large_synchsafe_size_is_decoded(self):
        body = b"x" * 300  # forces more than one synchsafe byte
        merged = gs.merge_mp3_chunks([b"\xff\xfbAAA", self.id3(body) + b"REST"])
        self.assertEqual(merged, b"\xff\xfbAAAREST")


class DecodeBytesTest(unittest.TestCase):
    def test_utf8_default(self):
        self.assertEqual(gs.decode_bytes("你好".encode("utf-8")), "你好")

    def test_charset_from_content_type(self):
        raw = "利率与货币政策".encode("gb18030")
        self.assertEqual(gs.decode_bytes(raw, "text/html; charset=GBK"), "利率与货币政策")

    def test_charset_from_meta_tag(self):
        raw = ('<html><head><meta charset="gbk"></head><body>' + "货币" + "</body>").encode("gb18030")
        self.assertEqual(gs.decode_bytes(raw), '<html><head><meta charset="gbk"></head><body>货币</body>')

    def test_gbk_fallback_without_declaration(self):
        raw = "纯正文没有声明编码，但仍然应该可读。".encode("gb18030")
        self.assertEqual(gs.decode_bytes(raw), "纯正文没有声明编码，但仍然应该可读。")


class StripCodeFencesTest(unittest.TestCase):
    def test_plain_json_untouched(self):
        self.assertEqual(gs.strip_code_fences('{"a": 1}'), '{"a": 1}')

    def test_json_fence_removed(self):
        self.assertEqual(gs.strip_code_fences('```json\n{"a": 1}\n```'), '{"a": 1}')

    def test_bare_fence_removed(self):
        self.assertEqual(gs.strip_code_fences('```\n{"a": 1}\n```'), '{"a": 1}')


class BuildFeedTest(unittest.TestCase):
    HISTORY = [
        {"date": "2026-07-26", "title": "标题 & 符号", "subtitle": "副标题", "category": "科技 · AI"},
        {"date": "2026-07-25", "title": "第二天", "subtitle": "说明", "category": "历史"},
    ]

    def test_feed_is_valid_xml_with_entries(self):
        feed = gs.build_feed(self.HISTORY, "2026-07-26T09:00:00+08:00", "https://example.org/site/")
        root = ET.fromstring(feed)
        ns = "{http://www.w3.org/2005/Atom}"
        entries = root.findall(f"{ns}entry")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].find(f"{ns}title").text, "标题 & 符号")
        self.assertEqual(entries[0].find(f"{ns}link").get("href"), "https://example.org/site/index.html?date=2026-07-26")

    def test_empty_history_still_valid(self):
        root = ET.fromstring(gs.build_feed([], "2026-07-26T09:00:00+08:00"))
        self.assertTrue(root.tag.endswith("feed"))


class PruneOldAudioTest(unittest.TestCase):
    def test_removes_only_expired_daily_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = Path(tmp)
            (audio_dir / "2026-07-01.mp3").write_bytes(b"old")
            (audio_dir / "2026-07-20.mp3").write_bytes(b"recent")
            (audio_dir / "intro.mp3").write_bytes(b"not-daily")
            original = gs.AUDIO
            gs.AUDIO = audio_dir
            try:
                removed = gs.prune_old_audio(dt.date(2026, 7, 26), keep_days=14)
            finally:
                gs.AUDIO = original
            self.assertEqual(removed, ["2026-07-01.mp3"])
            self.assertTrue((audio_dir / "2026-07-20.mp3").exists())
            self.assertTrue((audio_dir / "intro.mp3").exists())


if __name__ == "__main__":
    unittest.main()
