// Global State
const state = {
    token: localStorage.getItem('token') || null,
    currentUser: null,
    tasks: [],
    pollingInterval: null,
    activeWorkspaceTaskId: null
};

// --- View Router ---
function showView(viewId) {
    document.querySelectorAll('.view-container').forEach(el => {
        el.classList.remove('active');
    });
    const target = document.getElementById(viewId);
    target.classList.add('active');
}

// --- Toast System ---
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');
    const toastIcon = document.getElementById('toast-icon');
    
    toast.className = `toast ${type}`;
    toastMessage.textContent = message;
    
    // Set icons
    if (type === 'success') {
        toastIcon.className = 'fa-solid fa-circle-check';
    } else if (type === 'error') {
        toastIcon.className = 'fa-solid fa-triangle-exclamation';
    } else {
        toastIcon.className = 'fa-solid fa-circle-info';
    }
    
    toast.classList.remove('hidden');
    
    // Auto hide after 3 seconds
    if (toast.timeoutId) clearTimeout(toast.timeoutId);
    toast.timeoutId = setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}

// --- Fetch Wrapper with JWT Header ---
async function apiFetch(url, options = {}) {
    const headers = options.headers || {};
    if (state.token) {
        headers['Authorization'] = `Bearer ${state.token}`;
    }
    
    options.headers = headers;
    const response = await fetch(url, options);
    
    if (response.status === 401) {
        // Token expired or invalid
        handleLogout();
        showToast('登录会话已过期，请重新登录', 'error');
        throw new Error('Unauthorized');
    }
    
    return response;
}

// --- Authentication UI and logic ---
function switchAuthTab(type) {
    document.querySelectorAll('.auth-tab').forEach(el => {
        el.classList.remove('active');
    });
    
    const authBtn = document.getElementById('auth-btn');
    const btnText = authBtn.querySelector('.btn-text');
    
    if (type === 'login') {
        document.querySelector('.auth-tab[onclick*="login"]').classList.add('active');
        btnText.textContent = '登录系统';
        authBtn.className = 'btn btn-primary btn-block';
    } else {
        document.querySelector('.auth-tab[onclick*="register"]').classList.add('active');
        btnText.textContent = '注册账号';
        authBtn.className = 'btn btn-cyan btn-block';
    }
    
    document.getElementById('auth-error').classList.add('hidden');
}

async function handleAuthSubmit(event) {
    event.preventDefault();
    const usernameInput = document.getElementById('username').value.strip ? document.getElementById('username').value.strip() : document.getElementById('username').value.trim();
    const passwordInput = document.getElementById('password').value;
    const authError = document.getElementById('auth-error');
    const isLogin = document.querySelector('.auth-tab.active').textContent.includes('登录');
    
    authError.classList.add('hidden');
    
    try {
        if (isLogin) {
            // Login: form urlencoded
            const formData = new URLSearchParams();
            formData.append('username', usernameInput);
            formData.append('password', passwordInput);
            
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: formData
            });
            
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || '登录失败');
            }
            
            state.token = data.access_token;
            localStorage.setItem('token', data.access_token);
            showToast('欢迎回来！登录成功', 'success');
            await initDashboard();
        } else {
            // Register: JSON
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username: usernameInput,
                    password: passwordInput
                })
            });
            
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.detail || '注册失败');
            }
            
            showToast('注册成功！正在为您自动登录', 'success');
            // Auto login after register
            switchAuthTab('login');
            document.getElementById('username').value = usernameInput;
            document.getElementById('password').value = passwordInput;
            document.getElementById('auth-form').dispatchEvent(new Event('submit'));
        }
    } catch (err) {
        authError.textContent = err.message;
        authError.classList.remove('hidden');
    }
}

function handleLogout() {
    state.token = null;
    state.currentUser = null;
    localStorage.removeItem('token');
    
    // Clear tasks polling
    if (state.pollingInterval) {
        clearInterval(state.pollingInterval);
        state.pollingInterval = null;
    }
    
    // Clear forms
    document.getElementById('username').value = '';
    document.getElementById('password').value = '';
    
    showView('auth-screen');
}

