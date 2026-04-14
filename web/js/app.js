/**
 * AI 智能助手前端应用
 */

const API_BASE_URL = 'http://localhost:8000';

class App {
    constructor() {
        this.currentPage = 'chat';
        this.messages = [];
        this.isTyping = false;
        this.sessionId = this.generateSessionId();
        this.chatHistory = []; // 对话历史列表（从后端获取）
        this.currentChatId = this.sessionId; // 当前对话ID
        this.init();
    }

    init() {
        this.checkHealth();
        this.setupEventListeners();
        this.loadInitialData();
        this.loadChatHistory(); // 从后端加载对话历史

        // 定期检查健康状态
        setInterval(() => this.checkHealth(), 30000);
    }

    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    setupEventListeners() {
        // 文件输入监听
        document.getElementById('fileInput').addEventListener('change', (e) => this.handleFileSelect(e));
        document.getElementById('folderInput').addEventListener('change', (e) => this.handleFolderSelect(e));
        document.getElementById('imageInput').addEventListener('change', (e) => this.handleImageSelect(e));
    }

    async loadInitialData() {
        await this.loadTools();
        await this.loadMCPServers();
        await this.loadSkills();
        await this.loadMemoryStats();
        await this.loadTokenStats();
    }

    // ========================================
    // 页面切换
    // ========================================

