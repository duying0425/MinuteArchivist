# VoiceNote Forge (声记工坊) 启动脚本

$Host.UI.RawUI.WindowTitle = "声记工坊 - VoiceNote Forge"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   声记工坊 (VoiceNote Forge) 正在初始化启动...   " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Check if .venv exists
if (!(Test-Path ".venv")) {
    Write-Host "[!] 未检测到 .venv 本地虚拟环境目录，正在尝试创建..." -ForegroundColor Yellow
    C:\Users\duyin\AppData\Local\Python\pythoncore-3.14-64\python.exe -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] 虚拟环境创建失败！请检查 Python 安装与权限。" -ForegroundColor Red
        Exit 1
    }
    Write-Host "[+] 虚拟环境创建成功，正在安装项目依赖包..." -ForegroundColor Green
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\pip install -r requirements.txt
}

# Create required folders
if (!(Test-Path "data")) { New-Item -ItemType Directory -Path "data" -Force | Out-Null }
if (!(Test-Path "data\uploads")) { New-Item -ItemType Directory -Path "data\uploads" -Force | Out-Null }
if (!(Test-Path "data\outputs")) { New-Item -ItemType Directory -Path "data\outputs" -Force | Out-Null }

Write-Host ""
Write-Host "[+] 本地服务运行说明:" -ForegroundColor Green
Write-Host "  👉 网页访问入口 : http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "  👉 API 交互文档 : http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "[*] 提示: 对接真实飞书应用，请在根目录创建 .env 并填写自建应用参数:" -ForegroundColor Yellow
Write-Host "    FEISHU_APP_ID=cli_xxxxxxxxxxxx" -ForegroundColor Gray
Write-Host "    FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx" -ForegroundColor Gray
Write-Host "    FEISHU_REDIRECT_URI=http://127.0.0.1:8000/api/auth/feishu/callback" -ForegroundColor Gray
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Run FastAPI Web server
& .\.venv\Scripts\uvicorn main:app --reload --host 127.0.0.1 --port 8000