// --- Dashboard Screen Initializer ---
async function initDashboard() {
    showView('dashboard-screen');
    await loadUserProfile();
    await checkAsrStatus();
    await loadTaskList();
    
    // Start polling task queue status
    if (state.pollingInterval) clearInterval(state.pollingInterval);
    state.pollingInterval = setInterval(loadTaskList, 3000);
}

async function loadUserProfile() {
    try {
        const response = await apiFetch('/api/auth/me');
        if (!response.ok) throw new Error();
        const user = await response.json();
        state.currentUser = user;
        
        document.getElementById('user-display-name').textContent = user.username;
        
        // Update Feishu Bind Badge
        const badge = document.getElementById('feishu-status-panel');
        const text = document.getElementById('feishu-status-text');
        const btn = document.getElementById('feishu-action-btn');
        
        if (user.feishu_bound) {
            badge.classList.add('bound');
            text.textContent = `已绑定: ${user.feishu_info.name || '飞书用户'}`;
            btn.textContent = '解绑飞书';
            btn.className = 'btn btn-sm btn-outline';
        } else {
            badge.classList.remove('bound');
            text.textContent = '未绑定飞书';
            btn.textContent = '立即绑定';
            btn.className = 'btn btn-sm btn-outline-success';
        }
    } catch (err) {
        console.error('Failed to load user profile');
    }
}

// Check local ASR system status
async function checkAsrStatus() {
    try {
        const response = await apiFetch('/api/asr/status');
        const data = await response.json();
        const badge = document.getElementById('asr-status-badge');
        badge.textContent = data.device;
        if (data.has_whisper) {
            badge.className = 'asr-badge whisper-ok';
        } else {
            badge.className = 'asr-badge whisper-sim';
        }
    } catch (err) {
        console.error(err);
    }
}

// --- Feishu Binding Handler Popup ---
function handleFeishuAction() {
    if (state.currentUser && state.currentUser.feishu_bound) {
        // Trigger Unbind
        if (confirm('确定要解绑您的飞书账号吗？解绑后将无法提交新的飞书妙记转换任务。')) {
            unbindFeishu();
        }
    } else {
        // Trigger Bind - opens oauth window
        const width = 600;
        const height = 600;
        const left = (screen.width - width) / 2;
        const top = (screen.height - height) / 2;
        
        // Pre-open the popup window to avoid modern browser popup blocker
        const authWindow = window.open('about:blank', 'feishu_auth_popup', `width=${width},height=${height},top=${top},left=${left},scrollbars=yes,resizable=yes`);
        if (!authWindow) {
            showToast('浏览器拦截了弹出窗口，请在浏览器设置中允许此网站的弹出式窗口。', 'error');
            return;
        }
        
        // Write a loading message into the window
        authWindow.document.write(`
            <html>
            <head><title>正在加载飞书授权...</title></head>
            <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #121214; color: #e1e1e6;">
                <div style="font-size: 18px; margin-bottom: 10px;">正在获取授权链接...</div>
                <div style="color: #8d8d99; font-size: 14px;">请稍候</div>
            </body>
            </html>
        `);
        
        // Fetch oauth url from API
        apiFetch('/api/auth/feishu/url')
            .then(res => res.json())
            .then(data => {
                if (data.url) {
                    authWindow.location.href = data.url;
                } else {
                    throw new Error('未返回有效的授权 URL');
                }
            })
            .catch(err => {
                authWindow.close();
                showToast('无法获取飞书授权地址', 'error');
            });
    }
}

// Unbind Feishu token API
async function unbindFeishu() {
    try {
        const response = await apiFetch('/api/auth/feishu/unbind', { method: 'POST' });
        if (response.ok) {
            showToast('已解绑飞书账号', 'info');
            await loadUserProfile();
        } else {
            const data = await response.json();
            showToast(data.detail || '解绑失败', 'error');
        }
    } catch (err) {
        showToast('解绑异常，请重试', 'error');
    }
}

