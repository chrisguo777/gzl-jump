# GZL 跳一跳 (gzl-jump)

> 一个「跳一跳」风格的小游戏，包含**两套独立实现**：一个自包含的 3D 等距网页版，和一个微信小程序 2D 横版。两者共用角色贴图 `gzl.png`，但**代码、玩法、坐标系完全不同**。

本文件同时面向人类与 AI 阅读助手，目标是让读者在不逐行通读代码的情况下，快速建立对项目结构、坐标系统与关键函数的准确认知。

---

## 1. 快速事实（TL;DR for AI）

| 项 | 网页版 | 小程序版 |
|---|---|---|
| 入口文件 | [`index.html`](index.html)（单文件，~1500 行，含内联 JS/CSS） | [`pages/game/game.js`](pages/game/game.js) 等 |
| 玩法维度 | 3D 等距（isometric），可选方向跳跃 | 2D 横版，自动向右 |
| 城市/关卡 | 12 座城市，各有地标剪影，随机地形 | 无城市概念，随机平台 |
| 渲染 | Canvas 2D + 一个覆盖在上方的 `<img>` 角色 | Canvas 2D（角色也画在 canvas 内） |
| 存档 | `localStorage`（键名 `jump3d_best`） | `wx.setStorageSync('gzl_best')` |
| 运行方式 | 浏览器直接打开，或本地静态服务器 | 微信开发者工具打开项目根目录 |
| 依赖 | 游戏本体无依赖；截图脚本需 Playwright | 微信小程序基础库 3.4.3 |

**两个版本互不依赖**。改一个不会影响另一个。修改前务必先确认目标是哪一版。

---

## 2. 文件结构

```
gzl-jump/
├── index.html            # 【网页版】3D 等距跳一跳，单文件自包含
├── images/gzl.png        # 角色贴图（网页版通过 <img src> 引用）
├── gzl.png               # 角色贴图副本（根目录，1.7MB，历史遗留）
├── verify_landmarks.js   # Playwright 截图辅助脚本（非自动断言测试）
├── companion/            # 本地聊天蒸馏与 Ollama 对话服务（不含真实数据）
│   ├── distill.py        # CSV/JSONL/TXT → persona + memories
│   ├── server.py         # 仅监听 127.0.0.1 的本地 API
│   └── start_companion.ps1
│
├── app.js                # 【小程序】全局入口（几乎为空）
├── app.json              # 小程序全局配置，pages 只注册 pages/game/game
├── app.wxss              # 全局样式
├── project.config.json   # 微信开发者工具配置（appid 当前为占位值）
├── sitemap.json          # 小程序 sitemap
├── pages/game/
│   ├── game.js           # 【小程序核心逻辑】Page({}) 全部游戏代码
│   ├── game.wxml         # 一个绑定触摸事件的 <canvas type="2d">
│   ├── game.wxss         # 全屏 canvas 样式
│   └── game.json         # 页面配置
│
└── Todolist              # 早期手写待办，部分内容已经过时
```

> 注：根目录 `gzl.png` 与 `images/gzl.png` 内容相同。网页版引用的是 `images/gzl.png`（见 `index.html` 中 `<img id="char-img" src="images/gzl.png">`）。

---

## 3. 网页版架构（`index.html`）

单文件，内联 `<script>` 中按注释分节组织。关键概念：

### 3.1 等距坐标系
- 世界坐标以**格子** `(col, row)` 表示。
- 投影到屏幕：
  ```js
  isoX(col,row) = (col - row) * (TILE_W/2)
  isoY(col,row) = (col + row) * (TILE_H/2)
  projectToScreen(col,row) → { x: W/2 + isoX - camIsoX, y: H*0.42 + isoY - camIsoY - TILE_Z }
  ```
- `TILE_W=96, TILE_H=48, TILE_Z=40`（基准值，按屏幕 `SCALE = min(W,H)/600` 缩放）。
- 相机跟随角色格子 `(camCol, camRow)`。

### 3.2 城市与确定性生成
- `CITIES[]`：12 座城市，每个含 `name / sky / glow / buildings / ground / accent` 配色。
- 用 **Lehmer 伪随机**（`seededRand`）+ `cityNameSeed(name)` 做**确定性生成**：同一城市每次布局/建筑一致。修改城市地形时注意别破坏 seed 的确定性。

### 3.3 渲染
- `drawCube(ctx, sx, sy, w, h, z, top, left, right)`：等距立方体三面绘制，是平台/建筑/地标的基本图元。
- 角色不是画在 canvas 里的，而是独立的 `#char-el`（`<img>`）用 CSS `transform` 定位在 canvas 之上（`mix-blend-mode:screen`）。改角色位置/动画要操作这个 DOM，不是 canvas。

### 3.4 验证脚本
- [`verify_landmarks.js`](verify_landmarks.js) 使用 Playwright 打开 `http://localhost:8888/index.html`，启动游戏并生成初始画面与推进画面截图。
- 该脚本目前只是**人工视觉检查辅助工具**：没有逐一进入 12 座城市，也没有像素对比或断言；脚本最后打印成功并不等于所有地标都已被自动验证。
- 当前“模拟 15 次跳跃”的实现使用普通 `click()` 加等待，并不能准确模拟按住蓄力再松开的操作。若把它升级为回归测试，需要改用明确的 `mouse.down()` / `mouse.up()` 或提供测试专用状态接口。
- 运行前需先启动静态服务器（见第 5 节），并安装 Playwright 及 Chromium：`npm i -D playwright && npx playwright install chromium`。

