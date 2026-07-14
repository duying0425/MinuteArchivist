# 妙记归档员 (MinuteArchivist)

妙记归档员（MinuteArchivist）是一个结合了本地 ASR（更快、更轻量化的高精度 Whisper 语音识别）与**飞书妙记自动归档与通知系统**的会议纪要管理平台。支持通过飞书视频会议录制事件触发自动转写，并由飞书机器人推送交互式 Markdown 纪要下载卡片。

---

## 🌟 核心特性
1. **飞书一键快捷登录**：用户无需繁琐的账号密码注册，直接使用飞书扫码/授权登录，系统自动完成账号绑定并完成登录。
2. **全自动 Webhook 转写与推送**：在飞书会议中开启录制，或手动在飞书妙记上传音频后，系统自动触发拉取转写，生成 Markdown 结构文档，并由飞书机器人通过消息卡片直接推送下载链接给用户。
3. **说话人映射人机修正**：在网页端工作区，用户可以轻松将自动识别的“说话人 1”等名称批量重命名（如“张三”），系统会即时重新编译生成包含精美排版的 Markdown 文件。
4. **本地 ASR 高精度识别（备选）**：集成本地 `faster-whisper` 模型。当不使用飞书或在离线环境下，支持手动上传音频在服务器本地完成语音识别与转写。

---

## 💡 用户使用手册 (User Guide)

### 1. 首次使用与飞书账号绑定
- 访问妙记归档员主页，点击 **“飞书一键快捷登录”** 按钮。
- 在弹出的飞书授权页面进行登录与同意授权。
- 授权成功后，弹窗将自动关闭，系统在后台为您**自动注册本地账户并绑定您的飞书 OpenID**，直接进入 Dashboard 主页面。
- *（备选）如果您处于没有外网或没有飞书授权的局域网环境，可以切换至表单的“注册/登录”选项卡，创建并使用传统的本地账号密码。*

### 2. 飞书妙记全自动接收与卡片推送
- 绑定完成后，日常工作流不需要打开妙记归档员网页：
  1. 在飞书中发起视频会议录制，或在飞书妙记网页端手动上传本地音频文件进行识别。
  2. 飞书识别完成后，妙记归档员后台会收到 Webhook 自动触发转写拉取，将其整理为结构化的 Markdown 笔记格式。
  3. 飞书应用机器人会自动在飞书客户端给您发送一条**“🎙️ 会议录制已自动转写编译”**的交互式卡片消息。
  4. 点击卡片上的 **「📥 下载 Markdown 会议纪要」** 按钮，即可一键下载已排版好的 `.md` 文件。

### 3. 人工修正说话人姓名
- 在飞书机器人推送的卡片或妙记归档员网页端任务队列中，点击对应任务进入 **Workspace 工作区**。
- Left panel 会列出当前音频检测到的所有独立说话人（如：`说话人 1`，`说话人 2`）。
- 可以在右侧输入框中填入该人真实的姓名或代号（如：`张三`，`李四`），点击保存。
- 系统会在后台即时重新编译生成最终的 Markdown，并可直接在右侧实时预览和点击“下载 MD 文件”。

### 4. 本地 ASR 备选转写
- 如果遇到涉密音频不能上传到飞书，或者飞书授权异常：
  1. 打开妙记归档员主面板，左侧选择 **“本地 ASR”** 标签页。
  2. 拖拽或浏览上传本地音频文件（支持 mp3, wav, m4a, aac, mp4，最大 100MB）。
  3. 点击 **“开始本地转写”**，服务器将使用本地 Whisper 模型进行识别。
  4. 识别完成后，可在任务列表中以相同的方式进行“说话人映射”修改 and 下载。

---

## 🚀 本地开发与启动

在本地 Windows 环境下，直接通过 PowerShell 运行快速启动脚本即可自动创建虚拟环境、安装依赖并启动服务：

```powershell
./run.ps1
```
服务将在本地 `http://127.0.0.1:8000` 启动，并自动挂载 Glassmorphism 极客科技感的前端单页应用。

---

## 🧪 测试

项目内置完整的单元测试与 API 集成测试套件（基于 pytest + FastAPI TestClient），覆盖核心业务逻辑与全部 API 端点。

### 测试依赖

测试依赖独立管理在 [requirements-dev.txt](requirements-dev.txt) 中，不污染生产依赖：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### 运行测试

在项目根目录执行：

```powershell
# 运行全部测试
.venv\Scripts\python.exe -m pytest tests/

# 运行单个测试文件
.venv\Scripts\python.exe -m pytest tests/test_parser.py

# 显示详细输出
.venv\Scripts\python.exe -m pytest tests/ -v
```

### 测试覆盖范围

