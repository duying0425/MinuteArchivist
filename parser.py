import re
import datetime
from typing import List, Dict, Tuple
from jinja2 import Template

# Regular expression to parse transcript lines: [HH:MM:SS] Speaker: Content or [MM:SS] Speaker: Content
TRANSCRIPT_LINE_REGEX = re.compile(
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
    Handles line combinations if some lines don't have timestamps (appends to previous speaker).
    """
    lines = raw_text.splitlines()
    parsed_items = []
    
    current_item = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        match = TRANSCRIPT_LINE_REGEX.match(line)
        if match:
            # If we had a previous item, save it
            if current_item:
                parsed_items.append(current_item)
                
            timestamp = match.group(1)
            speaker = match.group(2).strip()
            content = match.group(3).strip()
            
            current_item = {
                "timestamp": timestamp,
                "speaker": speaker,
                "content": content
            }
        else:
            # If line doesn't match the regex, it's either header text or continuous speaker content
            if current_item:
                current_item["content"] += "\n" + line
            else:
                # Discard or keep as initial speaker-less segment
                current_item = {
                    "timestamp": "00:00:00",
                    "speaker": "未知说话人",
                    "content": line
                }
                
    if current_item:
        parsed_items.append(current_item)
        
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
