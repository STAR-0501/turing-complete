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
const conversationSelect = document.getElementById('conversation-select');
const THINKING_MARKER = '__TC_THINKING__';
const ANSWER_MARKER = '__TC_ANSWER__';
const STATE_CHANGED_MARKER = '__TC_STATE_CHANGED__';

let thinkingMode = false;
let currentSessionId = ''; // 当前对话的 session_id

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

  // 拖拽拉伸手柄：调整侧边栏宽度（仅拖拽时挂载 document 监听器，释放后立即移除）
  let isResizing = false;
  const MIN_WIDTH = 280;
  const MAX_WIDTH = 600;

  const onResizeMove = (e) => {
    if (!isResizing) return;
    const newWidth = window.innerWidth - e.clientX;
    const clamped = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, newWidth));
    agentSidebar.style.width = clamped + 'px';
  };

  const onResizeEnd = () => {
    if (!isResizing) return;
    isResizing = false;
    agentResizeHandle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    document.removeEventListener('mousemove', onResizeMove);
    document.removeEventListener('mouseup', onResizeEnd);
  };

  agentResizeHandle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    e.stopPropagation();
    isResizing = true;
    agentResizeHandle.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onResizeMove);
    document.addEventListener('mouseup', onResizeEnd);
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

  // 加载历史对话列表
  loadConversationList();

  // 对话选择切换
  conversationSelect.addEventListener('change', () => {
    const sessId = conversationSelect.value;
    if (!sessId) {
      // 选择"当前对话"——清空并显示默认欢迎语
      const welcomeHtml = '<div class="agent-message ai">你好！我是 Agent，可以帮你构建电路。例如："帮我放一个与门"或"连接这两个元件"。</div>';
      agentMessages.innerHTML = welcomeHtml;
      return;
    }
    loadConversationMessages(sessId);
  });

  // 检查配置状态，决定显示表单还是聊天
  checkAiConfig();

  // 密码显示/隐藏切换
  const pwdToggle = document.getElementById('cfg-pwd-toggle');
  const cfgApiKey = document.getElementById('cfg-api-key');
  if (pwdToggle && cfgApiKey) {
    pwdToggle.addEventListener('click', () => {
      const isPassword = cfgApiKey.type === 'password';
      cfgApiKey.type = isPassword ? 'text' : 'password';
      pwdToggle.textContent = isPassword ? '🙈' : '👁';
    });
  }

  // 保存配置按钮
  const cfgSaveBtn = document.getElementById('cfg-save-btn');
  if (cfgSaveBtn) {
    cfgSaveBtn.addEventListener('click', saveAiConfig);
  }

  // 测试连接按钮
  const cfgTestBtn = document.getElementById('cfg-test-btn');
  if (cfgTestBtn) {
    cfgTestBtn.addEventListener('click', testAiConfig);
  }

  // 更换 API Key 按钮
  const changeBtn = document.getElementById('btn-change-apikey');
  if (changeBtn) {
    changeBtn.addEventListener('click', () => {
      const configForm = document.getElementById('ai-config-form');
      if (configForm) {
        configForm.style.display = 'block';
        changeBtn.style.display = 'none';
        // 隐藏聊天/输入区域
        const promptSuggestions = document.getElementById('agent-prompt-suggestions');
        const inputArea = document.querySelector('.agent-input-area');
        const welcomeMsg = document.querySelector('.agent-message');
        if (promptSuggestions) promptSuggestions.style.display = 'none';
        if (inputArea) inputArea.style.display = 'none';
        if (welcomeMsg) welcomeMsg.style.display = 'none';
      }
    });
  }
}

