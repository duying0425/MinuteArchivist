# 声记工坊 (VoiceNote Forge)

声记工坊（VoiceNote Forge）是一个结合了本地 ASR（更快、更轻量化的高精度 Whisper 语音识别）与**飞书妙记自动归档与通知系统**的会议纪要管理平台。支持通过飞书视频会议录制事件触发自动转写，并由飞书机器人推送交互式 Markdown 纪要下载卡片。

---

## 🚀 本地开发与启动

在本地 Windows 环境下，直接通过 PowerShell 运行快速启动脚本即可自动创建虚拟环境、安装依赖并启动服务：

```powershell
./run.ps1
```
服务将在本地 `http://127.0.0.1:8000` 启动，并自动挂载 Glassmorphism 极客科技感的前端单页应用。

---

## 🌐 阿里云生产环境部署指南

声记工坊在云端作为**系统后台服务 (Systemd User Service)** 运行，并通过 **Nginx 反向代理** 结合 **Cloudflare CDN/SSL** 暴露安全 HTTPS 公网链接。

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

运行以下命令将声记工坊的 Nginx 配置文件复制到系统配置目录，并重载 Nginx 服务：

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
2. **事件订阅 (Event Subscription)**：
   - 配置 **“请求网址 (Request URL)”** 为：
     `https://voice.tmhcorps.cn/api/feishu/events`
     *(配置填写并点击保存时，飞书服务器会自动向我们的服务发送 Webhook challenge 握手验证，声记工坊会自动处理并秒过验证)*
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
   - 权限申请和事件订阅配置好后，进入 **“版本管理与发布”** 创建版本，申请发布（自建应用可由管理员直接秒批，测试阶段也可以先将您的账号加入测试账号列表进行联调测试）。

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