// Trigger direct login via Feishu
function handleFeishuLogin() {
    const width = 600;
    const height = 600;
    const left = (screen.width - width) / 2;
    const top = (screen.height - height) / 2;
    
    // Pre-open the popup window to avoid modern browser popup blocker
    const loginWindow = window.open('about:blank', 'feishu_login_popup', `width=${width},height=${height},top=${top},left=${left},scrollbars=yes,resizable=yes`);
    if (!loginWindow) {
        showToast('浏览器拦截了弹出窗口，请在浏览器设置中允许此网站的弹出式窗口。', 'error');
        return;
    }
    
    // Write a loading message into the window
    loginWindow.document.write(`
        <html>
        <head><title>正在加载飞书登录...</title></head>
        <body style="font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #121214; color: #e1e1e6;">
            <div style="font-size: 18px; margin-bottom: 10px;">正在获取登录链接...</div>
            <div style="color: #8d8d99; font-size: 14px;">请稍候</div>
        </body>
        </html>
    `);
    
    fetch('/api/auth/feishu/login_url')
        .then(res => res.json())
        .then(data => {
            if (data.url) {
                loginWindow.location.href = data.url;
            } else {
                throw new Error('未返回有效的登录 URL');
            }
        })
        .catch(err => {
            loginWindow.close();
            showToast('无法获取飞书授权登录地址', 'error');
        });
}

// Listen to Feishu auth success/login messages from OAuth popup
window.addEventListener('message', async (event) => {
    if (!event.data) return;
    
    if (event.data.type === 'FEISHU_AUTH_SUCCESS') {
        showToast('飞书绑定成功！', 'success');
        await loadUserProfile();
    } else if (event.data.type === 'FEISHU_LOGIN_SUCCESS') {
        const token = event.data.token;
        state.token = token;
        localStorage.setItem('token', token);
        showToast('飞书登录成功！欢迎回来', 'success');
        await initDashboard();
    }
});

// --- Tab Switchers ---
function switchTaskTab(type) {
    document.querySelectorAll('.task-tab').forEach(el => {
        el.classList.remove('active');
    });
    document.querySelectorAll('.task-form').forEach(el => {
        el.classList.remove('active');
    });
    
    if (type === 'feishu') {
        document.querySelector('.task-tab[onclick*="feishu"]').classList.add('active');
        document.getElementById('feishu-task-form').classList.add('active');
    } else {
        document.querySelector('.task-tab[onclick*="local"]').classList.add('active');
        document.getElementById('local-task-form').classList.add('active');
    }
}

// --- Submit tasks ---

async function submitFeishuTask() {
    const inputField = document.getElementById('feishu-token-input');
    const titleField = document.getElementById('feishu-title-input');
    const inputVal = inputField.value.trim();
    const titleVal = titleField.value.trim();
    
    if (!inputVal) {
        showToast('请输入飞书妙记分享链接或 Token', 'error');
        return;
    }
    
    try {
        const response = await apiFetch('/api/tasks/feishu', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                minute_url_or_token: inputVal,
                title: titleVal || null
            })
        });
        
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || '提交任务失败');
        }
        
        showToast('飞书转换任务已提交！正在处理中...', 'success');
        inputField.value = '';
        titleField.value = '';
        await loadTaskList();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// Local File Upload trigger
function triggerFileInput() {
    document.getElementById('file-input').click();
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const info = document.getElementById('selected-file-info');
    const name = document.getElementById('selected-file-name');
    
    name.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    info.classList.remove('hidden');
    document.getElementById('drop-zone').style.borderColor = 'var(--cyan)';
}

function clearSelectedFile() {
    document.getElementById('file-input').value = '';
    document.getElementById('selected-file-info').classList.add('hidden');
    document.getElementById('drop-zone').style.borderColor = 'var(--border-color)';
}

async function submitLocalTask() {
    const fileInput = document.getElementById('file-input');
    const titleInput = document.getElementById('local-title-input');
    const file = fileInput.files[0];
    const titleVal = titleInput.value.trim();
    
    if (!file) {
        showToast('请选择或拖放一个音频文件', 'error');
        return;
    }
    
    const submitBtn = document.getElementById('local-submit-btn');
    const originalHtml = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 正在上传音频文件中...';
    
    const formData = new FormData();
    formData.append('file', file);
    if (titleVal) {
        formData.append('title', titleVal);
    }
    
    try {
        const response = await apiFetch('/api/tasks/local', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || '上传本地音频失败');
        }
        
        showToast('音频上传成功，本地 ASR 转写队列已启动！', 'success');
        clearSelectedFile();
        titleInput.value = '';
        await loadTaskList();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalHtml;
    }
}