// 检查 AI 配置状态，切换表单/聊天界面
async function checkAiConfig() {
  const configForm = document.getElementById('ai-config-form');
  const promptSuggestions = document.getElementById('agent-prompt-suggestions');
  const inputArea = document.querySelector('.agent-input-area');
  const welcomeMsg = document.querySelector('.agent-message');
  const changeBtn = document.getElementById('btn-change-apikey');

  if (!configForm) return;

  try {
    const res = await fetch('/api/config');
    const data = await res.json();

    if (data.configured) {
      configForm.style.display = 'none';
      if (promptSuggestions) promptSuggestions.style.display = '';
      if (inputArea) inputArea.style.display = '';
      if (welcomeMsg) welcomeMsg.style.display = '';
      if (changeBtn) changeBtn.style.display = '';  // 显示更换按钮
    } else {
      configForm.style.display = 'block';
      if (promptSuggestions) promptSuggestions.style.display = 'none';
      if (inputArea) inputArea.style.display = 'none';
      if (welcomeMsg) welcomeMsg.style.display = 'none';
      if (changeBtn) changeBtn.style.display = 'none';
      // 填充当前值
      const baseUrlInput = document.getElementById('cfg-base-url');
      const modelInput = document.getElementById('cfg-model');
      const maxTokensInput = document.getElementById('cfg-max-tokens');
      const connectTimeoutInput = document.getElementById('cfg-connect-timeout');
      const readTimeoutInput = document.getElementById('cfg-read-timeout');
      if (baseUrlInput && data.base_url) baseUrlInput.value = data.base_url;
      if (modelInput && data.model) modelInput.value = data.model;
      if (maxTokensInput && data.max_tokens) maxTokensInput.value = data.max_tokens;
      if (connectTimeoutInput && data.connect_timeout) connectTimeoutInput.value = data.connect_timeout;
      if (readTimeoutInput && data.read_timeout) readTimeoutInput.value = data.read_timeout;
    }
  } catch (err) {
    console.error('检查 AI 配置失败:', err);
  }
}

// 保存 AI 配置
async function saveAiConfig() {
  const cfgSaveBtn = document.getElementById('cfg-save-btn');
  const cfgStatus = document.getElementById('cfg-status');
  if (!cfgSaveBtn || !cfgStatus) return;

  const apiKey = document.getElementById('cfg-api-key').value.trim();
  const baseUrl = document.getElementById('cfg-base-url').value.trim();
  const model = document.getElementById('cfg-model').value.trim();
  const maxTokens = parseInt(document.getElementById('cfg-max-tokens').value, 10) || 4000;
  const connectTimeout = parseInt(document.getElementById('cfg-connect-timeout').value, 10) || 10;
  const readTimeout = parseInt(document.getElementById('cfg-read-timeout').value, 10) || 180;

  if (!apiKey) {
    cfgStatus.textContent = '请输入 API Key';
    cfgStatus.style.color = '#ff6b6b';
    return;
  }

  cfgSaveBtn.disabled = true;
  cfgSaveBtn.textContent = '保存中...';
  cfgStatus.textContent = '';

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: apiKey,
        base_url: baseUrl || undefined,
        model: model || undefined,
        max_tokens: maxTokens,
        connect_timeout: connectTimeout,
        read_timeout: readTimeout
      })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      cfgStatus.textContent = '✓ 配置已保存';
      cfgStatus.style.color = '#00ff88';
      // 重新检查配置状态，切换到聊天界面
      setTimeout(() => checkAiConfig(), 800);
    } else {
      cfgStatus.textContent = '保存失败: ' + (data.message || '未知错误');
      cfgStatus.style.color = '#ff6b6b';
    }
  } catch (err) {
    cfgStatus.textContent = '保存失败: ' + err.message;
    cfgStatus.style.color = '#ff6b6b';
  } finally {
    cfgSaveBtn.disabled = false;
    cfgSaveBtn.textContent = '保存配置';
  }
}

