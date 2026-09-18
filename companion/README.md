# 本地陪伴角色（隐私优先原型）

这部分把“聊天记录蒸馏”和“游戏对话”放在玩家自己的 Windows 电脑上运行。真实聊天、蒸馏结果和 Ollama 请求都不上传到 GitHub。

## 数据边界

- `distill.py` 读取你主动导出的 CSV / JSONL / TXT；不会直接控制微信，也不会修改微信数据库。
- 手机号、证件号、银行卡号、邮箱和明显的密码/验证码会在送入本地模型前替换。
- `private_data/`、`exports/`、`.env` 和 SQLite 文件已被 `.gitignore` 排除。
- 生成角色必须经聊天双方同意；角色会明确声明自己是 AI 游戏角色，不冒充真人。

## 第一次使用

1. 安装并启动 Ollama，确认本地已有模型：

   ```powershell
   ollama list
   ollama pull qwen2.5:3b
   ```

2. 把双方同意使用的导出文件放在仓库之外，或放入被忽略的 `companion/exports/`。

3. 在项目根目录运行蒸馏（把昵称替换为导出文件中实际显示的名字）：

   ```powershell
   python .\companion\distill.py "D:\private\chat.csv" --target "Jocelyn"
   ```

4. 人工检查：

   - `companion/private_data/persona.json`
   - `companion/private_data/memories.jsonl`

   删除错误、过度私密或不希望游戏使用的内容。

5. 双击 `companion/start_companion.ps1`，或在 PowerShell 运行：

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\companion\start_companion.ps1
   ```

6. 另开一个 PowerShell，在项目根目录启动游戏：

   ```powershell
   python -m http.server 8888
   ```

   打开 `http://127.0.0.1:8888/`，点击右上角“对话”。

## 当前限制

GitHub Pages 是 HTTPS，而本地原型服务是 HTTP。浏览器会阻止线上页面直接访问本机 HTTP 服务，因此当前应通过 `http://127.0.0.1:8888/` 本地预览。成品阶段需要把同一 API 部署到受保护的 HTTPS 后端；原始聊天仍不应进入前端或公开仓库。
