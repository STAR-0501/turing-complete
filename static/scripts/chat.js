/**
 * 聊天模块
 * 处理与 AI 的对话和指令同步
 */
import { loadFromServer } from './app.js';

const chatContainer = document.getElementById('chat-container');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-chat');
const toggleBtn = document.getElementById('toggle-chat');
const chatHeader = document.querySelector('.chat-header');
const thinkingToggle = document.getElementById('thinking-toggle');
const THINKING_MARKER = '__TC_THINKING__';
const ANSWER_MARKER = '__TC_ANSWER__';
const STATE_CHANGED_MARKER = '__TC_STATE_CHANGED__';
const ROUND_MARKER = '__TC_ROUND__';

let thinkingMode = false;

// 初始化聊天窗口
export function initChat() {
    // 切换折叠状态
    toggleBtn.addEventListener('click', (e) => {
        e.stopPropagation(); // 防止触发拖拽开始
        chatContainer.classList.toggle('collapsed');
        toggleBtn.textContent = chatContainer.classList.contains('collapsed') ? '+' : '_';
    });

    // 实现拖拽
    let isDragging = false;
    let offset = { x: 0, y: 0 };

    chatHeader.addEventListener('mousedown', (e) => {
        if (e.target === toggleBtn) return;
        
        isDragging = true;
        // 获取当前鼠标相对于容器左上角的偏移
        const rect = chatContainer.getBoundingClientRect();
        offset.x = e.clientX - rect.left;
        offset.y = e.clientY - rect.top;
        
        // 拖拽时禁用过渡效果
        chatContainer.style.transition = 'none';
        
        // 改变鼠标指针
        document.body.style.cursor = 'move';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        
        // 计算新位置
        let left = e.clientX - offset.x;
        let top = e.clientY - offset.y;
        
        // 限制在屏幕内
        const rect = chatContainer.getBoundingClientRect();
        left = Math.max(0, Math.min(window.innerWidth - rect.width, left));
        top = Math.max(0, Math.min(window.innerHeight - rect.height, top));
        
        // 应用新位置
        chatContainer.style.left = left + 'px';
        chatContainer.style.top = top + 'px';
        chatContainer.style.right = 'auto';
        chatContainer.style.bottom = 'auto';
    });

    document.addEventListener('mouseup', () => {
        if (!isDragging) return;
        isDragging = false;
        
        // 恢复过渡效果
        chatContainer.style.transition = 'height 0.3s ease';
        document.body.style.cursor = 'default';
    });

    // 发送消息事件
    sendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    // 思考模式切换
    if (thinkingToggle) {
        thinkingToggle.addEventListener('click', () => {
            thinkingMode = !thinkingMode;
            thinkingToggle.classList.toggle('active', thinkingMode);
            thinkingToggle.title = thinkingMode ? '深度思考模式已开启（DeepSeek深度推理）' : '开启DeepSeek思考模式（深度推理，耗时更长但结果更准确）';
        });
    }
}