// 测试 API Key 连接
async function testAiConfig() {
  const cfgTestBtn = document.getElementById('cfg-test-btn');
  const cfgStatus = document.getElementById('cfg-status');
  if (!cfgTestBtn || !cfgStatus) return;

  const apiKey = document.getElementById('cfg-api-key').value.trim();
  const baseUrl = document.getElementById('cfg-base-url').value.trim();
  const model = document.getElementById('cfg-model').value.trim();

  if (!apiKey) {
    cfgStatus.textContent = '请先输入 API Key';
    cfgStatus.style.color = '#ff6b6b';
    return;
  }

  cfgTestBtn.disabled = true;
  cfgTestBtn.textContent = '测试中...';
  cfgStatus.textContent = '';

  try {
    const res = await fetch('/api/test-apikey', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: apiKey,
        base_url: baseUrl || undefined,
        model: model || undefined
      })
    });
    const data = await res.json();
    if (data.status === 'ok') {
      cfgStatus.textContent = data.message || '✓ 连接正常';
      cfgStatus.style.color = '#00ff88';
    } else {
      cfgStatus.textContent = data.message || '测试失败';
      cfgStatus.style.color = '#ff6b6b';
    }
  } catch (err) {
    cfgStatus.textContent = '测试失败: ' + err.message;
    cfgStatus.style.color = '#ff6b6b';
  } finally {
    cfgTestBtn.disabled = false;
    cfgTestBtn.textContent = '测试连接';
  }
}

// 加载历史对话列表
async function loadConversationList() {
  try {
    const res = await fetch('/api/conversations');
    const data = await res.json();
    // 保留第一个"当前对话"选项
    while (conversationSelect.options.length > 1) {
      conversationSelect.remove(1);
    }
    if (data.conversations) {
      for (const conv of data.conversations) {
        const opt = document.createElement('option');
        opt.value = conv.session_id;
        const dateStr = conv.date || '';
        const preview = conv.preview ? conv.preview.replace(/[\n\r]/g, ' ').substring(0, 30) : '';
        opt.textContent = dateStr ? `${dateStr} ${preview}` : (preview || conv.session_id);
        conversationSelect.appendChild(opt);
      }
    }
  } catch (err) {
    console.error('加载对话列表失败:', err);
  }
}

// 加载指定对话的消息
async function loadConversationMessages(sessionId) {
  try {
    const res = await fetch('/api/conversations/' + sessionId);
    const data = await res.json();
    if (data.messages) {
      // 清空消息区
      agentMessages.innerHTML = '';
      for (const msg of data.messages) {
        const type = msg.type;
        const content = msg.content || '';
        if (type === 'user') {
          addMessage(content, 'user');
        } else if (type === 'assistant') {
          const div = addMessage('', 'ai');
          // 显示纯文本内容（不含 thinking/answer 标记）
          const cleaned = content
            .replace(new RegExp(THINKING_MARKER, 'g'), '')
            .replace(new RegExp(ANSWER_MARKER, 'g'), '')
            .replace(/<commands>[\s\S]*?<\/commands>/g, '')
            .trim();
          div.textContent = cleaned || '(空回复)';
        } else if (type === 'system') {
          const div = addMessage('[系统] ' + content, 'ai');
          div.style.opacity = '0.6';
        }
        // 忽略 llm_request, llm_response, command, observe, plan 等内部类型
      }
    }
  } catch (err) {
    console.error('加载对话消息失败:', err);
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
    let sessionParsed = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });

      // 解析首块中的 session_id 标记
      if (!sessionParsed && chunk.startsWith('__TC_SESSION__:')) {
        const nlIdx = chunk.indexOf('\n');
        if (nlIdx !== -1) {
          currentSessionId = chunk.substring('__TC_SESSION__:'.length, nlIdx).trim();
          sessionParsed = true;
          // 选择框切到当前会话（如果已在列表中）
          const opt = conversationSelect.querySelector(`option[value="${currentSessionId}"]`);
          if (opt) opt.selected = true;
        }
        continue; // 跳过标记行
      }

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
    // 发送完成后刷新对话列表
    loadConversationList();
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