| 测试文件 | 用例数 | 覆盖内容 |
| :--- | :---: | :--- |
| `tests/test_parser.py` | 25 | 飞书妙记格式解析、旧格式解析、空输入兜底、多行内容合并、Markdown 生成、说话人映射、时长格式化 |
| `tests/test_auth.py` | 7 | bcrypt 密码哈希与校验、JWT 签发/解码/过期校验 |
| `tests/test_feishu.py` | 12 | minute_token 提取、OAuth URL scope 约束、机器人卡片消息 payload 构造 |
| `tests/test_api_auth.py` | 15 | 注册/登录/获取当前用户/飞书绑定 URL/解绑 |
| `tests/test_api_tasks.py` | 31 | 任务 CRUD、下载、说话人映射重编译、权限隔离、公共下载、文件名安全化 |
| `tests/test_api_webhook.py` | 11 | URL Verification 握手、录制就绪/妙记生成事件分发、无绑定用户忽略 |
| `tests/test_api_misc.py` | 8 | ASR 状态、静态首页、版本号注入、`no-store` 缓存头 |
| **合计** | **109** | 全部通过 ✅ |

### 测试设计要点

- **内存数据库隔离**：[tests/conftest.py](tests/conftest.py) 在导入项目模块前将 `DATABASE_URL` 设置为共享内存 SQLite，并 patch `sqlalchemy.create_engine` 使用 `StaticPool`，确保测试完全不污染真实 `data/` 目录。
- **后台任务 Mock**：通过 autouse fixture 自动 patch `process_feishu_task` / `process_local_task`，避免触发真实飞书 API 或本地 ASR 外部调用。
- **临时目录隔离**：`isolated_dirs` fixture 将 `OUTPUT_DIR` / `UPLOAD_DIR` 重定向到 pytest 的 `tmp_path`，测试产物自动清理。
- **Webhook 事件捕获**：monkeypatch `BackgroundTasks.add_task` 捕获事件分发调用，验证事件路由逻辑而不实际执行后台任务。
- **关键约束验证**：测试覆盖了 [project_memory](.trae-cn/memory) 中记录的硬约束，包括 OAuth scope 必含三项权限、静态资源 `Cache-Control: no-store`、下载文件名非法字符替换等。

---

## 🌐 阿里云生产环境部署指南

妙记归档员在云端作为**系统后台服务 (Systemd User Service)** 运行，并通过 **Nginx 反向代理** 结合 **Cloudflare CDN/SSL** 暴露安全 HTTPS 公网链接。

### 第一步：代码拉取与基础部署

1. **拉取代码**：
   在阿里云服务器的个人家目录下执行：
   ```bash
   git clone git@github.com:duying0425/MinuteArchivist.git ~/MinuteArchivist
   ```
2. **执行自动化部署脚本**：
   ```bash
   cd ~/MinuteArchivist
   chmod +x deploy.sh
   ./deploy.sh
   ```
   *该脚本会自动初始化数据与日志目录、创建 Python 虚拟环境、配置清华源 PyPI 镜像高速安装依赖、生成并开启用户级系统服务 `voicenote.service`（绑定在 `127.0.0.1:8090`）。*

---

### 第二步：Nginx 反向代理与热重载

运行以下命令将妙记归档员的 Nginx 配置文件复制到系统配置目录，并重载 Nginx 服务：

```bash
# 1. 复制配置文件
sudo cp ~/MinuteArchivist/voicenote.conf /etc/nginx/conf.d/voicenote.conf

# 2. 检查 Nginx 配置语法
sudo nginx -t

# 3. 热重载 Nginx 使其生效
sudo nginx -s reload
```

---

### 第三步：Cloudflare (CF) 子域名解析

在您的 Cloudflare 域名控制台中，添加如下解析以开启免费 SSL 证书及代理加速：

- **解析类型 (Type)**：`CNAME` 或 `A`
- **解析名称 (Name)**：`voice` （指向子域名 `voice.tmhcorps.cn`）
- **解析目标 (Target / IP)**：指向您的阿里云服务器（可参考 `pm.tmhcorps.cn` 记录）
- **代理状态 (Proxy status)**：**已代理 (Proxied / 开启黄色小云朵)**

---

### 第四步：配置应用环境变量 `.env`

项目依赖 `.env` 存储敏感的安全配置。请在阿里云服务器的 `~/MinuteArchivist/` 目录下创建 `.env` 文件：

```bash
nano ~/MinuteArchivist/.env
```

填入并修改以下内容：

