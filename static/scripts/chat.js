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
const THINKING_MARKER = '__TC_THINKING__';
const ANSWER_MARKER = '__TC_ANSWER__';

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
}

// 发送消息到后端
async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    // 添加用户消息到界面
    addMessage(text, 'user');
    chatInput.value = '';

    // 创建 AI 消息容器
    const aiMsgDiv = addMessage('', 'ai');
    let fullContent = '';
    let lastRenderTime = 0;
    const renderInterval = 50;
    const escapeHtml = (text) => String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

    const splitThinkingAndAnswer = (raw) => {
        const cleaned = raw.replace(/<commands>[\s\S]*?<\/commands>/g, '');
        const thinkIdx = cleaned.indexOf(THINKING_MARKER);
        const answerIdx = cleaned.indexOf(ANSWER_MARKER);
        let thinking = '';
        let answer = '';
        if (thinkIdx === -1 && answerIdx === -1) {
            answer = cleaned.trim();
            return { thinking, answer };
        }
        if (thinkIdx !== -1) {
            const fromThink = cleaned.slice(thinkIdx + THINKING_MARKER.length);
            const answerPosInThink = fromThink.indexOf(ANSWER_MARKER);
            if (answerPosInThink === -1) {
                thinking = fromThink.trim();
            } else {
                thinking = fromThink.slice(0, answerPosInThink).trim();
                answer = fromThink.slice(answerPosInThink + ANSWER_MARKER.length).trim();
            }
            return { thinking, answer };
        }
        answer = cleaned.slice(answerIdx + ANSWER_MARKER.length).trim();
        return { thinking, answer };
    };

    const renderContent = () => {
        const { thinking, answer } = splitThinkingAndAnswer(fullContent);
        if (!thinking && !answer) {
            aiMsgDiv.textContent = '正在思考...';
            chatMessages.scrollTop = chatMessages.scrollHeight;
            return;
        }
        const sections = [];
        if (thinking) {
            sections.push(
                `<div style="margin-bottom:8px;"><div style="font-size:11px;opacity:0.7;margin-bottom:2px;">思考过程</div><div style="white-space:pre-wrap;">${escapeHtml(thinking)}</div></div>`
            );
        }
        if (answer) {
            sections.push(
                `<div><div style="font-size:11px;opacity:0.7;margin-bottom:2px;">正式输出</div><div style="white-space:pre-wrap;">${escapeHtml(answer)}</div></div>`
            );
        }
        aiMsgDiv.innerHTML = sections.join('');
        chatMessages.scrollTop = chatMessages.scrollHeight;
    };

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        if (!response.ok) throw new Error('Network response was not ok');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            fullContent += chunk;
            const now = performance.now();
            if (now - lastRenderTime >= renderInterval) {
                renderContent();
                lastRenderTime = now;
            }
        }
        renderContent();

        // 检查是否执行了指令（提取标签内容并检查是否为空列表）
        const match = fullContent.match(/<commands>([\s\S]*?)<\/commands>/);
        if (match && match[1].trim() !== '[]') {
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