// --- Load Task List & Render Card ---
async function loadTaskList() {
    if (!state.token) return;
    
    try {
        const response = await apiFetch('/api/tasks');
        if (!response.ok) throw new Error();
        const tasks = await response.json();
        state.tasks = tasks;
        
        renderTaskList(tasks);
    } catch (err) {
        console.error('Failed to reload tasks list', err);
    }
}

function renderTaskList(tasks) {
    const container = document.getElementById('task-list-container');
    if (!tasks || tasks.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-inbox"></i>
                <p>暂无正在进行或历史任务</p>
            </div>`;
        return;
    }
    
    let html = '';
    tasks.forEach(task => {
        // Append 'Z' to timezone-naive UTC datetime strings from backend to parse correctly in browser local time
        const cleanCreatedAt = task.created_at && !task.created_at.endsWith('Z') && !task.created_at.includes('+')
            ? task.created_at + 'Z'
            : task.created_at;
        const dateStr = new Date(cleanCreatedAt).toLocaleString();
        const durationStr = task.duration ? formatDuration(task.duration) : '--';
        
        // Progress render
        let progressHtml = '';
        if (task.status === 'pending' || task.status === 'processing') {
            const statusMsg = task.error_message || '排队中...';
            progressHtml = `
                <div class="task-progress-row">
                    <div class="progress-track">
                        <div class="progress-bar" style="width: ${task.progress}%"></div>
                    </div>
                    <span class="progress-text">${task.progress}%</span>
                </div>
                <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
                    <i class="fa-solid fa-arrows-spin fa-spin"></i> ${statusMsg}
                </div>`;
        }
        
        // Badge type
        const typeBadge = task.task_type === 'feishu' 
            ? '<span class="badge badge-feishu">飞书妙记</span>' 
            : '<span class="badge badge-local">本地 ASR</span>';
            
        // Status Badge
        let statusBadge = '';
        if (task.status === 'pending') statusBadge = '<div class="status-indicator pending"><div class="status-dot"></div>排队中</div>';
        else if (task.status === 'processing') statusBadge = '<div class="status-indicator processing"><div class="status-dot"></div>处理中</div>';
        else if (task.status === 'completed') statusBadge = '<div class="status-indicator completed"><div class="status-dot"></div>已完成</div>';
        else if (task.status === 'failed') statusBadge = '<div class="status-indicator failed"><div class="status-dot"></div>已失败</div>';
        
        // Action buttons
        let actionsHtml = '';
        if (task.status === 'completed') {
            actionsHtml = `
                <button class="btn btn-sm btn-cyan" onclick="openWorkspace('${task.id}')">
                    <i class="fa-solid fa-cubes"></i> 视图面板
                </button>
                <button class="btn btn-sm btn-outline" onclick="triggerDownload('${task.id}')" title="下载 Markdown">
                    <i class="fa-solid fa-download"></i> 下载
                </button>`;
        }
        
        // Delete button is always available unless processing
        if (task.status !== 'processing') {
            actionsHtml += `
                <button class="btn-icon btn-danger-icon" onclick="deleteTask('${task.id}')" title="删除任务">
                    <i class="fa-solid fa-trash-can"></i>
                </button>`;
        }
        
        // Error block
        const errorBlock = (task.status === 'failed' && task.error_message)
            ? `<div class="task-error-msg"><i class="fa-solid fa-triangle-exclamation"></i> 失败原因: ${task.error_message}</div>`
            : '';
            
        html += `
            <div class="task-card">
                <div class="task-info-col">
                    <div class="task-title-row">
                        ${typeBadge}
                        <span class="task-title" title="${task.title || '无标题'}">${task.title || '无标题'}</span>
                    </div>
                    <div class="task-meta-row">
                        <span><i class="fa-solid fa-clock"></i> ${dateStr}</span>
                        <span><i class="fa-solid fa-hourglass-half"></i> 时长: ${durationStr}</span>
                    </div>
                    ${progressHtml}
                </div>
                
                <div class="task-actions-col">
                    ${statusBadge}
                    <div style="display:flex; gap: 8px; margin-top: auto;">
                        ${actionsHtml}
                    </div>
                </div>
                ${errorBlock}
            </div>`;
    });
    
    container.innerHTML = html;
}

// Formatting seconds helper
function formatDuration(sec) {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}分${s}秒`;
}

// Delete Task API
async function deleteTask(taskId) {
    if (!confirm('确定要删除这个转写任务吗？与之关联的所有转写缓存和 Markdown 编译文件将被物理删除。')) {
        return;
    }
    
    try {
        const response = await apiFetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
        if (response.ok) {
            showToast('任务已成功删除', 'info');
            await loadTaskList();
        } else {
            showToast('删除失败，请重试', 'error');
        }
    } catch (err) {
        showToast('删除异常', 'error');
    }
}

// Download MD directly trigger
function triggerDownload(taskId) {
    const token = state.token;
    const url = `/api/tasks/${taskId}/download`;
    // Create temporary link for downloading
    const link = document.createElement('a');
    link.href = url;
    
    // Fetch file with authorization header using object url
    apiFetch(url)
        .then(res => {
            if (!res.ok) throw new Error('Download failed');
            // Extract filename from Content-Disposition header.
            // 支持两种格式:
            //   1. filename="xxx.md"            (纯 ASCII)
            //   2. filename*=UTF-8''%E5%A6%99... (RFC 5987,中文会被 URL 编码)
            const contentDisposition = res.headers.get('Content-Disposition');
            let filename = '妙记归档员会议记录.md';
            if (contentDisposition) {
                const starMatch = contentDisposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i);
                if (starMatch) {
                    filename = decodeURIComponent(starMatch[1]);
                } else {
                    const match = contentDisposition.match(/filename="?([^";]+)"?/);
                    if (match) filename = match[1];
                }
            }
            return res.blob().then(blob => ({ blob, filename }));
        })
        .then(({ blob, filename }) => {
            const objUrl = URL.createObjectURL(blob);
            link.href = objUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(objUrl);
        })
        .catch(err => showToast('下载文件出错', 'error'));
}

