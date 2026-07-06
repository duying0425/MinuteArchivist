import re
import datetime
from typing import List, Dict, Tuple
from jinja2 import Template

# 兼容两种转写格式：
# 1. 飞书妙记格式（speaker 后跟时间戳，内容在下一行）：
#    "说话人 1 00:00:01.700\n诶，邓老师。..."
# 2. 本地 ASR / 旧格式（方括号时间戳 + 冒号分隔）：
#    "[00:00:01] 说话人 1: 诶，邓老师。"
FEISHU_TRANSCRIPT_LINE_REGEX = re.compile(
    r"^(.+?)\s+(\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\s*$"
)
LEGACY_TRANSCRIPT_LINE_REGEX = re.compile(
    r"^\[(\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2})\]\s*(.*?)[：:]\s*(.*)$"
)

MARKDOWN_TEMPLATE = """# {{ title }}

- 来源文件：{{ filename }}
- 处理方式：{{ method }}
- 处理时间：{{ processed_at }}
- 音频时长：{{ duration }}
- 说话人数量：{{ speaker_count }}

---

## 一、会议概要

*提示：此版本为 MVP 阶段，暂未开启大模型智能摘要。您可以在此手动补充会议概要。*

---

## 二、关键结论

*提示：您可以在此整理会议达成的重要决议与关键结论。*

---

## 三、待办事项

| 序号 | 事项 | 负责人 | 截止时间 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 整理会议纪要并分发给团队 | {{ current_user }} | {{ today_str }} | 妙记归档员自动生成 |

---

## 四、原始发言记录

{% for item in items -%}
### {{ item.timestamp }} {{ item.speaker }}

{{ item.content }}

{% endfor %}"""

def parse_transcript_text(raw_text: str) -> List[Dict[str, str]]:
    """
    Parse a raw transcript text into structured paragraphs.
    支持两种格式：
    - 飞书妙记：'说话人 1 00:00:01.700\\n内容...'
    - 旧格式：'[00:00:01] 说话人 1: 内容...'
    连续非匹配行追加到当前说话人的 content。
    """
    lines = raw_text.splitlines()
    parsed_items = []

    current_item = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 优先尝试飞书妙记格式：'说话人名 HH:MM:SS[.mmm]'
        feishu_match = FEISHU_TRANSCRIPT_LINE_REGEX.match(line)
        if feishu_match:
            # 确认这不是普通文本误匹配（要求 speaker 部分不能为空，且整体不能太长）
            speaker_candidate = feishu_match.group(1).strip()
            if speaker_candidate and len(speaker_candidate) <= 50:
                if current_item:
                    parsed_items.append(current_item)
                current_item = {
                    "timestamp": feishu_match.group(2),
                    "speaker": speaker_candidate,
                    "content": ""
                }
                continue

        # 尝试旧格式：'[HH:MM:SS] 说话人: 内容'
        legacy_match = LEGACY_TRANSCRIPT_LINE_REGEX.match(line)
        if legacy_match:
            if current_item:
                parsed_items.append(current_item)
            current_item = {
                "timestamp": legacy_match.group(1),
                "speaker": legacy_match.group(2).strip(),
                "content": legacy_match.group(3).strip()
            }
            continue

        # 非匹配行：追加到当前说话人的内容
        if current_item:
            if current_item["content"]:
                current_item["content"] += "\n" + line
            else:
                current_item["content"] = line
        else:
            # 还没遇到任何说话人：作为头部文本丢弃，避免污染第一段发言
            continue

    if current_item:
        # 过滤掉空内容的 item（飞书格式末尾可能有多余的说话人标记）
        if current_item["content"]:
            parsed_items.append(current_item)

    # 如果整个文本完全没匹配到任何说话人，兜底返回原文作为未知说话人
    if not parsed_items:
        parsed_items.append({
            "timestamp": "00:00:00",
            "speaker": "未知说话人",
            "content": raw_text.strip()
        })

    return parsed_items

def generate_markdown(
    title: str,
    filename: str,
    method: str,
    duration_seconds: float,
    raw_text: str,
    speaker_map: Dict[str, str] = None,
    username: str = "当前用户"
) -> Tuple[str, int]:
    """
    Parses raw_text, applies speaker_map, and returns (markdown_content, unique_speaker_count).
    """
    if speaker_map is None:
        speaker_map = {}
        
    parsed_items = parse_transcript_text(raw_text)
    
    # Track unique speakers (both original and mapped)
    original_speakers = set()
    unique_speakers_mapped = set()
    
    # Map speakers
    mapped_items = []
    for item in parsed_items:
        orig_speaker = item["speaker"]
        original_speakers.add(orig_speaker)
        
        mapped_speaker = speaker_map.get(orig_speaker, orig_speaker)
        unique_speakers_mapped.add(mapped_speaker)
        
        mapped_items.append({
            "timestamp": item["timestamp"],
            "speaker": mapped_speaker,
            "content": item["content"]
        })
        
    speaker_count = len(original_speakers)
    
    # Format duration
    if duration_seconds:
        h = int(duration_seconds // 3600)
        m = int((duration_seconds % 3600) // 60)
        s = int(duration_seconds % 60)
        if h > 0:
            duration_str = f"{h}小时{m}分{s}秒"
        else:
            duration_str = f"{m}分{s}秒"
    else:
        duration_str = "未知"
        
    processed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # Render using Jinja2 Template
    tmpl = Template(MARKDOWN_TEMPLATE)
    markdown_content = tmpl.render(
        title=title,
        filename=filename,
        method="飞书妙记" if method == "feishu" else "本地 ASR",
        processed_at=processed_at,
        duration=duration_str,
        speaker_count=speaker_count,
        current_user=username,
        today_str=today_str,
        items=mapped_items
    )
    
    return markdown_content, speaker_count
