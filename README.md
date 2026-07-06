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
   - 进入 **“开发配置” -> “权限管理”**，搜索并开通以下核心接口权限：
     - **飞书妙记**：`minutes:minute` / `minutes:minute:readonly` （获取、修改妙记信息及下载/导出逐字稿）
     - **即时消息 (机器人卡片)**：`im:message` （给用户发送单聊卡片消息）、`im:message:send_as_bot` （以应用身份发送消息）
     - **视频会议 (会议录制)**：`vc:meeting` （获取会议录制信息，配合会议事件使用）
4. **机器人开启 (Bot)**：
   - 进入 **“应用功能” -> “机器人”**，点击开启机器人功能（卡片消息由该机器人推送）。
5. **应用版本发布**：
   - 权限申请与事件订阅配置好后，进入 **“版本管理与发布”** 创建版本，申请发布（自建应用可由管理员直接秒批，测试阶段也可以先将您的账号加入测试账号列表进行联调测试）。

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