// --- WORKSPACE VIEW AND EDIT ---
async function openWorkspace(taskId) {
    state.activeWorkspaceTaskId = taskId;
    
    try {
        const response = await apiFetch(`/api/tasks/${taskId}`);
        if (!response.ok) throw new Error();
        const task = await response.json();
        
        // Setup Workspace Header info
        document.getElementById('ws-task-title').textContent = task.title || '未命名任务';
        const typeBadge = document.getElementById('ws-type-badge');
        typeBadge.textContent = task.task_type === 'feishu' ? '飞书妙记' : '本地 ASR';
        typeBadge.className = task.task_type === 'feishu' ? 'badge badge-feishu' : 'badge badge-local';
        
        // Parse speakers list from transcript
        const speakers = extractUniqueSpeakers(task.result_markdown);
        
        // Render Speaker Mapping editor
        renderSpeakerMappingList(speakers, task.speaker_map || {});
        
        // Fetch rendered Markdown preview
        await loadMarkdownPreview(taskId);
        
        showView('workspace-screen');
        
        // Pause dashboard polling while in workspace to avoid heavy reloads
        if (state.pollingInterval) {
            clearInterval(state.pollingInterval);
            state.pollingInterval = null;
        }
    } catch (err) {
        showToast('打开视图面板失败', 'error');
    }
}

function closeWorkspace() {
    state.activeWorkspaceTaskId = null;
    showView('dashboard-screen');
    
    // Resume dashboard polling
    if (!state.pollingInterval && state.token) {
        state.pollingInterval = setInterval(loadTaskList, 3000);
    }
}

// Extract unique speakers list from raw transcript content
function extractUniqueSpeakers(transcriptText) {
    if (!transcriptText) return [];
    
    // Regex matches [HH:MM:SS] SpeakerName: or [MM:SS] SpeakerName:
    // Support both full colon and half colon
    const regex = /^\[(?:\d{1,2}:)?\d{2}:\d{2}\]\s*(.*?)[：:]/gm;
    const speakers = new Set();
    let match;
    
    // Reset index just in case
    regex.lastIndex = 0;
    while ((match = regex.exec(transcriptText)) !== null) {
        const speakerName = match[1].trim();
        if (speakerName) {
            speakers.add(speakerName);
        }
    }
    
    return Array.from(speakers);
}