### 3.5 已实现功能
- 最高分会写入浏览器 `localStorage`，键名为 `jump3d_best`。
- 已使用 Web Audio API 实现 `jump`、`land`、`perfect`、`miss` 四类合成音效。
- 城市按分数推进，`Math.floor(score / 100) % CITIES.length` 决定当前城市。

### 3.6 本地陪伴角色原型
- 页面右上角提供独立聊天面板，不会把对话输入传给游戏画布。
- 默认请求 `http://127.0.0.1:8765/api/chat`，由 [`companion/server.py`](companion/server.py) 调用本机 Ollama。
- [`companion/distill.py`](companion/distill.py) 可将双方授权的 CSV、JSONL 或常见 TXT 导出记录，整理为 `persona.json` 与 `memories.jsonl`。
- 真实导出和蒸馏结果放在 `companion/exports/`、`companion/private_data/`，两者已被 `.gitignore` 排除，禁止提交到公开仓库。
- 详细运行步骤和当前 HTTPS 限制见 [`companion/README.md`](companion/README.md)。

---

## 4. 小程序版架构（`pages/game/game.js`）

整个游戏是一个 `Page({})` 对象，无外部依赖。核心状态机与函数：

### 4.1 状态机
`this.state ∈ { 'start', 'play', 'charge', 'dead' }`
- `start` → 点击 → `play`
- `play` 且角色在地面 → 按下 → `charge`（蓄力）
- `charge` → 松手 → `doJump()` → `play`
- 掉出屏幕 → `die()` → `dead` → （55 帧后）点击 → `reset()`

### 4.2 关键方法
| 方法 | 作用 |
|---|---|
| `initCanvas()` | 通过 `wx.createSelectorQuery` 取 canvas 节点，设 DPR，加载角色图后启动 `tick()` |
| `reset()` | 初始化物理、角色、平台数组 `plats[]`、粒子、读取最高分 |
| `addPlat()` | 在末尾追加一个随机 gap/高度/宽度的平台 |
| `onTouchStart/End` | 触摸驱动状态切换与蓄力计时 |
| `doJump()` | 依据 `chargeT`(0~1) 设定 `vx`(3~7.5)/`vy`(-7~-11) |
| `update()` | 每帧物理积分、`checkCollision()`、相机平滑跟随、按需生成平台 |
| `checkCollision()` | 只检测 `platIdx` 附近平台；落稳则加分、更新 `platIdx`、喷落地粒子 |
| `draw()` / `drawBg/Plats/Char/Parts/UI` | 分层绘制（背景视差、平台、粒子、角色、UI） |
| `die()` | 记录最高分到 `gzl_best`，喷死亡粒子 |
| `tick()` | `update()+draw()` 的 `requestAnimationFrame` 主循环 |

### 4.3 物理参数（调参入口）
- 重力 `G = 0.48`
- 蓄力满程 1800ms（`update()` 中 `chargeT = min(1, (now-chargeMs)/1800)`）
- 平台间距 `gap = 80~200`，宽 `65~130`，高差 `±35`

---

## 5. 如何运行

### 网页版（最简单）
直接用浏览器打开 [`index.html`](index.html) 即可游玩。

若角色图因浏览器本地文件（`file://`）安全策略不显示，用本地静态服务器：
```bash
# 任选其一，在项目根目录执行
python companion/preview.py
# 或
npx serve -l 8888
# 然后访问 http://localhost:8888/index.html
```
`verify_landmarks.js` 假定服务跑在 `8888` 端口。

### 小程序版
1. 安装「微信开发者工具」。
2. 用它「导入项目」，选择本仓库**根目录**。
3. `project.config.json` 中的 `appid` 当前是占位值 `wx0000000000000000`。请在微信开发者工具中选择适用的测试方式，或替换为自己的有效 AppID；真机预览和发布需要有效配置。

---

## 6. 给 AI 助手的注意事项

- **先确认版本**：用户说的「游戏」可能指网页版或小程序版，两者代码不共享。改动前先问清或从上下文判断。
- **网页版是单文件**：JS 内联在 `index.html`，无构建步骤，改完刷新即可。别去找不存在的 `src/` 或打包配置。
- **角色渲染差异**：网页版角色是 DOM `<img>`（`#char-el`），小程序版角色画在 canvas 里。别混。
- **确定性生成**：网页版城市用 seed 生成，改地形/建筑逻辑要保持同 seed 结果稳定，否则 `verify_landmarks.js` 的预期会变。
- **无测试框架**：目前只有 `verify_landmarks.js` 生成截图供人工检查，它不构成完整的自动化验证。
- **待办文件已过时**：`Todolist` 仍列有“音效”，但网页版音效已经实现。现阶段可确认的后续方向是：① 自动方向控制 ② 小程序版音效或两版音效统一 ③ 彩蛋 ④ 把截图脚本升级成真正的回归测试。

---

## 7. 许可 / 归属

个人小游戏项目，角色贴图 `gzl.png` 为项目自带资源。