// 发送消息到后端
async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    // 添加用户消息到界面
    addMessage(text, 'user');
    chatInput.value = '';

    // 创建 AI 消息容器
    let aiMsgDiv = addMessage('', 'ai');
    let fullContent = '';
    let lastRenderTime = 0;
    const renderInterval = 50;
    const escapeHtml = (text) => String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

    const parseSections = (raw) => {
        // Extract LAST occurrence of each tag (to show the latest round's content)
        const extractLastTag = (text, tag) => {
            const regex = new RegExp(`<${tag}>([\\s\\S]*?)<\\/${tag}>`, 'gi');
            let match;
            let lastMatch = '';
            while ((match = regex.exec(text)) !== null) {
                lastMatch = match[1].trim();
            }
            return lastMatch;
        };
        // Extract new 5-mode sections - use LAST occurrence for multi-round display
        let think = extractLastTag(raw, 'think');
        let plan = extractLastTag(raw, 'plan');
        let build = extractLastTag(raw, 'build');
        let observe = extractLastTag(raw, 'observe');
        let sum = extractLastTag(raw, 'sum');
        // Fallback to old formats for backward compat
        if (!build) build = extractLastTag(raw, 'commands');
        if (!observe) observe = extractLastTag(raw, 'verify');
        let answer = extractLastTag(raw, 'answer');

        // If no <answer> tag found, fall back to stripped answer text
        if (!answer) {
            answer = raw
                .replace(/<think>[\s\S]*?<\/think>/gi, '')
                .replace(/<plan>[\s\S]*?<\/plan>/gi, '')
                .replace(/<build>[\s\S]*?<\/build>/gi, '')
                .replace(/<observe>[\s\S]*?<\/observe>/gi, '')
                .replace(/<sum>[\s\S]*?<\/sum>/gi, '')
                .replace(/<answer>[\s\S]*?<\/answer>/gi, '')
                .replace(/<commands>[\s\S]*?<\/commands>/gi, '')
                .replace(/<verify>[\s\S]*?<\/verify>/gi, '')
                .replace(new RegExp(STATE_CHANGED_MARKER, 'g'), '')
                .trim();
        }

        return { think, plan, build, observe, sum, answer };
    };

    const renderContent = () => {
        const sections = parseSections(fullContent);
        const hasContent = sections.think || sections.plan || sections.build || sections.observe || sections.sum || sections.answer;
        if (!hasContent) {
            aiMsgDiv.textContent = '正在思考...';
            chatMessages.scrollTop = chatMessages.scrollHeight;
            return;
        }
        const html = [];
        if (sections.think) {
            html.push(
                `<details open style="margin-bottom:6px;font-size:12px;">` +
                `<summary style="cursor:pointer;opacity:0.7;font-size:11px;">🤔 思考分析</summary>` +
                `<div style="white-space:pre-wrap;margin-top:4px;padding:4px 8px;background:rgba(255,255,200,0.15);border-radius:4px;">${escapeHtml(sections.think)}</div>` +
                `</details>`
            );
        }
        if (sections.plan) {
            html.push(
                `<details style="margin-bottom:6px;font-size:12px;">` +
                `<summary style="cursor:pointer;opacity:0.7;font-size:11px;">📋 计划</summary>` +
                `<div style="white-space:pre-wrap;margin-top:4px;padding:4px 8px;background:rgba(200,255,200,0.15);border-radius:4px;">${escapeHtml(sections.plan)}</div>` +
                `</details>`
            );
        }
        if (sections.build) {
            html.push(
                `<details style="margin-bottom:6px;font-size:12px;">` +
                `<summary style="cursor:pointer;opacity:0.7;font-size:11px;">🔧 构建命令</summary>` +
                `<div style="white-space:pre-wrap;margin-top:4px;padding:4px 8px;background:rgba(200,200,255,0.15);border-radius:4px;font-family:monospace;font-size:11px;">${escapeHtml(sections.build)}</div>` +
                `</details>`
            );
        }
        if (sections.observe) {
            html.push(
                `<details style="margin-bottom:6px;font-size:12px;">` +
                `<summary style="cursor:pointer;opacity:0.7;font-size:11px;">🔍 观察/验证</summary>` +
                `<div style="white-space:pre-wrap;margin-top:4px;padding:4px 8px;background:rgba(255,200,255,0.15);border-radius:4px;">${escapeHtml(sections.observe)}</div>` +
                `</details>`
            );
        }
        if (sections.sum) {
            html.push(
                `<details style="margin-bottom:6px;font-size:12px;">` +
                `<summary style="cursor:pointer;opacity:0.7;font-size:11px;">📝 总结</summary>` +
                `<div style="white-space:pre-wrap;margin-top:4px;padding:4px 8px;background:rgba(200,255,255,0.15);border-radius:4px;">${escapeHtml(sections.sum)}</div>` +
                `</details>`
            );
        }
        if (sections.answer) {
            html.push(
                `<div><div style="font-size:11px;opacity:0.7;margin-bottom:2px;">💬 输出</div>` +
                `<div style="white-space:pre-wrap;">${escapeHtml(sections.answer)}</div></div>`
            );
        }
        aiMsgDiv.innerHTML = html.join('');
        chatMessages.scrollTop = chatMessages.scrollHeight;
    };

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, thinking_mode: thinkingMode })
        });

        if (!response.ok) throw new Error('Network response was not ok');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            
            // Detect round boundaries: finalize current div, create new one per round
            if (chunk.includes(ROUND_MARKER)) {
                renderContent();
                aiMsgDiv = addMessage('', 'ai');
                fullContent = '';
                // Extract round number for display
                const rm = chunk.match(/__TC_ROUND__(\d+)/);
                if (rm) {
                    const label = document.createElement('div');
                    label.className = 'message system';
                    label.style.fontSize = '10px';
                    label.style.opacity = '0.6';
                    label.textContent = `--- 第 ${rm[1]} 轮 ---`;
                    chatMessages.appendChild(label);
                }
                continue;
            }
            
            if (chunk.includes(STATE_CHANGED_MARKER)) {
                loadFromServer();
            }

            fullContent += chunk;
            const now = performance.now();
            if (now - lastRenderTime >= renderInterval) {
                renderContent();
                lastRenderTime = now;
            }
        }
        renderContent();

        // 检查是否执行了指令（检查 <build> 或 <commands> 标签）
        const buildMatch = fullContent.match(/<build>([\s\S]*?)<\/build>/i);
        const cmdMatch = fullContent.match(/<commands>([\s\S]*?)<\/commands>/);
        const hasBuild = buildMatch && buildMatch[1].trim() && buildMatch[1].trim() !== '[]';
        const hasCmd = cmdMatch && cmdMatch[1].trim() && cmdMatch[1].trim() !== '[]';
        if (hasBuild || hasCmd) {
            // 立即触发状态加载和渲染
            await loadFromServer();

            const systemMsg = document.createElement('div');
            systemMsg.className = 'message ai';
            systemMsg.style.fontSize = '11px';
            systemMsg.style.opacity = '0.7';
            systemMsg.textContent = '[系统] 电路操作指令已执行。';
            chatMessages.appendChild(systemMsg);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

    } catch (error) {
        aiMsgDiv.textContent = `错误: ${error.message || '连接失败'}`;
        console.error('Chat error:', error);
    }
}

// 在界面上添加消息
function addMessage(text, type, isLoading = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${type}`;
    msgDiv.textContent = text;
    
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return msgDiv;
}

// 移除消息
function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// 自动初始化
initChat();