function renderSpeakerMappingList(speakers, currentMap) {
    const listEl = document.getElementById('speaker-mapping-list');
    if (speakers.length === 0) {
        listEl.innerHTML = '<p style="font-size:13px; color:var(--text-muted);">未在转写文本中找到明显的说话人标记。</p>';
        return;
    }
    
    let html = '';
    speakers.forEach(speaker => {
        const val = currentMap[speaker] || '';
        html += `
            <div class="speaker-mapping-item" data-speaker="${speaker}">
                <label>${speaker}</label>
                <input type="text" placeholder="给该发言人绑定名字..." value="${val}">
            </div>`;
    });
    
    listEl.innerHTML = html;
}

// Load compiled Markdown output file text
async function loadMarkdownPreview(taskId) {
    try {
        const response = await apiFetch(`/api/tasks/${taskId}/download`);
        if (!response.ok) throw new Error();
        const mdText = await response.text();
        document.getElementById('markdown-raw-view').textContent = mdText;
    } catch (err) {
        document.getElementById('markdown-raw-view').textContent = '加载 Markdown 预览失败。';
    }
}

// Post speaker mappings to API
async function applySpeakerMapping() {
    const taskId = state.activeWorkspaceTaskId;
    if (!taskId) return;
    
    const items = document.querySelectorAll('.speaker-mapping-item');
    const speakerMap = {};
    
    items.forEach(item => {
        const origSpeaker = item.getAttribute('data-speaker');
        const inputVal = item.querySelector('input').value.trim();
        if (inputVal) {
            speakerMap[origSpeaker] = inputVal;
        }
    });
    
    try {
        const response = await apiFetch(`/api/tasks/${taskId}/update_speaker_map`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ speaker_map: speakerMap })
        });
        
        if (response.ok) {
            showToast('说话人别名映射已成功更新，Markdown 文档已重新编译！', 'success');
            // Reload preview
            await loadMarkdownPreview(taskId);
        } else {
            const data = await response.json();
            showToast(data.detail || '更新映射失败', 'error');
        }
    } catch (err) {
        showToast('更新映射时发生异常', 'error');
    }
}

// Clipboard copying
function copyMarkdownToClipboard() {
    const text = document.getElementById('markdown-raw-view').textContent;
    if (!text || text.includes('加载 Markdown 预览失败')) {
        showToast('无有效文档内容可复制', 'error');
        return;
    }
    
    navigator.clipboard.writeText(text)
        .then(() => showToast('Markdown 内容已复制到剪贴板！', 'success'))
        .catch(err => showToast('复制失败，请手动选择复制', 'error'));
}

// Download button inside Workspace
function downloadMarkdown() {
    if (state.activeWorkspaceTaskId) {
        triggerDownload(state.activeWorkspaceTaskId);
    }
}

// Drag & drop handlers setup
function setupDragAndDrop() {
    const zone = document.getElementById('drop-zone');
    if (!zone) return;
    
    ['dragenter', 'dragover'].forEach(eventName => {
        zone.addEventListener(eventName, (e) => {
            e.preventDefault();
            zone.style.borderColor = 'var(--cyan)';
            zone.style.background = 'rgba(6, 182, 212, 0.05)';
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        zone.addEventListener(eventName, (e) => {
            e.preventDefault();
            if (eventName === 'dragleave') {
                zone.style.borderColor = 'var(--border-color)';
                zone.style.background = 'rgba(255, 255, 255, 0.01)';
            }
        }, false);
    });
    
    zone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            const fileInput = document.getElementById('file-input');
            fileInput.files = files;
            // Trigger selector updates
            const event = new Event('change', { bubbles: true });
            fileInput.dispatchEvent(event);
        }
    }, false);
}

// --- App Startup ---
document.addEventListener('DOMContentLoaded', () => {
    // If token exists, load dashboard directly
    if (state.token) {
        initDashboard();
    } else {
        showView('auth-screen');
    }
    
    setupDragAndDrop();
});