```env
# 飞书应用凭证 (在飞书开放平台后台获取)
FEISHU_APP_ID=您的飞书AppID_cli_xxxxxx
FEISHU_APP_SECRET=您的飞书AppSecret_xxxxxx
# 飞书回调地址 (必须在飞书安全设置中配置，用于OAuth绑定与飞书一键快捷登录)
FEISHU_REDIRECT_URI=https://voice.tmhcorps.cn/api/auth/feishu/callback

# JWT 安全密钥 (自定义一个较长的随机安全字符串)
SECRET_KEY=yoursecretkeyhere_minute_archivist_2026

# 数据库文件路径 (保持默认即可)
DATABASE_URL=sqlite:///./data/minute_archivist.db
```

保存退出后，**重启后台服务**使配置生效：
```bash
systemctl --user restart voicenote.service
```

---

### 第五步：飞书开放平台开发者后台配置

登录 [飞书开放平台](https://open.feishu.cn/) 控制台，进入您的自建应用中进行如下设置：

1. **安全设置 (Security Settings)**：
   - 找到 **“安全设置”**，在 **“重定向 URL (Redirect URL)”** 输入框中添加：
     `https://voice.tmhcorps.cn/api/auth/feishu/callback`
     *(注：该回调路径同时用于支持“用户账号一键快捷登录”与登录后的“飞书账号绑定”流程)*
2. **事件订阅 (Event Subscription)**：
   - 配置 **“请求网址 (Request URL)”** 为：
     `https://voice.tmhcorps.cn/api/feishu/events`
     *(配置填写并点击保存时，飞书服务器会自动向我们的服务发送 Webhook challenge 握手验证，妙记归档员会自动处理并秒过验证)*
   - **添加事件订阅**（核心推荐订阅以下两个事件）：
     - **「妙记生成事件」** (`minutes.minute.generated_v1`)：**【强烈推荐】** 不论是通过会议自动录制，还是**手动在飞书妙记中上传音视频文件**生成的妙记，均会触发该事件，本系统已原生适配此直接推送通道！
     - **「录制就绪事件」** (`vc.meeting.recording_ready_v1`)：【可选】用于保障常规视频会议录制归档。
3. **权限管理 (Permissions/Scopes)**：
   - 进入 **"开发配置" -> "权限管理"**，**搜索关键词用 "妙记" 或 "minutes"（不要用 "meeting"）**，搜索并开通以下核心接口权限：
     - **飞书妙记（必选）**：
       - `minutes:minutes.basic:read`（获取妙记基本信息，用于通过 minute_token 查询妙记元数据）
       - `minutes:minutes.transcript:export`（导出妙记转写的文字内容，用于下载逐字稿，**这是核心权限，缺失会报错 99991679 / 20027**）
     - **即时消息 (机器人卡片)**：`im:message` （给用户发送单聊卡片消息）、`im:message:send_as_bot` （以应用身份发送消息）
     - **视频会议 (会议录制)**：`vc:meeting` （获取会议录制信息，配合会议事件使用）
   - ⚠️ **权限名易错点提醒**：飞书的妙记权限域是 `minutes:minutes.*`（**双 s**），不是 `minutes:minute.*`（单数）。错误码 99991679 / 20027 报错信息里写的 `minutes:minute:download` 实际并不存在，飞书后台可开通的是 `minutes:minutes.transcript:export`。
4. **机器人开启 (Bot)**：
   - 进入 **"应用功能" -> "机器人"**，点击开启机器人功能（卡片消息由该机器人推送）。
5. **应用版本发布（关键步骤，不开通权限不生效）**：
   - 权限申请与事件订阅配置好后，进入 **"版本管理与发布"** 创建版本，申请发布（自建应用可由管理员直接秒批，测试阶段也可以先将您的账号加入测试账号列表进行联调测试）。
   - ⚠️ **权限开通后必须发布新版本才会生效**，仅在权限管理页勾选是不够的。
6. **用户重新授权（关键步骤，旧 token 不带新权限）**：
   - 应用版本发布后，**已经绑定飞书的旧用户 access_token 仍然没有新权限**，必须让用户重新走 OAuth 流程换取新 token：
     1. 登录妙记归档员主页，进入账号绑定页面
     2. 解绑飞书账号
     3. 重新点击「绑定飞书账号」
     4. 授权页这次会显示要获取「导出妙记转写文字内容」权限，用户点同意后才能拿到带新 scope 的 token
   - 完成后才能正常贴入飞书妙记链接下载逐字稿，否则会持续报错 99991679 / 20027。

---

## 🛠️ 后台服务维护指令

您可以使用以下命令对部署在阿里云上的 `voicenote` 服务进行状态监控与管理：

- **查看服务运行状态**：
  ```bash
  systemctl --user status voicenote.service
  ```
- **查看应用实时日志**：
  ```bash
  tail -f ~/MinuteArchivist/logs/app.log
  ```
- **重启服务**：
  ```bash
  systemctl --user restart voicenote.service
  ```
- **停止服务**：
  ```bash
  systemctl --user stop voicenote.service
  ```

---

## 🔧 故障排查 (Troubleshooting)

### 1. 飞书妙记导出失败：错误码 99991679 / 20027

**报错信息示例**：
```
飞书妙记导出失败: Unauthorized. You do not have permission to perform the requested operation on the resource.
Please request user re-authorization and try again.
required one of these privileges under the user identity: [minutes:minute:download, minutes:minutes.transcript:export]
应用未获取所需的用户授权：[minutes:minute:download, minutes:minutes.transcript:export] (错误码: 99991679)
```

**根因**：飞书 OAuth 授权的 access_token 没有妙记导出权限。

**解决步骤**（必须按顺序完成）：
1. **飞书开发者后台开通权限**：进入应用 → 开发配置 → 权限管理，搜索 "妙记" 或 "minutes"，开通 `minutes:minutes.basic:read` 和 `minutes:minutes.transcript:export`。
   - ⚠️ 报错信息里的 `minutes:minute:download` 这个权限名**实际上不存在**，是飞书错误信息里的误导，飞书后台可开通的正确权限名是 `minutes:minutes.transcript:export`（注意是双 `s`）。
2. **发布新版本**：进入「版本管理与发布」创建版本并发布，权限才会生效。
3. **用户重新授权**：旧 token 没有新权限，必须解绑飞书账号后重新绑定，走一遍 OAuth 流程换取带新 scope 的 token。

### 2. 网页下载文件名错误（显示"妙记归档员会议记录.md"）

**根因**：通常是浏览器或 CDN（如 Cloudflare）缓存了旧版静态资源 `app.js`。

**自动解决方案（已实现）**：项目已集成 **Cache Busting 自动化机制** - 服务启动时读取 git commit hash，自动注入到 `index.html` 的静态资源 URL（如 `app.js?v=9ae1a33`）。每次部署新代码 commit hash 变化 → URL 变化 → CDN 视为新文件不命中旧缓存。

**手动排查步骤**（如果仍不生效）：
1. F12 → Network → 点击 download 请求，查看 Response Headers
2. 检查 `Cf-Cache-Status` 字段：如果是 `HIT` 且 `Age` 较大，说明 Cloudflare 命中了旧缓存
3. 登录 Cloudflare 后台 → Caching → Configuration → Purge Cache → Purge Everything
4. 强制刷新浏览器（Ctrl+Shift+R）

### 3. Markdown 预览加载失败 / 下载接口报 500

**根因**：`main.py` 中使用了 `re.sub()` 生成安全文件名，但缺少 `import re`。

**解决方案**：确保 `main.py` 顶部有 `import re`（已修复）。

### 4. 说话人映射 UI 显示"未找到明显的说话人标记"

**根因**：飞书妙记返回的转写格式与 parser 的正则不匹配。

**飞书妙记实际格式**（parser 已支持）：
```
说话人 1 00:00:01.700
说话人 1 的发言内容...

说话人 2 00:00:15.200
说话人 2 的发言内容...
```

**注意**：飞书的格式是「说话人在前 + 时间戳带毫秒 + 内容在下一行」，与传统的 `[00:00:01] 说话人: 内容` 格式不同。`parser.py` 已同时支持两种格式。

### 5. 部署后浏览器未生效新代码

**根因**：CDN 或浏览器缓存了旧版 JS/CSS。

**自动机制**：项目使用 git commit hash 作为静态资源版本号（cache busting），URL 形如 `app.js?v=<git-hash>`，每次部署自动变化。

**手动操作**：通常普通刷新（Ctrl+R）即可，因为 `index.html` 配置了 `Cache-Control: no-store`。如果 CDN 仍命中旧缓存，需要在 Cloudflare 后台手动清缓存。

---

## 📝 部署后维护注意事项

### 静态资源缓存策略

项目使用 **Cache Busting 自动化机制** 管理静态资源缓存：

- **机制**：服务启动时读取 git commit hash，注入到 `index.html` 的静态资源 URL（如 `app.js?v=9ae1a33`）
- **目的**：每次部署新代码，URL 自动变化，CDN 和浏览器视为新文件，不命中旧缓存
- **配置位置**：
  - [main.py](main.py) 中的 `_get_app_version()` 和 `_render_index_html()` 函数
  - [static/index.html](static/index.html) 中的 `?v=__APP_VERSION__` 占位符
- **维护**：无需手动改版本号，每次 `git pull` + 重启服务即自动生效

### 修改飞书权限后的必要操作

如果在飞书开发者后台修改了应用权限（新增/删除 scope），必须：
1. 发布新版本（版本管理与发布 → 创建版本 → 申请发布）
2. 通知所有已绑定用户重新授权（解绑后重新绑定飞书账号）

否则旧 access_token 仍带旧 scope，新权限不会生效。
