#!/bin/bash
# ==========================================================================
# VoiceNote Forge (声记工坊) Automated Deployment Script
# ==========================================================================
set -e

echo "=================================================="
echo "🚀 开始部署：声记工坊 (VoiceNote Forge) on Aliyun "
echo "=================================================="

# 1. Ensure required directories exist
echo "[+] 正在初始化数据和日志目录..."
mkdir -p logs data data/uploads data/outputs

# 2. Check and establish Python virtual environment (.venv)
if [ ! -d ".venv" ]; then
    echo "[+] 未检测到 .venv 目录，正在创建 Python 虚拟环境..."
    python3 -m venv .venv
    echo "[+] 虚拟环境创建成功。"
fi

# 3. Upgrade pip and install dependencies
echo "[+] 正在使用阿里云镜像安装/更新项目依赖包..."
.venv/bin/python3 -m pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
.venv/bin/pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
echo "[+] 依赖包安装完成。"

# 4. Copy systemd user service configuration
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
echo "[+] 正在配置 systemd 用户级别服务..."
mkdir -p "$USER_SYSTEMD_DIR"
cp voicenote.service "$USER_SYSTEMD_DIR/voicenote.service"

# 5. Reload systemd daemon and restart service
echo "[+] 正在重载 systemd 服务配置..."
systemctl --user daemon-reload
echo "[+] 正在启用并启动 voicenote 服务..."
systemctl --user enable voicenote.service
systemctl --user restart voicenote.service

# 6. Output current service status
echo "[+] 服务当前状态："
systemctl --user status voicenote.service --no-pager

echo ""
Write-Host() {
    echo -e "\033[36m$1\033[0m"
}
echo -e "\033[32m==================================================\033[0m"
echo -e "\033[32m🎉 部署成功！\033[0m"
echo -e "\033[32m==================================================\033[0m"
echo -e "💡 接下来请手动执行以下命令以完成 Nginx 反向代理配置："
echo -e "   \033[33msudo cp ~/MinuteArchivist/voicenote.conf /etc/nginx/conf.d/voicenote.conf\033[0m"
echo -e "   \033[33msudo nginx -t\033[0m"
echo -e "   \033[33msudo nginx -s reload\033[0m"
echo -e "=================================================="
