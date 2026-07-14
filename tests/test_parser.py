"""
parser.py 单元测试。

覆盖：
- 飞书妙记格式解析（说话人在前 + 时间戳带毫秒 + 内容在下一行）
- 旧格式解析（[HH:MM:SS] 说话人: 内容，含 [MM:SS] 短时间戳）
- 多行内容追加、空输入、无匹配兜底
- generate_markdown 生成：标题/时长格式/说话人映射/计数/空转写
"""
from parser import parse_transcript_text, generate_markdown


# ==================== parse_transcript_text ====================

class TestParseFeishuFormat:
    """飞书妙记原生格式：'说话人 1 00:00:01.700\\n内容...'"""

    def test_single_segment(self):
        raw = "说话人 1 00:00:01.700\n诶，邓老师。"
        items = parse_transcript_text(raw)
        assert len(items) == 1
        assert items[0]["speaker"] == "说话人 1"
        assert items[0]["timestamp"] == "00:00:01.700"
        assert items[0]["content"] == "诶，邓老师。"

    def test_multiple_segments(self):
        raw = (
            "说话人 1 00:00:01.700\n你好\n"
            "说话人 2 00:00:05.200\n你好呀\n"
            "说话人 1 00:00:08.000\n再见"
        )
        items = parse_transcript_text(raw)
        assert len(items) == 3
        assert items[0]["speaker"] == "说话人 1"
        assert items[1]["speaker"] == "说话人 2"
        assert items[2]["speaker"] == "说话人 1"
        assert items[2]["content"] == "再见"

    def test_timestamp_without_milliseconds(self):
        raw = "张三 00:00:01\n内容一"
        items = parse_transcript_text(raw)
        assert items[0]["timestamp"] == "00:00:01"
        assert items[0]["speaker"] == "张三"

    def test_multiline_content(self):
        """同一说话人内容跨多行应被合并。"""
        raw = "说话人 1 00:00:01.000\n第一行\n第二行\n第三行"
        items = parse_transcript_text(raw)
        assert len(items) == 1
        assert items[0]["content"] == "第一行\n第二行\n第三行"

    def test_speaker_name_with_spaces(self):
        raw = "李 四 00:01:23.456\n内容"
        items = parse_transcript_text(raw)
        # 注意：'李 四' 整体作为 speaker（group 1 在时间戳之前）
        assert items[0]["speaker"] == "李 四"

    def test_empty_trailing_speaker_dropped(self):
        """末尾出现说话人标记但没有内容，应被过滤。"""
        raw = "说话人 1 00:00:01.000\n内容\n说话人 2 00:00:10.000"
        items = parse_transcript_text(raw)
        assert len(items) == 1
        assert items[0]["speaker"] == "说话人 1"


class TestParseLegacyFormat:
    """旧格式：'[HH:MM:SS] 说话人: 内容'"""

    def test_legacy_full_timestamp(self):
        raw = "[00:00:01] 说话人 1: 诶，邓老师。"
        items = parse_transcript_text(raw)
        assert len(items) == 1
        assert items[0]["timestamp"] == "00:00:01"
        assert items[0]["speaker"] == "说话人 1"
        assert items[0]["content"] == "诶，邓老师。"

    def test_legacy_short_timestamp(self):
        """[MM:SS] 短时间戳也应被支持。"""
        raw = "[01:23] 张三: 你好"
        items = parse_transcript_text(raw)
        assert len(items) == 1
        assert items[0]["timestamp"] == "01:23"
        assert items[0]["speaker"] == "张三"
        assert items[0]["content"] == "你好"

    def test_legacy_chinese_colon(self):
        """中文冒号 '：' 也应被识别。"""
        raw = "[00:00:05] 李四：你好"
        items = parse_transcript_text(raw)
        assert items[0]["speaker"] == "李四"
        assert items[0]["content"] == "你好"

    def test_legacy_multiple_segments(self):
        raw = (
            "[00:00:01] A: hi\n"
            "[00:00:10] B: hello\n"
            "[00:00:20] A: bye"
        )
        items = parse_transcript_text(raw)
        assert len(items) == 3
        assert items[2]["speaker"] == "A"