    switchPage(page) {
        this.currentPage = page;

        // 更新导航状态
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.page === page) {
                item.classList.add('active');
            }
        });

        // 切换页面
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.getElementById(`page-${page}`).classList.add('active');

        // 加载页面数据
        switch(page) {
            case 'tools':
                this.loadTools();
                break;
            case 'mcp':
                this.loadMCPServers();
                this.loadMCPTools();
                break;
            case 'skills':
                this.loadSkills();
                break;
            case 'memory':
                this.loadMemoryStats();
                break;
            case 'tokens':
                this.loadTokenStats();
                break;
        }
    }

    // ========================================
    // API 请求
    // ========================================

    async apiRequest(endpoint, options = {}) {
        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, {
                headers: {
                    'Content-Type': 'application/json',
                },
                ...options
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '请求失败');
            }

            return await response.json();
        } catch (error) {
            this.showToast(error.message, 'error');
            throw error;
        }
    }

    // ========================================
    // 健康检查
    // ========================================

    async checkHealth() {
        try {
            const data = await this.apiRequest('/health');
            const indicator = document.getElementById('statusIndicator');
            const dot = indicator.querySelector('.status-dot');
            const text = indicator.querySelector('.status-text');

            if (data.status === 'healthy') {
                dot.classList.add('connected');
                text.textContent = '已连接';
            } else {
                dot.classList.remove('connected');
                text.textContent = '未就绪';
            }
        } catch (error) {
            const indicator = document.getElementById('statusIndicator');
            const dot = indicator.querySelector('.status-dot');
            const text = indicator.querySelector('.status-text');
            dot.classList.remove('connected');
            text.textContent = '连接失败';
        }
    }

    // ========================================
    // 聊天功能
    // ========================================

    async sendMessage() {
        const input = document.getElementById('messageInput');
        const message = input.value.trim();

        if (!message || this.isTyping) return;

        // 添加用户消息
        this.addMessage('user', message);
        input.value = '';
        this.autoResize(input);

        // 显示正在输入
        this.showTypingIndicator();
        this.isTyping = true;

        try {
            const data = await this.apiRequest('/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message: message,
                    session_id: this.sessionId,
                    enable_memory: true
                })
            });

            this.hideTypingIndicator();

            if (data.success) {
                this.addMessage('assistant', data.response, [], data.thoughts);

                // 刷新历史列表（从后端日志读取）
                await this.loadChatHistory();
            } else {
                this.addMessage('assistant', '抱歉，处理您的请求时出现了错误。');
            }
        } catch (error) {
            this.hideTypingIndicator();
            this.addMessage('assistant', '抱歉，服务暂时不可用，请稍后再试。');
        } finally {
            this.isTyping = false;
        }
    }

    sendQuickMessage(message) {
        const input = document.getElementById('messageInput');
        input.value = message;
        this.sendMessage();
    }

    addMessage(role, content, attachments = [], thoughts = []) {
        const container = document.getElementById('chatMessages');

        // 移除欢迎消息
        const welcome = container.querySelector('.welcome-message');
        if (welcome) {
            welcome.remove();
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;

        const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

        let attachmentsHtml = '';
        if (attachments.length > 0) {
            attachmentsHtml = `
                <div class="message-attachments">
                    ${attachments.map(att => `
                        <div class="attachment">
                            <i class="fas fa-${att.icon}"></i>
                            <span>${att.name}</span>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        // 构建思考过程 HTML
        let thoughtsHtml = '';
        if (thoughts && thoughts.length > 0) {
            const nonFinalThoughts = thoughts.filter(t => !t.is_final);
            if (nonFinalThoughts.length > 0) {
                thoughtsHtml = `
                    <div class="thoughts-process">
                        <div class="thoughts-header" onclick="app.toggleThoughts(this)">
                            <i class="fas fa-brain"></i>
                            <span>思考过程 (${nonFinalThoughts.length} 步)</span>
                            <i class="fas fa-chevron-down thoughts-toggle"></i>
                        </div>
                        <div class="thoughts-content collapsed">
                            ${nonFinalThoughts.map((t, idx) => `
                                <div class="thought-step">
                                    <div class="thought-step-header">
                                        <span class="step-number">步骤 ${t.step}</span>
                                        ${t.action ? `<span class="step-action"><i class="fas fa-tools"></i> ${t.action.tool_name}</span>` : ''}
                                    </div>
                                    <div class="thought-step-content">
                                        <div class="thought-section">
                                            <div class="section-label"><i class="fas fa-lightbulb"></i> 思考</div>
                                            <div class="section-text">${this.formatMessage(t.thought)}</div>
                                        </div>
                                        ${t.action ? `
                                            <div class="thought-section">
                                                <div class="section-label"><i class="fas fa-bolt"></i> 行动</div>
                                                <div class="section-text">
                                                    <code>${t.action.tool_name}</code>
                                                    <pre class="params-pre"><code>${JSON.stringify(t.action.parameters, null, 2)}</code></pre>
                                                </div>
                                            </div>
                                        ` : ''}
                                        ${t.observation ? `
                                            <div class="thought-section">
                                                <div class="section-label"><i class="fas fa-eye"></i> 观察</div>
                                                <div class="section-text observation-text">${this.formatObservation(t.observation)}</div>
                                            </div>
                                        ` : ''}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }
        }

        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-${role === 'user' ? 'user' : 'robot'}"></i>
            </div>
            <div class="message-body">
                ${thoughtsHtml}
                <div class="message-content">
                    ${this.formatMessage(content)}
                    ${attachmentsHtml}
                </div>
                <div class="message-time">${time}</div>
            </div>
        `;

        container.appendChild(messageDiv);
        this.scrollToBottom();
    }

    formatObservation(observation) {
        // 尝试格式化 JSON 观察结果
        try {
            const parsed = JSON.parse(observation);
            return `<pre class="observation-pre"><code>${JSON.stringify(parsed, null, 2)}</code></pre>`;
        } catch (e) {
            // 如果不是 JSON，直接返回格式化后的文本
            return this.formatMessage(observation);
        }
    }

    toggleThoughts(header) {
        const content = header.nextElementSibling;
        const toggle = header.querySelector('.thoughts-toggle');

        if (content.classList.contains('collapsed')) {
            content.classList.remove('collapsed');
            content.classList.add('expanded');
            toggle.style.transform = 'rotate(180deg)';
        } else {
            content.classList.add('collapsed');
            content.classList.remove('expanded');
            toggle.style.transform = 'rotate(0deg)';
        }
    }

    formatMessage(content) {
        // 提取 final 标记中的内容
        const finalMatch = content.match(/```final\n?([\s\S]*?)```/);
        if (finalMatch) {
            content = finalMatch[1].trim();
        }

        // Markdown 格式化
        let formatted = content
            // 代码块 (排除 final 标记)
            .replace(/```(?!final)([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
            // 行内代码
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            // 粗体
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            // 斜体
            .replace(/\*([^*]+)\*/g, '<em>$1</em>')
            // 删除线
            .replace(/~~([^~]+)~~/g, '<del>$1</del>');

        // 表格处理
        formatted = this.formatTables(formatted);

        // 列表处理
        formatted = this.formatLists(formatted);

        // 换行处理 (在代码块和表格之后)
        formatted = formatted.replace(/\n/g, '<br>');

        return formatted;
    }

    formatTables(content) {
        // 匹配 Markdown 表格
        const tableRegex = /\|([^\n]+)\|\n\|[-:\|\s]+\|\n((?:\|[^\n]+\|\n?)+)/g;

        return content.replace(tableRegex, (match, header, rows) => {
            // 解析表头
            const headers = header.split('|').map(h => h.trim()).filter(h => h);

            // 解析行
            const rowData = rows.trim().split('\n').map(row => {
                return row.split('|').map(cell => cell.trim()).filter(cell => cell);
            }).filter(row => row.length > 0);

            // 构建 HTML 表格
            let html = '<table class="md-table">';

            // 表头
            html += '<thead><tr>';
            headers.forEach(h => {
                html += `<th>${h}</th>`;
            });
            html += '</tr></thead>';

            // 表体
            html += '<tbody>';
            rowData.forEach(row => {
                html += '<tr>';
                row.forEach(cell => {
                    html += `<td>${cell}</td>`;
                });
                html += '</tr>';
            });
            html += '</tbody></table>';

            return html;
        });
    }

    formatLists(content) {
        // 有序列表
        let formatted = content.replace(/(^|\n)(\d+\.\s+.+)(?=\n|$)/g, (match, prefix, item) => {
            return `${prefix}<ol class="md-list"><li>${item.replace(/^\d+\.\s*/, '')}</li></ol>`;
        });

        // 无序列表
        formatted = formatted.replace(/(^|\n)([-*]\s+.+)(?=\n|$)/g, (match, prefix, item) => {
            return `${prefix}<ul class="md-list"><li>${item.replace(/^[-*]\s*/, '')}</li></ul>`;
        });

        // 合并连续的列表项
        formatted = formatted.replace(/<\/ol>\s*<ol class="md-list">/g, '');
        formatted = formatted.replace(/<\/ul>\s*<ul class="md-list">/g, '');

        return formatted;
    }

    showTypingIndicator() {
        const container = document.getElementById('chatMessages');
        const indicator = document.createElement('div');
        indicator.className = 'message assistant typing';
        indicator.id = 'typingIndicator';
        indicator.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;
        container.appendChild(indicator);
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.remove();
        }
    }

    scrollToBottom() {
        const container = document.getElementById('chatMessages');
        container.scrollTop = container.scrollHeight;
    }

    handleKeyDown(event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    }

    autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }

    newChat() {
        this.messages = [];
        this.sessionId = this.generateSessionId();
        document.getElementById('chatMessages').innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <i class="fas fa-robot"></i>
                </div>
                <h3>你好！我是 AI 智能助手</h3>
                <p>我可以帮你解答问题、处理文件、管理工具等。试着问我点什么吧！</p>
                <div class="quick-actions">
                    <button class="quick-btn" onclick="app.sendQuickMessage('介绍一下你自己')">
                        <i class="fas fa-user"></i>
                        介绍自己
                    </button>
                    <button class="quick-btn" onclick="app.sendQuickMessage('查看可用工具')">
                        <i class="fas fa-tools"></i>
                        查看工具
                    </button>
                    <button class="quick-btn" onclick="app.sendQuickMessage('帮我搜索资料')">
                        <i class="fas fa-search"></i>
                        搜索资料
                    </button>
                </div>
            </div>
        `;
        this.switchPage('chat');
    }

    clearChat() {
        if (confirm('确定要清空当前对话吗？')) {
            this.newChat();
        }
    }

    // ========================================
    // 文件上传功能
    // ========================================

    uploadFile() {
        document.getElementById('fileInput').click();
    }

    uploadFolder() {
        document.getElementById('folderInput').click();
    }

    uploadImage() {
        document.getElementById('imageInput').click();
    }

    async handleFileSelect(event) {
        const files = event.target.files;
        if (files.length === 0) return;

        console.log('[上传] 选择的文件:', files);
        this.showToast(`正在上传 ${files.length} 个文件...`, 'info');

        try {
            // 创建 FormData
            const formData = new FormData();
            for (const file of files) {
                formData.append('files', file);
                console.log('[上传] 添加文件:', file.name, file.size);
            }

            console.log('[上传] 发送请求到:', `${API_BASE_URL}/upload`);

            // 调用后端上传接口
            const response = await fetch(`${API_BASE_URL}/upload`, {
                method: 'POST',
                body: formData
            });

            console.log('[上传] 响应状态:', response.status);

            if (!response.ok) {
                const errorText = await response.text();
                console.error('[上传] 错误响应:', errorText);
                throw new Error(`上传失败 (${response.status}): ${errorText}`);
            }

            const data = await response.json();
            console.log('[上传] 响应数据:', data);

            if (data.success) {
                // 创建附件列表
                const attachments = data.files.map(file => ({
                    name: file.filename,
                    icon: this.getFileIcon(file.content_type),
                    size: this.formatFileSize(file.size),
                    path: file.path
                }));

                // 添加带有附件的消息
                this.addMessage('user', `[上传了 ${data.total} 个文件]`, attachments);
                this.showToast(data.message, 'success');
            } else {
                this.showToast(data.message || '上传失败', 'error');
            }
        } catch (error) {
            console.error('[上传] 错误:', error);
            this.showToast(`上传失败: ${error.message}`, 'error');
        }

        // 清空输入
        event.target.value = '';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async handleFolderSelect(event) {
        const files = event.target.files;
        if (files.length === 0) return;

        // 显示上传中提示
        this.showToast(`正在上传文件夹，包含 ${files.length} 个文件...`, 'info');

        try {
            // 创建 FormData
            const formData = new FormData();
            for (const file of files) {
                // webkitRelativePath 包含文件的相对路径
                const relativePath = file.webkitRelativePath || file.name;
                formData.append('files', file, relativePath);
            }
            formData.append('folder_name', this.extractFolderName(files[0].webkitRelativePath));

            // 调用后端文件夹上传接口
            const response = await fetch(`${API_BASE_URL}/upload/folder`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '上传失败');
            }

            const data = await response.json();

            if (data.success) {
                // 创建附件列表
                const attachments = [{
                    name: `${data.files[0]?.filename.split('/')[0]} (${data.total} 个文件)`,
                    icon: 'folder',
                    size: `${data.total} 个文件`
                }];

                // 添加带有附件的消息
                this.addMessage('user', `[上传了文件夹，包含 ${data.total} 个文件]`, attachments);
                this.showToast(data.message, 'success');
            } else {
                this.showToast(data.message || '上传失败', 'error');
            }
        } catch (error) {
            this.showToast(`上传失败: ${error.message}`, 'error');
            console.error('上传错误:', error);
        }

        event.target.value = '';
    }

    extractFolderName(webkitRelativePath) {
        if (!webkitRelativePath) return 'folder';
        const parts = webkitRelativePath.split('/');
        return parts[0] || 'folder';
    }

    async handleImageSelect(event) {
        const files = event.target.files;
        if (files.length === 0) return;

        // 显示上传中提示
        this.showToast(`正在上传 ${files.length} 张图片...`, 'info');

        try {
            // 创建 FormData
            const formData = new FormData();
            for (const file of files) {
                formData.append('files', file);
            }

            // 调用后端上传接口（图片和普通文件使用相同的接口）
            const response = await fetch(`${API_BASE_URL}/upload`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '上传失败');
            }

            const data = await response.json();

            if (data.success) {
                // 创建附件列表（包含图片预览）
                const attachments = [];
                for (const fileData of data.files) {
                    // 查找对应的原始文件以获取预览
                    const originalFile = Array.from(files).find(f => 
                        fileData.filename.includes(f.name)
                    );
                    
                    if (originalFile) {
                        const preview = await this.createImagePreview(originalFile);
                        attachments.push({
                            name: fileData.filename,
                            icon: 'image',
                            preview: preview,
                            size: this.formatFileSize(fileData.size),
                            path: fileData.path
                        });
                    }
                }

                // 添加带有附件的消息
                this.addMessage('user', `[上传了 ${data.total} 张图片]`, attachments);
                this.showToast(data.message, 'success');
            } else {
                this.showToast(data.message || '上传失败', 'error');
            }
        } catch (error) {
            this.showToast(`上传失败: ${error.message}`, 'error');
            console.error('上传错误:', error);
        }

        event.target.value = '';
    }

    createImagePreview(file) {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.readAsDataURL(file);
        });
    }

    getFileIcon(mimeType) {
        if (mimeType.startsWith('image/')) return 'image';
        if (mimeType.startsWith('video/')) return 'video';
        if (mimeType.startsWith('audio/')) return 'music';
        if (mimeType.includes('pdf')) return 'file-pdf';
        if (mimeType.includes('word') || mimeType.includes('document')) return 'file-word';
        if (mimeType.includes('excel') || mimeType.includes('sheet')) return 'file-excel';
        if (mimeType.includes('zip') || mimeType.includes('compressed')) return 'file-archive';
        return 'file';
    }

    // ========================================
    // 语音输入
    // ========================================

    recordVoice() {
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            this.showToast('您的浏览器不支持语音输入', 'error');
            return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SpeechRecognition();

        recognition.lang = 'zh-CN';
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onstart = () => {
            this.showToast('正在聆听，请说话...', 'success');
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            const input = document.getElementById('messageInput');
            input.value = transcript;
            this.autoResize(input);
        };

        recognition.onerror = (event) => {
            this.showToast('语音识别失败: ' + event.error, 'error');
        };

        recognition.start();
    }

    // ========================================
    // 工具列表
    // ========================================

    async loadTools() {
        try {
            const data = await this.apiRequest('/tools');
            const container = document.getElementById('toolsGrid');

            if (data.tools.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-toolbox"></i>
                        <p>暂无可用工具</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = data.tools.map(tool => `
                <div class="tool-card">
                    <div class="tool-header">
                        <div class="tool-icon">
                            <i class="fas fa-${this.getToolIcon(tool.type)}"></i>
                        </div>
                        <div>
                            <div class="tool-name">${tool.name}</div>
                            <span class="tool-type">${tool.type}</span>
                        </div>
                    </div>
                    <div class="tool-description">${tool.description || '暂无描述'}</div>
                </div>
            `).join('');
        } catch (error) {
            console.error('加载工具失败:', error);
        }
    }

    getToolIcon(type) {
        const iconMap = {
            'mcp': 'server',
            'skill': 'puzzle-piece',
            'function': 'code',
            'api': 'plug'
        };
        return iconMap[type] || 'tool';
    }

    // ========================================
    // MCP 服务器管理
    // ========================================

    async loadMCPServers() {
        try {
            const data = await this.apiRequest('/mcp/servers');
            const container = document.getElementById('mcpServersList');

            if (data.servers.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-server"></i>
                        <p>暂无 MCP 服务器配置</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = data.servers.map(server => `
                <div class="mcp-server-card">
                    <div class="mcp-server-info">
                        <div class="mcp-server-header">
                            <span class="mcp-server-name">${server.name}</span>
                            <span class="mcp-server-status ${server.running ? 'running' : 'stopped'}">
                                <i class="fas fa-${server.running ? 'check-circle' : 'times-circle'}"></i>
                                ${server.running ? '运行中' : '已停止'}
                            </span>
                        </div>
                        <div class="mcp-server-command">${server.command} ${server.args.join(' ')}</div>
                    </div>
                    <div class="mcp-server-actions">
                        ${server.running ? `
                            <button class="action-btn stop" onclick="app.stopMCPServer('${server.name}')">
                                <i class="fas fa-stop"></i> 停止
                            </button>
                        ` : `
                            <button class="action-btn start" onclick="app.startMCPServer('${server.name}')">
                                <i class="fas fa-play"></i> 启动
                            </button>
                        `}
                        <button class="action-btn" onclick="app.toggleMCPServer('${server.name}', ${!server.enabled})">
                            <i class="fas fa-${server.enabled ? 'ban' : 'check'}"></i>
                            ${server.enabled ? '停用' : '启用'}
                        </button>
                        <button class="action-btn" onclick="app.removeMCPServer('${server.name}')">
                            <i class="fas fa-trash"></i> 删除
                        </button>
                    </div>
                </div>
            `).join('');
        } catch (error) {
            console.error('加载 MCP 服务器失败:', error);
        }
    }

    showAddMCPServerModal() {
        document.getElementById('modalOverlay').classList.add('active');
        document.getElementById('addMCPServerModal').classList.add('active');
    }

    async addMCPServer() {
        const name = document.getElementById('mcpServerName').value.trim();
        const command = document.getElementById('mcpServerCommand').value.trim();
        const argsText = document.getElementById('mcpServerArgs').value.trim();

        if (!name || !command) {
            this.showToast('请填写服务器名称和启动命令', 'error');
            return;
        }

        const args = argsText.split('\n').filter(arg => arg.trim());

        try {
            await this.apiRequest('/mcp/servers', {
                method: 'POST',
                body: JSON.stringify({
                    name: name,
                    config: { command, args }
                })
            });

            this.showToast('MCP 服务器添加成功', 'success');
            this.closeModal();
            this.loadMCPServers();

            // 清空表单
            document.getElementById('mcpServerName').value = '';
            document.getElementById('mcpServerCommand').value = '';
            document.getElementById('mcpServerArgs').value = '';
        } catch (error) {
            console.error('添加 MCP 服务器失败:', error);
        }
    }

    async removeMCPServer(name) {
        if (!confirm(`确定要删除 MCP 服务器 "${name}" 吗？`)) return;

        try {
            await this.apiRequest(`/mcp/servers/${name}`, {
                method: 'DELETE'
            });
            this.showToast('MCP 服务器已删除', 'success');
            this.loadMCPServers();
        } catch (error) {
            console.error('删除 MCP 服务器失败:', error);
        }
    }

    async startMCPServer(name) {
        try {
            await this.apiRequest(`/mcp/servers/${name}/start`, {
                method: 'POST'
            });
            this.showToast('MCP 服务器已启动', 'success');
            this.loadMCPServers();
        } catch (error) {
            console.error('启动 MCP 服务器失败:', error);
        }
    }

    async stopMCPServer(name) {
        try {
            await this.apiRequest(`/mcp/servers/${name}/stop`, {
                method: 'POST'
            });
            this.showToast('MCP 服务器已停止', 'success');
            this.loadMCPServers();
        } catch (error) {
            console.error('停止 MCP 服务器失败:', error);
        }
    }

    async toggleMCPServer(name, enable) {
        try {
            await this.apiRequest(`/mcp/servers/${name}/${enable ? 'enable' : 'disable'}`, {
                method: 'POST'
            });
            this.showToast(`MCP 服务器已${enable ? '启用' : '停用'}`, 'success');
            this.loadMCPServers();
        } catch (error) {
            console.error('切换 MCP 服务器状态失败:', error);
        }
    }

    // ========================================
    // 工具管理 (MCP页面)
    // ========================================

    async loadMCPTools() {
        const container = document.getElementById('toolsList');
        if (!container) {
            console.log('[MCP工具] toolsList 容器不存在，跳过加载');
            return;
        }

        try {
            // 获取所有MCP工具（包括已禁用的）
            const toolsData = await this.apiRequest('/mcp/tools/all');
            console.log('[MCP工具] 获取到的工具数据:', toolsData);

            // 获取被禁用的工具
            let disabledTools = [];
            try {
                const response = await this.apiRequest('/mcp/tools/disabled');
                // 确保转换为数组
                disabledTools = Array.isArray(response) ? response : Object.values(response);
                console.log('[MCP工具] 被禁用的工具:', disabledTools);
            } catch (e) {
                console.warn('[MCP工具] 获取禁用工具列表失败:', e);
            }

            if (!toolsData.tools || toolsData.tools.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-tools"></i>
                        <p>暂无可用工具</p>
                    </div>
                `;
                return;
            }

            console.log('[MCP工具] 总工具数量:', toolsData.tools.length);
            console.log('[MCP工具] 所有工具名称:', toolsData.tools.map(t => t.name));
            console.log('[MCP工具] disabledTools 内容:', disabledTools);

            // 检查被禁用的工具是否在列表中
            disabledTools.forEach(dt => {
                const found = toolsData.tools.find(t => t.name === dt);
                console.log(`[MCP工具] 被禁用的工具 '${dt}' 在列表中:`, found ? '是' : '否');
            });

            container.innerHTML = toolsData.tools.map(tool => {
                // 使用更严格的比较，确保类型匹配
                const isDisabled = disabledTools.some(dt => dt === tool.name || dt.toString() === tool.name.toString());
                console.log(`[MCP工具] 工具 ${tool.name}: isDisabled=${isDisabled}`);
                return `
                    <div class="tool-card ${isDisabled ? 'disabled' : ''}">
                        <div class="tool-info">
                            <div class="tool-header">
                                <span class="tool-name">${tool.name}</span>
                                <span class="tool-type">${tool.type}</span>
                                ${isDisabled ? '<span class="badge" style="background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-left: 8px;">已禁用</span>' : ''}
                            </div>
                            <div class="tool-description">${tool.description || '无描述'}</div>
                        </div>
                        <div class="tool-actions">
                            <button class="action-btn ${isDisabled ? 'enable' : 'disable'}" onclick="app.toggleTool('${tool.name}', ${isDisabled})">
                                <i class="fas fa-${isDisabled ? 'check' : 'ban'}"></i>
                                ${isDisabled ? '启用' : '禁用'}
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (error) {
            console.error('加载工具列表失败:', error);
            container.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>加载工具列表失败</p>
                    <small>${error.message}</small>
                </div>
            `;
        }
    }

    showDisableToolModal() {
        document.getElementById('modalOverlay').classList.add('active');
        document.getElementById('disableToolModal').classList.add('active');
    }

    async disableTool() {
        const toolName = document.getElementById('disableToolName').value.trim();

        if (!toolName) {
            this.showToast('请输入工具名称', 'error');
            return;
        }

        try {
            await this.apiRequest(`/mcp/tools/${toolName}/disable`, {
                method: 'POST'
            });
            this.showToast(`工具 "${toolName}" 已禁用`, 'success');
            this.closeModal();
            this.loadMCPTools();

            // 清空表单
            document.getElementById('disableToolName').value = '';
        } catch (error) {
            console.error('禁用工具失败:', error);
            this.showToast('禁用工具失败: ' + error.message, 'error');
        }
    }

    async enableTool(toolName) {
        try {
            await this.apiRequest(`/mcp/tools/${toolName}/enable`, {
                method: 'POST'
            });
            this.showToast(`工具 "${toolName}" 已启用`, 'success');
            this.loadMCPTools();
        } catch (error) {
            console.error('启用工具失败:', error);
            this.showToast('启用工具失败: ' + error.message, 'error');
        }
    }

    async toggleTool(toolName, isDisabled) {
        if (isDisabled) {
            await this.enableTool(toolName);
        } else {
            // 如果当前是启用状态，则禁用
            try {
                await this.apiRequest(`/mcp/tools/${toolName}/disable`, {
                    method: 'POST'
                });
                this.showToast(`工具 "${toolName}" 已禁用`, 'success');
                this.loadMCPTools();
            } catch (error) {
                console.error('禁用工具失败:', error);
                this.showToast('禁用工具失败: ' + error.message, 'error');
            }
        }
    }

    // ========================================
    // Skill 管理
    // ========================================

    async loadSkills() {
        try {
            const data = await this.apiRequest('/skills');
            const container = document.getElementById('skillsList');

            if (data.skills.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-puzzle-piece"></i>
                        <p>暂无 Skill 配置</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = data.skills.map(skill => `
                <div class="skill-card">
                    <div class="skill-info">
                        <div class="skill-header">
                            <span class="skill-name">${skill.name}</span>
                            <div class="skill-badges">
                                <span class="badge ${skill.enabled ? 'badge-enabled' : 'badge-disabled'}">
                                    ${skill.enabled ? '已启用' : '已停用'}
                                </span>
                                ${skill.loaded ? '<span class="badge badge-loaded">已加载</span>' : ''}
                            </div>
                        </div>
                        <div class="skill-path">${skill.source_path}</div>
                    </div>
                    <div class="skill-actions">
                        <button class="action-btn" onclick="app.toggleSkill('${skill.name}', ${!skill.enabled})">
                            <i class="fas fa-${skill.enabled ? 'ban' : 'check'}"></i>
                            ${skill.enabled ? '停用' : '启用'}
                        </button>
                        <button class="action-btn" onclick="app.removeSkill('${skill.name}')">
                            <i class="fas fa-trash"></i> 删除
                        </button>
                    </div>
                </div>
            `).join('');
        } catch (error) {
            console.error('加载 Skill 失败:', error);
        }
    }

    showAddSkillModal() {
        document.getElementById('modalOverlay').classList.add('active');
        document.getElementById('addSkillModal').classList.add('active');
    }

    async addSkill() {
        const sourcePath = document.getElementById('skillSourcePath').value.trim();
        const name = document.getElementById('skillName').value.trim();

        if (!sourcePath) {
            this.showToast('请填写 Skill 目录路径', 'error');
            return;
        }

        try {
            await this.apiRequest('/skills/add', {
                method: 'POST',
                body: JSON.stringify({
                    source_dir: sourcePath,
                    skill_name: name || null
                })
            });

            this.showToast('Skill 添加成功', 'success');
            this.closeModal();
            this.loadSkills();

            // 清空表单
            document.getElementById('skillSourcePath').value = '';
            document.getElementById('skillName').value = '';
        } catch (error) {
            console.error('添加 Skill 失败:', error);
        }
    }

    async removeSkill(name) {
        if (!confirm(`确定要删除 Skill "${name}" 吗？`)) return;

        try {
            await this.apiRequest(`/skills/${name}`, {
                method: 'DELETE'
            });
            this.showToast('Skill 已删除', 'success');
            this.loadSkills();
        } catch (error) {
            console.error('删除 Skill 失败:', error);
        }
    }

    async toggleSkill(name, enable) {
        try {
            await this.apiRequest(`/skills/${name}/${enable ? 'enable' : 'disable'}`, {
                method: 'POST'
            });
            this.showToast(`Skill 已${enable ? '启用' : '停用'}`, 'success');
            this.loadSkills();
        } catch (error) {
            console.error('切换 Skill 状态失败:', error);
        }
    }

    // ========================================
    // 记忆管理
    // ========================================

    async loadMemoryStats() {
        try {
            const data = await this.apiRequest('/memory/stats');
            const container = document.getElementById('memoryStats');

            container.innerHTML = `
                <div class="stat-card">
                    <div class="stat-header">
                        <div class="stat-icon">
                            <i class="fas fa-comment-dots"></i>
                        </div>
                        <div class="stat-title">文本记忆</div>
                    </div>
                    <div class="stat-value">${data.text_memory?.message_count || 0}</div>
                    <div class="stat-label">消息数量</div>
                </div>
                <div class="stat-card">
                    <div class="stat-header">
                        <div class="stat-icon">
                            <i class="fas fa-database"></i>
                        </div>
                        <div class="stat-title">向量记忆</div>
                    </div>
                    <div class="stat-value">${data.vector_memory?.document_count || 0}</div>
                    <div class="stat-label">文档数量</div>
                </div>
            `;
        } catch (error) {
            console.error('加载记忆统计失败:', error);
        }
    }

    async searchMemory() {
        const query = document.getElementById('memorySearchInput').value.trim();
        if (!query) return;

        try {
            const data = await this.apiRequest('/memory/search', {
                method: 'POST',
                body: JSON.stringify({ query, top_k: 5 })
            });

            const container = document.getElementById('memorySearchResults');

            if (data.results.length === 0) {
                container.innerHTML = '<p style="color: var(--text-muted); text-align: center;">未找到相关记忆</p>';
                return;
            }

            container.innerHTML = data.results.map(result => `
                <div class="search-result-item">
                    <div class="search-result-content">${result.content}</div>
                    <div class="search-result-meta">
                        相似度: ${(result.score * 100).toFixed(1)}%
                    </div>
                </div>
            `).join('');
        } catch (error) {
            console.error('搜索记忆失败:', error);
        }
    }

    async clearMemory() {
        if (!confirm('确定要清除所有记忆吗？此操作不可恢复。')) return;

        try {
            await this.apiRequest('/memory/clear', {
                method: 'POST'
            });
            this.showToast('记忆已清除', 'success');
            this.loadMemoryStats();
        } catch (error) {
            console.error('清除记忆失败:', error);
        }
    }

    // ========================================
    // Token 统计
    // ========================================

    async loadTokenStats() {
        try {
            const data = await this.apiRequest('/tokens');
            const container = document.getElementById('tokenStats');

            container.innerHTML = `
                <div class="token-stats-grid">
                    <div class="token-stat-section">
                        <h3><i class="fas fa-clock"></i> 本轮对话</h3>
                        <div class="token-stat-item">
                            <span class="token-stat-label">输入 Tokens</span>
                            <span class="token-stat-value">${data.round?.prompt_tokens?.toLocaleString() || 0}</span>
                        </div>
                        <div class="token-stat-item">
                            <span class="token-stat-label">输出 Tokens</span>
                            <span class="token-stat-value">${data.round?.completion_tokens?.toLocaleString() || 0}</span>
                        </div>
                        <div class="token-stat-item">
                            <span class="token-stat-label">总计 Tokens</span>
                            <span class="token-stat-value" style="color: var(--primary-color);">
                                ${data.round?.total_tokens?.toLocaleString() || 0}
                            </span>
                        </div>
                    </div>
                    <div class="token-stat-section">
                        <h3><i class="fas fa-chart-bar"></i> 本次会话累计</h3>
                        <div class="token-stat-item">
                            <span class="token-stat-label">输入 Tokens</span>
                            <span class="token-stat-value">${data.session?.prompt_tokens?.toLocaleString() || 0}</span>
                        </div>
                        <div class="token-stat-item">
                            <span class="token-stat-label">输出 Tokens</span>
                            <span class="token-stat-value">${data.session?.completion_tokens?.toLocaleString() || 0}</span>
                        </div>
                        <div class="token-stat-item">
                            <span class="token-stat-label">总计 Tokens</span>
                            <span class="token-stat-value" style="color: var(--primary-color);">
                                ${data.session?.total_tokens?.toLocaleString() || 0}
                            </span>
                        </div>
                    </div>
                </div>
            `;
        } catch (error) {
            console.error('加载 Token 统计失败:', error);
        }
    }

    // ========================================
    // 模态框
    // ========================================

    closeModal() {
        document.getElementById('modalOverlay').classList.remove('active');
        document.querySelectorAll('.modal').forEach(modal => {
            modal.classList.remove('active');
        });
    }

    // ========================================
    // Toast 通知
    // ========================================

    showToast(message, type = 'info') {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = {
            success: 'check-circle',
            error: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };

        toast.innerHTML = `
            <i class="fas fa-${icons[type]}"></i>
            <span>${message}</span>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // ========================================
    // 对话历史管理（使用后端日志）
    // ========================================

    async loadChatHistory() {
        try {
            const data = await this.apiRequest('/history');
            if (data.success) {
                this.chatHistory = data.history.map(item => ({
                    id: item.id,
                    title: item.user_message.slice(0, 20) + (item.user_message.length > 20 ? '...' : ''),
                    preview: item.assistant_response.slice(0, 30) + (item.assistant_response.length > 30 ? '...' : ''),
                    timestamp: new Date(item.timestamp).getTime(),
                    user_message: item.user_message,
                    assistant_response: item.assistant_response,
                    token_usage: item.token_usage,
                    execution_time: item.execution_time
                }));
                this.renderChatHistory();
            }
        } catch (e) {
            console.error('加载对话历史失败:', e);
            this.chatHistory = [];
        }
    }

    renderChatHistory() {
        const container = document.getElementById('chatHistoryList');
        if (!container) return;

        if (this.chatHistory.length === 0) {
            container.innerHTML = '<div class="empty-history">暂无对话历史</div>';
            return;
        }

        container.innerHTML = this.chatHistory.map(chat => {
            const isActive = chat.id === this.currentChatId;
            const time = new Date(chat.timestamp).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });

            return `
                <div class="chat-history-item ${isActive ? 'active' : ''}" data-chat-id="${chat.id}" onclick="app.switchChat('${chat.id}')">
                    <div class="chat-history-icon">
                        <i class="fas fa-comment"></i>
                    </div>
                    <div class="chat-history-info">
                        <div class="chat-history-title-text">${this.escapeHtml(chat.title)}</div>
                        <div class="chat-history-preview">${this.escapeHtml(chat.preview)}</div>
                    </div>
                    <div class="chat-history-time">${time}</div>
                    <button class="chat-history-delete" onclick="event.stopPropagation(); app.deleteChat('${chat.id}')">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
        }).join('');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async switchChat(chatId) {
        if (chatId === this.currentChatId) return;

        // 从历史记录中找到对应的对话
        const chat = this.chatHistory.find(c => c.id === chatId);
        if (!chat) return;

        // 切换到历史对话
        this.currentChatId = chatId;

        // 显示历史对话内容
        const container = document.getElementById('chatMessages');
        container.innerHTML = '';

        // 添加用户消息
        this.addMessage('user', chat.user_message);

        // 添加助手回复
        this.addMessage('assistant', chat.assistant_response);

        this.renderChatHistory();
        this.showToast('已切换到历史对话', 'success');
    }

    async deleteChat(chatId) {
        if (!confirm('确定要删除这个对话吗？')) return;

        try {
            // 从ID中提取会话ID (格式: session_20260412_105008_0)
            const parts = chatId.split('_');
            const sessionId = parts.slice(0, 3).join('_'); // session_20260412_105008

            console.log('删除会话:', sessionId);

            await this.apiRequest(`/history/${sessionId}`, {
                method: 'DELETE'
            });

            // 从本地数组中移除
            this.chatHistory = this.chatHistory.filter(c => !c.id.startsWith(sessionId));

            // 重新渲染
            this.renderChatHistory();

            // 如果删除的是当前对话，创建新对话
            if (chatId === this.currentChatId) {
                this.newChat();
            }

            this.showToast('对话已删除', 'success');
        } catch (e) {
            console.error('删除对话失败:', e);
            this.showToast('删除失败: ' + e.message, 'error');
        }
    }

    async clearAllHistory() {
        if (!confirm('确定要清除所有对话历史吗？此操作不可恢复。')) return;

        try {
            // 获取所有唯一的会话ID
            const sessionIds = new Set();
            for (const chat of this.chatHistory) {
                const parts = chat.id.split('_');
                const sessionId = parts.slice(0, 3).join('_');
                sessionIds.add(sessionId);
            }

            // 逐个删除
            for (const sessionId of sessionIds) {
                try {
                    await this.apiRequest(`/history/${sessionId}`, {
                        method: 'DELETE'
                    });
                } catch (e) {
                    console.error(`删除会话 ${sessionId} 失败:`, e);
                }
            }

            // 清空本地数组
            this.chatHistory = [];
            this.renderChatHistory();
            this.newChat();
            this.showToast('所有历史已清除', 'success');
        } catch (e) {
            console.error('清除历史失败:', e);
            this.showToast('清除失败', 'error');
        }
    }

    newChat() {
        // 创建新对话
        this.sessionId = this.generateSessionId();
        this.currentChatId = this.sessionId;
        this.messages = [];

        // 清空聊天区域并显示欢迎消息
        document.getElementById('chatMessages').innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <i class="fas fa-robot"></i>
                </div>
                <h3>你好！我是 AI 智能助手</h3>
                <p>我可以帮你解答问题、处理文件、管理工具等。试着问我点什么吧！</p>
                <div class="quick-actions">
                    <button class="quick-btn" onclick="app.sendQuickMessage('介绍一下你自己')">
                        <i class="fas fa-user"></i>
                        介绍自己
                    </button>
                    <button class="quick-btn" onclick="app.sendQuickMessage('查看可用工具')">
                        <i class="fas fa-tools"></i>
                        查看工具
                    </button>
                    <button class="quick-btn" onclick="app.sendQuickMessage('帮我搜索资料')">
                        <i class="fas fa-search"></i>
                        搜索资料
                    </button>
                </div>
            </div>
        `;

        this.renderChatHistory();
    }

    toggleHistory() {
        const chatHistory = document.getElementById('chatHistory');
        const icon = document.getElementById('historyToggleIcon');

        if (chatHistory.classList.contains('collapsed')) {
            chatHistory.classList.remove('collapsed');
            icon.style.transform = 'rotate(0deg)';
        } else {
            chatHistory.classList.add('collapsed');
            icon.style.transform = 'rotate(-90deg)';
        }
    }
}

// 初始化应用
const app = new App();
