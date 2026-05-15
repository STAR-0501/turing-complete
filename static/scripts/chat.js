/**
 * Agent 侧边栏模块
 * 处理与 AI 的对话和指令同步 — 右侧滑入侧边栏
 */
import { loadFromServer } from './app.js';

const agentSidebar = document.getElementById('agent-sidebar');
const agentToggle = document.getElementById('agent-toggle');
const agentMessages = document.getElementById('agent-messages');
const agentInput = document.getElementById('agent-input');
const agentSend = document.getElementById('agent-send');
const agentThink = document.getElementById('agent-think');
const agentMinimize = document.getElementById('agent-minimize');
const agentResizeHandle = document.getElementById('agent-resize-handle');
const agentPromptSuggestions = document.getElementById('agent-prompt-suggestions');
const THINKING_MARKER = '__TC_THINKING__';
const ANSWER_MARKER = '__TC_ANSWER__';
const STATE_CHANGED_MARKER = '__TC_STATE_CHANGED__';

let thinkingMode = false;

// 初始化 Agent 侧边栏
export function initChat() {
  // 切换按钮：打开侧边栏
  agentToggle.addEventListener('click', () => {
    agentSidebar.classList.add('open');
    agentToggle.classList.add('hidden');
    agentInput.focus();
  });

  // 最小化按钮：关闭侧边栏
  agentMinimize.addEventListener('click', () => {
    agentSidebar.classList.remove('open');
    agentToggle.classList.remove('hidden');
  });

  // 拖拽拉伸手柄：调整侧边栏宽度
  let isResizing = false;
  const MIN_WIDTH = 280;
  const MAX_WIDTH = 600;

  agentResizeHandle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    e.stopPropagation();
    isResizing = true;
    agentResizeHandle.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const newWidth = window.innerWidth - e.clientX;
    const clamped = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, newWidth));
    agentSidebar.style.width = clamped + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!isResizing) return;
    isResizing = false;
    agentResizeHandle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });

  // textarea 自动扩展高度（无滚动条，随内容增长）
  const autoResize = () => {
    agentInput.style.height = 'auto';
    agentInput.style.height = agentInput.scrollHeight + 'px';
  };

  // 输入框内容变化时切换快捷提示的显示（空则显示，有内容则隐藏）
  const updateSuggestions = () => {
    const empty = agentInput.value.trim() === '';
    agentPromptSuggestions.classList.toggle('visible', empty);
  };
  agentInput.addEventListener('input', () => {
    autoResize();
    updateSuggestions();
  });
  // 初始状态：如果输入框为空则显示快捷提示
  updateSuggestions();
  autoResize();

  // 快捷提示按钮：填充输入框
  agentPromptSuggestions.querySelectorAll('.agent-suggestion-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      agentInput.value = btn.getAttribute('data-prompt');
      agentPromptSuggestions.classList.remove('visible');
      autoResize();
      agentInput.focus();
    });
  });

  // 发送消息
  agentSend.addEventListener('click', sendMessage);
  agentInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sendMessage();
    }
  });

  // 思考模式切换
  if (agentThink) {
    agentThink.addEventListener('click', () => {
      thinkingMode = !thinkingMode;
      agentThink.classList.toggle('active', thinkingMode);
      agentThink.title = thinkingMode
        ? '深度思考模式已开启（DeepSeek深度推理）'
        : '开启DeepSeek思考模式（深度推理，耗时更长但结果更准确）';
    });
  }
}

// 发送消息到后端
async function sendMessage() {
  const text = agentInput.value.trim();
  if (!text) return;

  addMessage(text, 'user');
  agentInput.value = '';

  // 创建 AI 消息容器
  const aiMsgDiv = addMessage('', 'ai');
  let fullContent = '';
  let lastRenderTime = 0;
  const renderInterval = 50;
  const escapeHtml = (text) =>
    String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');

  const splitThinkingAndAnswer = (raw) => {
    const cleaned = raw
      .replace(/<commands>[\s\S]*?<\/commands>/g, '')
      .replace(new RegExp(STATE_CHANGED_MARKER, 'g'), '');
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
      agentMessages.scrollTop = agentMessages.scrollHeight;
      return;
    }
    const sections = [];
    if (thinking) {
      sections.push(
        `<div class="msg-thinking-label">思考过程</div><div class="msg-thinking-content">${escapeHtml(thinking)}</div>`,
      );
    }
    if (answer) {
      if (sections.length > 0) sections.push('<div style="height:6px"></div>');
      sections.push(
        `<div class="msg-answer-label">正式输出</div><div class="msg-answer-content">${escapeHtml(answer)}</div>`,
      );
    }
    aiMsgDiv.innerHTML = sections.join('');
    agentMessages.scrollTop = agentMessages.scrollHeight;
  };

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        thinking_mode: thinkingMode,
      }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      // 过滤掉状态变更标记（由后端直接处理）
      if (chunk.includes(STATE_CHANGED_MARKER)) {
        loadFromServer();
      }
      const cleanChunk = chunk.replace(new RegExp(STATE_CHANGED_MARKER, 'g'), '');
      fullContent += cleanChunk;

      const now = Date.now();
      if (now - lastRenderTime > renderInterval) {
        renderContent();
        lastRenderTime = now;
      }
    }
    renderContent();
  } catch (err) {
    aiMsgDiv.textContent = '连接失败，请检查后端是否运行。';
    console.error('Chat error:', err);
  }
}

// 添加消息到界面
export function addMessage(text, type) {
  const div = document.createElement('div');
  div.className = `agent-message ${type}`;
  if (type === 'ai') {
    // AI 消息用 textContent 初始占位，后续 SSE 流式填充 innerHTML
    div.textContent = text || '...';
  } else if (type === 'round') {
    div.className = 'agent-round-marker';
    div.textContent = text;
  } else {
    div.textContent = text;
  }
  agentMessages.appendChild(div);
  agentMessages.scrollTop = agentMessages.scrollHeight;
  return div;
}

// 暴露给 app.js 用于 round 标记和自动展开
export function openAgentSidebar() {
  agentSidebar.classList.add('open');
  agentToggle.classList.add('hidden');
}

export function getAgentMessages() {
  return agentMessages;
}

// 自动初始化
initChat();
