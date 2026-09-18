# 本地运行与安全边界

本目录只包含程序和虚构示例。角色必须显示“AI 游戏角色，不是真人本人”。不要将微信、导出或人格文件上传到在线模型、GitHub 或静态网站。

## Windows 启动

需要 Python 3.10+、Ollama 和已下载的 `qwen2.5:3b`。不自动安装软件、不修改系统安全设置。

在项目根目录的 PowerShell 中运行：

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_DEBUG_LOG_REQUESTS = 'false'
$env:OLLAMA_NOPRUNE = 'true'
ollama serve
```

另开终端：

```powershell
.\companion\start_companion.ps1 -CheckOnly -Example
.\companion\start_companion.ps1 -Example
```

打开 `http://127.0.0.1:8888/`。`-Example` 允许在没有真实人格时使用公开示例；已有真实人格时默认读取真实人格。若出现 CUDA 内核兼容错误，追加 `-Cpu`，无需更改驱动或安全设置。CPU 推理更慢。运行策略阻止脚本时，可分别运行 `python companion/preview.py` 和 `python companion/server.py`，不要修改执行策略。

不要从仓库根目录运行普通 `python -m http.server`：它会把 Git 忽略的私人目录也当作静态资源提供。`preview.py` 只允许首页、固定角色图片和固定 Three.js 文件，且只监听回环地址。

## 单聊输入与蒸馏

程序不自动提取微信数据库。先通过经过确认的安全流程，仅导出双方一对一文本至 `companion/exports/`。不要将整库、群聊或多联系人混合导出交给本程序。

在被 Git 忽略的 `companion/private_data/config.json` 中填写：

```json
{"target":"示例昵称","self_name":"示例本人","confirmed_single_chat":true}
```

只有核实目标会话和双方发送者后才把确认值设为 true；昵称一致本身不能证明会话归属。程序用 Unicode 标准化后的精确匹配，遇到第三个发送者会拒绝处理。CSV 支持 sender/time/content 等中英文列名；JSONL 每行一个同样结构的对象；TXT 支持 `[2026-01-01 12:30] 示例昵称: 内容`、日期时间加昵称及 `昵称: 内容`。TXT 仅支持逐行消息，复杂多行或混合格式应先本机规范化，不要假设忽略行也已导出。

```powershell
$env:GZL_OLLAMA_CPU = '1' # 仅在 GPU 不可用时设置
python companion/distill.py companion/exports/chat.jsonl --config companion/private_data/config.json
```

先清洗，保存 `cleaned.jsonl`，再按消息数和字符数双重分块，通过本机模型进行分层合并。目标消息少于20条会停止。输出 `persona.json`、`memories.jsonl`，包括记忆置信度；限制字段、长度和列表规模，不接受过长原文复刻。JSON 解析失败最多重试三次；结构不合法时停止，不把无效结果投入运行。已存在私人输出时停止，不覆盖或删除；中断后由所有者先检查和归档，再重试。

## 隐私与安全审计

- API 固定监听 `127.0.0.1:8765`，只接受两个固定本地预览 Origin；拒绝 `null`、无 Origin、非法 Host、非 JSON、超长消息和超过16 KiB的请求。一次只处理一个模型请求。
- 模型请求固定指向 `127.0.0.1:11434`，不使用系统代理，不跟随重定向。可使用 CPU 模式。不要把模型名换成云端模型。
- 输入、模型摘要和回复均脱敏。规则覆盖常见手机号、邮箱、长号码、密码/验证码标记、常见 Token 和住址表达，但无法穷尽自然语言地址或刻意编码的秘密。
- 提示词将聊天、角色和记忆视为数据；拦截常见配置/记忆批量提取请求；只检索少量相关记忆。提示词和关键词拦截**不能证明彻底抵御 prompt injection**。不要把任何凭据或高敏感资料保留在人格或记忆中；本地恶意进程也不在 CORS 的隔离能力内。
- API 与预览不记录请求正文、URL 或模型输出；响应禁止缓存；前端对话只保存在内存，最多8条上下文和40个气泡，刷新即丢弃。游戏最高分仍按原逻辑保存。
- 前端只向固定回环 API 发送消息，拒绝重定向，CSP 限制网络；Three.js 0.160.0 随代码保存，附 MIT 许可证。聊天显示使用 textContent。
- `private_data/`、`exports/`、数据库及密钥文件被忽略。Git ignore 不会撤销已追踪文件，也不会防止 `git add -f`；提交前必须检查实际暂存文件。

## 地址配置与未来部署

本版端口集中在 `server.py`（8765）、`preview.py`（8888）与 `index.html` 的 `COMPANION_ENDPOINT` 和 CSP 中。修改端口需要同步修改严格的 Origin 白名单和这些常量。已移除浏览器 localStorage 任意地址覆盖，以防误发私人聊天。

GitHub Pages 的 HTTPS 页面连接本机 HTTP 会受到浏览器混合内容及本地网络访问策略影响；不同浏览器对回环地址有特殊规则，不能保证一概可用。本项目进一步主动禁止线上页面访问陪伴 API，使用本机 HTTP 预览是已测试路径。

未来线上服务需要真正的 HTTPS 私有后端、身份认证、授权、速率限制、严格 Origin、无正文日志和受保护存储。API 密钥不能放进 index.html：浏览器用户和脚本都能读取。后端的凭据应留在后端，绝不可打包进静态资源。

| 方案 | 隐私 | 费用与维护 |
| --- | --- | --- |
| 本机预览 + Ollama | 数据留本机，符合当前约束 | 无云推理账单；电脑需运行 |
| 自有设备 HTTPS 私有服务 | 需要认证和网络配置；远程访问需重新确认授权范围 | 维护证书、补丁、访问控制 |
| 云端私有服务 | 会上传人格/记忆，不符合当前“仅本机”授权 | 托管和推理费用、运维及日志风险 |

不要部署 `exports/`、`private_data/`、清洗结果、备份、SQLite、密钥、日志和本机配置。当前没有创建云资源、Secrets 或生产部署。

## 验证

```powershell
python -m py_compile companion/privacy.py companion/distill.py companion/server.py companion/preview.py
python -m unittest discover -s companion -v
git diff --check
git status --short --ignored
git diff --cached --name-only
```

浏览器回归使用 `companion/verify_browser.cjs`（需测试环境已有 Playwright）：检查桌面/手机、发送/失败/重试、输入隔离、开始/蓄力/落地/死亡/重开、前空翻和镜头边界。只允许虚构测试回复，不截图真实人格回复。测试输出目录由 `GZL_TEST_OUTPUT` 指定，默认在忽略目录中。
