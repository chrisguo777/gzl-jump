"""Shared local-only transport, redaction and schema checks. No private logging."""
import json
import os
import re
import urllib.request

NOTICE = 'AI 游戏角色，不是真人本人'
PATTERNS = [
    r'(?i)(?:password|passwd|密码|验证码|verification\s*code|api[_ -]?key|access[_ -]?token|token|secret|authorization)\s*(?:是|为|[:：=])?\s*[^\s，。；,;]+',
    r'(?i)(?:住址|地址|address)\s*[:：=]?[^\n，。；;]+',
    r'[\u4e00-\u9fff]{2,}(?:路|街|巷)\s*\d+号[^\s，。；;]*',
    r'(?i)\b(?:sk-[\w-]{12,}|gh[pousr]_[\w]{16,}|eyJ[\w-]+\.[\w-]+\.[\w-]+)\b',
    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
    r'(?<!\d)\d{17}[0-9Xx](?!\d)',
    r'(?<!\d)(?:\d[ -]?){13,19}(?!\d)',
    r'(?<!\d)(?:\+?86[ -]?)?1[3-9](?:[ -]?\d){9}(?!\d)',
    r'(?<!\d)\d{3}[- ]\d{3}[- ]\d{4}(?!\d)',
]
REDACT = [re.compile(p) for p in PATTERNS]

def redact(text):
    for pattern in REDACT:
        text = pattern.sub('[已移除]', text)
    return text

def scrub(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('本地模型不允许重定向')

def local_json(payload, timeout=180):
    if os.environ.get('GZL_OLLAMA_CPU') == '1':
        payload = dict(payload, options=dict(payload.get('options', {}), num_gpu=0))
    # Ignore system proxy settings; redirects cannot forward private request bodies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request('http://127.0.0.1:11434/api/chat',
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=timeout) as response:
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError('本地模型响应过大')
    return json.loads(data)

def validate_memory(m):
    if not isinstance(m, dict) or not isinstance(m.get('summary'), str) or not 1 <= len(m['summary']) <= 240:
        raise ValueError('记忆摘要格式错误')
    c = m.get('confidence')
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 1:
        raise ValueError('记忆置信度错误')
    words = m.get('keywords')
    if not isinstance(words, list) or len(words) > 8 or any(not isinstance(w, str) or len(w) > 40 for w in words):
        raise ValueError('记忆关键词格式错误')
    return {'summary': redact(m['summary']), 'keywords': scrub(words), 'confidence': c}

def validate_persona(p):
    if not isinstance(p, dict) or not isinstance(p.get('display_name'), str) or not 1 <= len(p['display_name']) <= 40:
        raise ValueError('角色名称格式错误')
    voice = p.get('voice')
    if not isinstance(voice, dict) or not isinstance(voice.get('tone'), list):
        raise ValueError('角色语气格式错误')
    result = {'display_name': redact(p['display_name']), 'identity_notice': NOTICE, 'voice': {}}
    for key in ('tone',):
        values = voice.get(key)
        if len(values) > 8 or any(not isinstance(v, str) or len(v) > 120 for v in values):
            raise ValueError('角色语气格式错误')
        result['voice'][key] = scrub(values)
    for key in ('typical_length', 'emoji_style'):
        v = voice.get(key)
        if not isinstance(v, str) or len(v) > 200:
            raise ValueError('角色习惯格式错误')
        result['voice'][key] = redact(v)
    for key in ('interaction_rules', 'favorite_patterns', 'avoid_patterns', 'comfort_style', 'humor_style', 'initiative_style'):
        v = p.get(key, [])
        if not isinstance(v, list) or len(v) > 12 or any(not isinstance(s, str) or len(s) > 160 for s in v):
            raise ValueError('角色规则格式错误')
        result[key] = scrub(v)
    return result
