#!/usr/bin/env python3
"""Locally turn an exported two-person chat into bounded persona + memories.

Only Python's standard library and a locally running Ollama are used. Raw chat
stays on the current computer. Supported inputs: CSV, JSONL and common TXT
lines such as "[2026-01-01 12:30] Name: message".
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SENSITIVE_PATTERNS = [
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号]"),
    (re.compile(r"(?<!\d)\d{15}(?:\d{2}[0-9Xx])?(?!\d)"), "[证件号]"),
    (re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)"), "[银行卡号]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[邮箱]"),
    (re.compile(r"(?i)(password|passwd|密码|验证码)\s*[:：]?\s*\S+"), r"\1：[已移除]"),
]

SENDER_KEYS = ("sender", "name", "talker", "from", "发送者", "昵称")
TEXT_KEYS = ("content", "text", "message", "msg", "内容", "消息")
TIME_KEYS = ("timestamp", "time", "datetime", "date", "时间", "日期")


def first_value(row: dict, keys: tuple[str, ...]) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def clean_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    for pattern, replacement in SENSITIVE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value[:1000]


def load_messages(path: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    rows: list[dict[str, str]] = []
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                rows.append({
                    "sender": first_value(row, SENDER_KEYS),
                    "time": first_value(row, TIME_KEYS),
                    "text": first_value(row, TEXT_KEYS),
                })
    elif suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                rows.append({
                    "sender": first_value(row, SENDER_KEYS),
                    "time": first_value(row, TIME_KEYS),
                    "text": first_value(row, TEXT_KEYS),
                })
    else:
        pattern = re.compile(
            r"^\s*(?:\[([^\]]+)\]|(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}[^\s]*\s+\d{1,2}:\d{2}(?::\d{2})?))?\s*([^:：]{1,40})[:：]\s*(.+)$"
        )
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            for line in handle:
                match = pattern.match(line.rstrip())
                if match:
                    rows.append({"time": match.group(1) or match.group(2) or "", "sender": match.group(3), "text": match.group(4)})

    cleaned = []
    for row in rows:
        text = clean_text(row.get("text", ""))
        sender = clean_text(row.get("sender", ""))
        if sender and text and text not in {"[图片]", "[视频]", "[表情]", "[语音]"}:
            cleaned.append({"sender": sender[:40], "time": row.get("time", "")[:40], "text": text})
    return cleaned


def ollama_json(model: str, system: str, prompt: str) -> dict:
    payload = json.dumps({
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "options": {"temperature": 0.15},
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError("无法连接 Ollama。请先运行 Ollama，并确认模型已经下载。") from exc
    content = result.get("message", {}).get("content", "{}")
    return json.loads(content)


def chunked(items: list[dict[str, str]], size: int = 180):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def reduce_partials(model: str, system: str, partials: list[dict]) -> list[dict]:
    """Hierarchically merge long histories so small local models keep context."""
    round_number = 1
    while len(partials) > 8:
        reduced = []
        batches = list(chunked(partials, 8))
        for index, batch in enumerate(batches, 1):
            prompt = f"""去重并压缩这些聊天风格摘要。只保留输入直接支持的内容。
输出对象：
{{"tone":[],"typical_phrases":[],"reply_habits":[],"emoji_habits":[],"boundaries":[],"memories":[{{"summary":"","keywords":[],"confidence":0.0}}]}}
每个列表最多8项，memories最多12项：
{json.dumps(batch, ensure_ascii=False)}"""
            print(f"正在合并长记录 第{round_number}轮 {index}/{len(batches)} ...")
            reduced.append(ollama_json(model, system, prompt))
        partials = reduced
        round_number += 1
    return partials


def main() -> int:
    parser = argparse.ArgumentParser(description="Local chat-to-companion distillation")
    parser.add_argument("input", type=Path, help="Exported .csv, .jsonl or .txt")
    parser.add_argument("--target", required=True, help="Name of the person whose style is distilled")
    parser.add_argument("--model", default="qwen2.5:3b", help="Local Ollama model")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "private_data")
    args = parser.parse_args()

    messages = load_messages(args.input)
    target_messages = [m for m in messages if args.target.lower() in m["sender"].lower()]
    if len(target_messages) < 20:
        print(f"可用的目标消息只有 {len(target_messages)} 条；请检查 --target 是否与导出昵称一致。", file=sys.stderr)
        return 2

    system = (
        "你是隐私优先的数据整理器。只总结可观察到的表达风格和双方共同经历；"
        "不得推断疾病、政治立场、宗教、性取向等敏感属性，不得保留密码、证件、精确住址或联系方式。"
        "输出必须是合法 JSON，不要 Markdown。"
    )
    partials = []
    total_chunks = (len(target_messages) + 179) // 180
    for index, chunk in enumerate(chunked(target_messages), 1):
        compact = "\n".join(f'{m["time"]} | {m["sender"]}: {m["text"]}' for m in chunk)
        prompt = f"""分析以下由 {args.target} 发送的消息片段。输出对象：
{{"tone":[],"typical_phrases":[],"reply_habits":[],"emoji_habits":[],"boundaries":[],"memories":[{{"summary":"","keywords":[],"confidence":0.0}}]}}
每个列表最多8项；memory只保留能从原文直接支持、适合日常对话的共同经历，confidence为0到1。
消息：
{compact}"""
        print(f"正在蒸馏 {index}/{total_chunks} ...")
        partials.append(ollama_json(args.model, system, prompt))

    partials = reduce_partials(args.model, system, partials)
    merge_prompt = f"""把这些分块总结合并为一个游戏对话角色配置。角色显示名为 {args.target}。
输出对象：
{{"display_name":"","identity_notice":"这是依据双方授权材料生成的游戏角色，不是真人本人。","voice":{{"tone":[],"typical_length":"","emoji_style":""}},"interaction_rules":[],"favorite_patterns":[],"avoid_patterns":[],"memories":[{{"summary":"","keywords":[],"confidence":0.0}}]}}
去重；不得添加输入中没有的事实；interaction_rules必须包含不冒充真人、不编造记忆、不泄露敏感信息。
分块总结：
{json.dumps(partials, ensure_ascii=False)}"""
    merged = ollama_json(args.model, system, merge_prompt)
    memories = merged.pop("memories", [])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "persona.json").write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    with (args.output / "memories.jsonl").open("w", encoding="utf-8") as handle:
        for memory in memories:
            if isinstance(memory, dict) and memory.get("summary"):
                handle.write(json.dumps(memory, ensure_ascii=False) + "\n")
    print(f"完成：{args.output.resolve()}")
    print("原始聊天没有被复制到输出目录。请人工检查 persona.json 和 memories.jsonl 后再启用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
