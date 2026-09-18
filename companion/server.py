#!/usr/bin/env python3
"""Private local companion API backed by Ollama and distilled memory."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
PRIVATE = ROOT / "private_data"
MODEL = "qwen2.5:3b"
HOST = "127.0.0.1"
PORT = 8765
ALLOWED_ORIGINS = {"null", "http://127.0.0.1:8888", "http://localhost:8888"}


def load_json(path: Path, fallback: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def load_memories() -> list[dict]:
    memories = []
    try:
        for line in (PRIVATE / "memories.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                memories.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        pass
    return memories


def terms(text: str) -> set[str]:
    latin = re.findall(r"[a-z0-9]{2,}", text.lower())
    han = [text[i:i + 2] for i in range(len(text) - 1) if "\u4e00" <= text[i] <= "\u9fff" and "\u4e00" <= text[i + 1] <= "\u9fff"]
    return set(latin + han)


def retrieve(query: str, memories: list[dict], limit: int = 5) -> list[dict]:
    query_terms = terms(query)
    scored = []
    for memory in memories:
        corpus = str(memory.get("summary", "")) + " " + " ".join(memory.get("keywords", []))
        score = len(query_terms & terms(corpus))
        if score:
            scored.append((score, float(memory.get("confidence", 0)), memory))
    return [item[2] for item in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)[:limit]]


def ask_ollama(persona: dict, context: list[dict], history: list[dict], message: str) -> str:
    system = f"""你是游戏《跳一跳·城市之旅》中的陪伴角色。
角色配置：{json.dumps(persona, ensure_ascii=False)}
可能相关的共同记忆：{json.dumps(context, ensure_ascii=False)}
严格规则：你是受授权聊天材料启发的AI角色，不是真人本人；不得声称自己就是真人；只在相关时自然使用记忆；
没有依据时说不确定，绝不编造共同经历；不要输出密码、地址、证件号等敏感信息；默认回复1到3句。"""
    messages = [{"role": "system", "content": system}]
    for item in history[-8:]:
        if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
            messages.append({"role": item["role"], "content": item["content"][:800]})
    messages.append({"role": "user", "content": message[:1000]})
    body = json.dumps({"model": MODEL, "stream": False, "messages": messages, "options": {"temperature": 0.65}}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
            return str(result.get("message", {}).get("content", "暂时没有想好怎么回答。")).strip()
    except urllib.error.URLError as exc:
        raise RuntimeError("本地 Ollama 没有响应") from exc


class Handler(BaseHTTPRequestHandler):
    server_version = "GZLCompanion/0.1"

    def cors(self):
        origin = self.headers.get("Origin", "null")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")

    def send_json(self, status: int, value: dict):
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            persona_exists = (PRIVATE / "persona.json").exists()
            self.send_json(200, {"ok": True, "persona_ready": persona_exists, "model": MODEL})
        else:
            self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_json(404, {"error": "not_found"})
            return
        origin = self.headers.get("Origin", "null")
        if origin not in ALLOWED_ORIGINS:
            self.send_json(403, {"error": "origin_not_allowed"})
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 64_000)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            message = str(payload.get("message", "")).strip()
            if not message:
                self.send_json(400, {"error": "empty_message"})
                return
            persona = load_json(PRIVATE / "persona.json", load_json(ROOT / "persona.example.json", {}))
            memories = load_memories()
            context = retrieve(message, memories)
            reply = ask_ollama(persona, context, payload.get("history", []), message)
            self.send_json(200, {"reply": reply, "memory_count": len(context), "display_name": persona.get("display_name", "旅伴")})
        except (ValueError, json.JSONDecodeError):
            self.send_json(400, {"error": "invalid_request"})
        except RuntimeError as exc:
            self.send_json(503, {"error": "ollama_unavailable", "message": str(exc)})
        except Exception:
            self.send_json(500, {"error": "internal_error"})

    def log_message(self, fmt: str, *args):
        print("[companion]", fmt % args)


if __name__ == "__main__":
    print(f"GZL companion is listening at http://{HOST}:{PORT}")
    print("This server binds to this computer only. Press Ctrl+C to stop.")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