class TestParseEdgeCases:
    def test_empty_string(self):
        assert parse_transcript_text("") == [
            {"timestamp": "00:00:00", "speaker": "未知说话人", "content": ""}
        ]

    def test_only_whitespace(self):
        assert parse_transcript_text("   \n  \n") == [
            {"timestamp": "00:00:00", "speaker": "未知说话人", "content": ""}
        ]

    def test_no_speaker_fallback(self):
        """完全无说话人标记时，原文作为未知说话人内容。"""
        raw = "这是一段没有说话人标记的纯文本。"
        items = parse_transcript_text(raw)
        assert len(items) == 1
        assert items[0]["speaker"] == "未知说话人"
        assert items[0]["content"] == "这是一段没有说话人标记的纯文本。"

    def test_text_before_first_speaker_dropped(self):
        """第一个说话人之前的头部文本应被丢弃，不污染第一段发言。"""
        raw = "会议开始\n说话人 1 00:00:01.000\n正式内容"
        items = parse_transcript_text(raw)
        assert len(items) == 1
        assert items[0]["content"] == "正式内容"

    def test_speaker_candidate_too_long_not_matched(self):
        """speaker 部分超过 50 字符不应被误识别为飞书格式（避免误匹配长文本）。"""
        long_text = "这是一个非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的句子 00:00:01"
        items = parse_transcript_text(long_text)
        # 因为没有冒号分隔且 speaker 过长，整体作为未知说话人内容
        assert len(items) == 1
        assert items[0]["speaker"] == "未知说话人"


# ==================== generate_markdown ====================

class TestGenerateMarkdown:
    def test_basic_markdown_structure(self):
        raw = "说话人 1 00:00:01.000\n你好\n说话人 2 00:00:05.000\n你好呀"
        md, count = generate_markdown(
            title="测试会议",
            filename="test.wav",
            method="feishu",
            duration_seconds=10.0,
            raw_text=raw,
            speaker_map={},
            username="alice",
        )
        assert count == 2
        assert "# 测试会议" in md
        assert "来源文件：test.wav" in md
        assert "处理方式：飞书妙记" in md
        assert "说话人数量：2" in md
        assert "## 一、会议概要" in md
        assert "## 四、原始发言记录" in md
        assert "你好" in md
        assert "你好呀" in md

    def test_method_local_label(self):
        md, _ = generate_markdown("t", "f", "local", 0.0, "", {}, "u")
        assert "处理方式：本地 ASR" in md

    def test_speaker_map_applied(self):
        raw = "说话人 1 00:00:01.000\nhi\n说话人 2 00:00:02.000\nhello"
        md, _ = generate_markdown(
            "t", "f", "feishu", 0.0, raw,
            speaker_map={"说话人 1": "张三", "说话人 2": "李四"},
            username="u",
        )
        assert "张三" in md
        assert "李四" in md
        # 原始标签应被替换，不再出现
        assert "说话人 1" not in md
        assert "说话人 2" not in md

    def test_speaker_map_partial(self):
        """只映射部分说话人，未映射的保留原名。"""
        raw = "说话人 1 00:00:01.000\nhi\n说话人 2 00:00:02.000\nhello"
        md, _ = generate_markdown(
            "t", "f", "feishu", 0.0, raw,
            speaker_map={"说话人 1": "张三"},
            username="u",
        )
        assert "张三" in md
        assert "说话人 2" in md

    def test_duration_format_hours(self):
        md, _ = generate_markdown("t", "f", "feishu", 3661.0, "", {}, "u")
        assert "1小时1分1秒" in md

    def test_duration_format_minutes_seconds(self):
        md, _ = generate_markdown("t", "f", "feishu", 65.0, "", {}, "u")
        assert "1分5秒" in md

    def test_duration_zero_or_none(self):
        md, _ = generate_markdown("t", "f", "feishu", 0.0, "", {}, "u")
        assert "音频时长：未知" in md

    def test_username_in_todos(self):
        md, _ = generate_markdown("t", "f", "feishu", 0.0, "", {}, "alice")
        assert "alice" in md  # 出现在待办事项负责人列

    def test_empty_transcript(self):
        """空转写文本应仍能生成有效 markdown（兜底未知说话人）。"""
        md, count = generate_markdown("t", "f", "feishu", 0.0, "", {}, "u")
        assert "未知说话人" in md
        assert count == 1

    def test_speaker_count_distinct(self):
        """同一说话人多次发言只计一次。"""
        raw = (
            "A 00:00:01.000\nhi\n"
            "B 00:00:02.000\nhello\n"
            "A 00:00:03.000\nbye"
        )
        _, count = generate_markdown("t", "f", "feishu", 0.0, raw, {}, "u")
        assert count == 2
