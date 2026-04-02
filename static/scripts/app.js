/**
 * 主应用模块
 * 整合所有其他模块，处理用户交互
 */
import { generateId, distance, isPointOnWire } from './utils.js';
import { createElement } from './elements.js';
import { calculateCircuit } from './circuit.js';
import { render } from './renderer.js';

// 全局变量
let canvas, ctx;
let elements = [];
let wires = [];
let selectedElement = null;
let selectedWire = null;
let selectedElements = []; // 多选状态下的选中元件数组
let isDragging = false;
let dragOffset = { x: 0, y: 0 };
let isDrawingWire = false;
let wireStart = null;
let gridEnabled = true;
let history = [];
let historyIndex = -1;
let currentTool = 'select'; // select, input-toggle, delete
let isPlacingElement = false;
let currentElementToPlace = null;
let isMiddleClickCopy = false; // 中键复制后连续放置模式
let lastMiddleClickElement = null; // 最后中键复制的元件（用于连续放置）
let mousePos = { x: 0, y: 0 };
let isPanning = false;
let panOffset = { x: 0, y: 0 };
let canvasOffset = { x: 0, y: 0 };
let zoom = 1; // 缩放级别
let camera = { x: 0, y: 0 }; // 相机位置
let signalAnimation = null;
let isSignalAnimating = false;

const SIGNAL_ANIMATION_SETTINGS = {
    nodeEmitDelay: 60,
    nodeLightDelay: 80,
    wireBaseDelay: 60,
    wireSpeed: 1.2
};

// 框选相关变量
let isSelecting = false; // 是否正在进行框选
let selectionStart = { x: 0, y: 0 }; // 框选起始位置
let selectionEnd = { x: 0, y: 0 }; // 框选结束位置

// 复制粘贴相关变量
let clipboardElements = []; // 剪贴板中的元件
let clipboardWires = []; // 剪贴板中的导线
let isPasting = false; // 是否正在粘贴模式
let pasteOffset = { x: 0, y: 0 }; // 粘贴偏移量

// 集体拖动相关变量
let isGroupDragging = false; // 是否正在集体拖动
let groupDragStart = { x: 0, y: 0 }; // 集体拖动起始位置
let groupDragOffsets = []; // 每个元件的拖动偏移量

let lastSaveTime = 0; // 上次保存到服务器的时间戳

// 函数保存相关
let savedFunctions = []; // 保存的函数列表
let isPlacingFunction = false; // 是否正在放置函数元件
let currentFunctionToPlace = null; // 当前要放置的函数
let isNameModalOpen = false; // 命名弹窗是否打开
let shouldCreateNewElement = true; // 是否应该创建新元件（用于防止点击工具栏时创建多个元件）

/**
 * 初始化应用
 */
async function init() {
    canvas = document.getElementById('canvas');
    ctx = canvas.getContext('2d');
    resizeCanvas();
    
    // 从本地存储加载电路状态          
    loadFromLocalStorage();
    
    // 从服务器加载电路状态
    await loadFromServer();
    
    // 初始化历史记录
    saveState();
    
    // 事件监听
    window.addEventListener('mousemove', handleMouseMove); // 改为 window 监听，以支持鼠标在任何位置（包括覆盖层）
    window.addEventListener('mouseup', handleMouseUp);
    
    // 只添加一个mousedown事件监听器到canvas
    canvas.addEventListener('mousedown', (e) => {
        // 阻止中键默认的滚动行为
        if (e.button === 1) {
            e.preventDefault();
        }
        handleMouseDown(e);
    });
    
    canvas.addEventListener('auxclick', handleMouseDown); // 支持中键点击
    // 阻止右键菜单
    canvas.addEventListener('contextmenu', (e) => {
        e.preventDefault();
    });
    // 添加滚轮缩放功能
    canvas.addEventListener('wheel', handleWheel);
    window.addEventListener('resize', resizeCanvas);
    
    // 定期从服务器同步状态 (为了AI指令系统的实时性)
    setInterval(async () => {
        // 如果正在操作中，或者刚保存完（防止覆盖最新的本地改动），不从服务器加载
        const now = Date.now();
        if (!isDragging && !isDrawingWire && !isPlacingElement && !isPanning && !isSignalAnimating && (now - lastSaveTime > 3000)) {
            await loadFromServer();
            await loadFunctionsFromServer(); // 动态加载函数列表，以响应 AI 的封装操作
        }
    }, 2000);

    // 辅助函数：设置工具状态
    function setTool(toolName, buttonId, statusText) {
        // 取消当前正在放置的元件
        if (isPlacingElement) {
            isPlacingElement = false;
            currentElementToPlace = null;
        }
        
        currentTool = toolName;
        document.getElementById('status-bar').textContent = statusText;
        // 重置所有按钮状态
        document.querySelectorAll('.toolbar button').forEach(btn => btn.classList.remove('active'));
        document.getElementById(buttonId).classList.add('active');
    }
    
    // 辅助函数：添加元件
    function addElementButtonHandler(type) {
        return function(e) {
            console.log('addElementButtonHandler 被调用，type=', type, 'isPlacingElement=', isPlacingElement);

            // 立即取消当前的放置/粘贴状态
            isPlacingElement = false;
            isPasting = false;
            currentElementToPlace = null;
            isMiddleClickCopy = false; // 重置中键复制连续模式
            lastMiddleClickElement = null; // 重置最后复制的元件
            currentTool = 'place-' + type;

            // 创建元件并进入跟随模式
            addElement(type);

            // 保持对应的工具栏按钮高亮
            document.querySelectorAll('.toolbar button').forEach(btn => btn.classList.remove('active'));
            switch(type) {
                case 'AND':
                    document.getElementById('btn-and').classList.add('active');
                    break;
                case 'OR':
                    document.getElementById('btn-or').classList.add('active');
                    break;
                case 'NOT':
                    document.getElementById('btn-not').classList.add('active');
                    break;
                case 'INPUT':
                    document.getElementById('btn-input').classList.add('active');
                    break;
                case 'OUTPUT':
                    document.getElementById('btn-output').classList.add('active');
                    break;
            }
            document.getElementById('status-bar').textContent = `点击画布放置 ${type} 元件`;
        };
    }
    
    // 工具栏按钮事件
    // 元件添加按钮
    document.getElementById('btn-and').addEventListener('click', addElementButtonHandler('AND'));
    document.getElementById('btn-or').addEventListener('click', addElementButtonHandler('OR'));
    document.getElementById('btn-not').addEventListener('click', addElementButtonHandler('NOT'));
    document.getElementById('btn-input').addEventListener('click', addElementButtonHandler('INPUT'));
    document.getElementById('btn-output').addEventListener('click', addElementButtonHandler('OUTPUT'));
    
    // 工具按钮
    document.getElementById('btn-select').addEventListener('click', () => setTool('select', 'btn-select', '选择工具已激活'));
    document.getElementById('btn-input-toggle').addEventListener('click', () => setTool('input-toggle', 'btn-input-toggle', '输入切换工具已激活'));
    document.getElementById('btn-delete').addEventListener('click', () => setTool('delete', 'btn-delete', '删除工具已激活'));
    
    // 其他按钮
    document.getElementById('btn-grid').addEventListener('click', toggleGrid);
    document.getElementById('btn-undo').addEventListener('click', undo);
    document.getElementById('btn-redo').addEventListener('click', redo);
    document.getElementById('btn-clear').addEventListener('click', clearCircuit);
    
    // 初始化函数相关功能
    initFunctionPanel();
    
    // 添加键盘事件监听器
    window.addEventListener('keydown', handleKeyDown);
    
    // 处理键盘按下事件
    function handleKeyDown(e) {
        // 如果命名弹窗打开，只允许 Esc 关闭弹窗
        if (isNameModalOpen) {
            if (e.key === 'Escape') {
                document.getElementById('name-modal').classList.remove('show');
                document.getElementById('function-name-input').value = '';
                isNameModalOpen = false;
            }
            return; // 屏蔽其他所有快捷键
        }
        
        // Ctrl+S 保存选中为函数
        if (e.ctrlKey && e.key.toLowerCase() === 's') {
            e.preventDefault();
            if (selectedElements.length > 0) {
                document.getElementById('name-modal').classList.add('show');
                document.getElementById('function-name-input').value = '';
                document.getElementById('function-name-input').focus();
                isNameModalOpen = true;
            } else {
                document.getElementById('status-bar').textContent = '请先选中包含输入输出的模块';
            }
            return;
        }
        
        // Ctrl+D 删除选中的元件
        if (e.ctrlKey && e.key.toLowerCase() === 'd') {
            e.preventDefault();
            deleteSelected();
            return;
        }
        
        // Ctrl+C 复制选中的元件
        if (e.ctrlKey && e.key.toLowerCase() === 'c') {
            e.preventDefault();
            copySelected();
            return;
        }
        
        // Ctrl+V 粘贴元件
        if (e.ctrlKey && e.key.toLowerCase() === 'v') {
            e.preventDefault();
            startPaste();
            return;
        }

        // Ctrl+A 全选
        if (e.ctrlKey && e.key.toLowerCase() === 'a') {
            e.preventDefault();
            if (elements.length > 0) {
                selectedElements = [...elements];
                document.getElementById('status-bar').textContent = `已选中 ${selectedElements.length} 个元件`;
            } else {
                document.getElementById('status-bar').textContent = '没有元件可选择';
            }
            return;
        }

        // ESC 取消所有放置状态
        if (e.key === 'Escape') {
            // 取消粘贴模式
            if (isPasting) {
                isPasting = false;
                document.getElementById('status-bar').textContent = '已取消粘贴';
            }

            // 取消普通放置状态
            if (isPlacingElement) {
                isPlacingElement = false;
                currentElementToPlace = null;
                isMiddleClickCopy = false; // 清除中键复制连续模式
                lastMiddleClickElement = null; // 清除最后复制的元件
                currentTool = 'select';
                document.querySelectorAll('.toolbar button').forEach(btn => btn.classList.remove('active'));
                document.getElementById('btn-select').classList.add('active');
                document.getElementById('status-bar').textContent = '已取消放置';
            }

            // 取消函数放置状态
            if (isPlacingFunction) {
                isPlacingFunction = false;
                currentFunctionToPlace = null;
                restoreFunctionPanelEvents();
                document.getElementById('status-bar').textContent = '已取消放置函数';
            }

            return;
        }
        
        // 检查是否按下了数字键
        switch(e.key) {
            case '1':
                document.getElementById('btn-select').click();
                break;
            case '2':
                document.getElementById('btn-input-toggle').click();
                break;
            case '3':
                document.getElementById('btn-and').click();
                break;
            case '4':
                document.getElementById('btn-or').click();
                break;
            case '5':
                document.getElementById('btn-not').click();
                break;
            case '6':
                document.getElementById('btn-input').click();
                break;
            case '7':
                document.getElementById('btn-output').click();
                break;
            case '8':
                document.getElementById('btn-delete').click();
                break;
            case '9':
                document.getElementById('btn-clear').click();
                break;
            case '0':
                document.getElementById('btn-grid').click();
                break;
            case 'z':
                if (e.ctrlKey) {
                    undo();
                }
                break;
            case 'y':
                if (e.ctrlKey) {
                    redo();
                }
                break;
        }
    }
    
    // 保存初始状态
    saveState();
    
    // 开始渲染循环
    render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
}

/**
 * 调整画布大小
 */
function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
}

/**
 * 添加元件
 * @param {string} type - 元件类型
 */
function addElement(type) {
    // 计算鼠标在世界坐标系中的位置
    const rect = canvas.getBoundingClientRect();
    const mouseX = mousePos.x;
    const mouseY = mousePos.y;
    const worldX = (mouseX - canvas.width / 2) / zoom + camera.x;
    const worldY = (mouseY - canvas.height / 2) / zoom + camera.y;
    
    // 创建临时元素
    const element = createElement(type, worldX, worldY);
    if (element) {
        // 设置元素位置为鼠标位置（世界坐标）
        element.x = worldX - element.width / 2;
        element.y = worldY - element.height / 2;
        currentElementToPlace = element;
        isPlacingElement = true;
        document.getElementById('status-bar').textContent = '请点击鼠标左键放置元件';
    }
}

/**
 * 为中键连续复制创建新元件
 * @param {object} sourceElement - 源元件
 * @param {number} x - x坐标
 * @param {number} y - y坐标
 * @returns {object|null} 新的元件
 */
function createElementForMiddleClickCopy(sourceElement, x, y) {
    let newElement;
    if (sourceElement.type === 'FUNCTION') {
        newElement = createElement('FUNCTION', x, y, {
            name: sourceElement.name,
            functionElements: JSON.parse(JSON.stringify(sourceElement.functionData.elements)),
            functionWires: JSON.parse(JSON.stringify(sourceElement.functionData.wires)),
            inputElements: JSON.parse(JSON.stringify(sourceElement.functionData.inputElementIds)),
            outputElements: JSON.parse(JSON.stringify(sourceElement.functionData.outputElementIds))
        });
        
        if (newElement) {
            // 使用与源元件相同的大小
            newElement.width = sourceElement.width;
            newElement.height = sourceElement.height;
            
            // 调整端口位置
            for (let i = 0; i < newElement.inputs.length; i++) {
                if (sourceElement.inputs[i]) {
                    newElement.inputs[i].x = sourceElement.inputs[i].x;
                    newElement.inputs[i].y = sourceElement.inputs[i].y;
                }
            }
            for (let i = 0; i < newElement.outputs.length; i++) {
                if (sourceElement.outputs[i]) {
                    newElement.outputs[i].x = sourceElement.outputs[i].x;
                    newElement.outputs[i].y = sourceElement.outputs[i].y;
                }
            }
        }
    } else {
        newElement = createElement(sourceElement.type, x, y);
        
        if (newElement) {
            if (sourceElement.type === 'INPUT') {
                newElement.state = sourceElement.state;
            }
            
            // 使用与源元件相同的大小
            newElement.width = sourceElement.width;
            newElement.height = sourceElement.height;
            
            // 调整端口位置
            for (let i = 0; i < newElement.inputs.length; i++) {
                if (sourceElement.inputs[i]) {
                    newElement.inputs[i].x = sourceElement.inputs[i].x;
                    newElement.inputs[i].y = sourceElement.inputs[i].y;
                }
            }
            for (let i = 0; i < newElement.outputs.length; i++) {
                if (sourceElement.outputs[i]) {
                    newElement.outputs[i].x = sourceElement.outputs[i].x;
                    newElement.outputs[i].y = sourceElement.outputs[i].y;
                }
            }
        }
    }
    
    if (newElement) {
        newElement.x = x - newElement.width / 2;
        newElement.y = y - newElement.height / 2;
        return newElement;
    }
    return null;
}

/**
 * 复制元素 - 使用跟随鼠标模式
 * @param {object} sourceElement - 要复制的源元素
 */
function duplicateElement(sourceElement) {
    // 计算鼠标在世界坐标系中的位置
    const rect = canvas.getBoundingClientRect();
    const mouseX = mousePos.x;
    const mouseY = mousePos.y;
    const worldX = (mouseX - canvas.width / 2) / zoom + camera.x;
    const worldY = (mouseY - canvas.height / 2) / zoom + camera.y;
    
    // 创建临时元素，位置在鼠标附近
    let newElement;
    if (sourceElement.type === 'FUNCTION') {
        // 函数元件需要特殊处理
        newElement = createElement('FUNCTION', worldX, worldY, {
            name: sourceElement.name,
            functionElements: JSON.parse(JSON.stringify(sourceElement.functionData.elements)),
            functionWires: JSON.parse(JSON.stringify(sourceElement.functionData.wires)),
            inputElements: JSON.parse(JSON.stringify(sourceElement.functionData.inputElementIds)),
            outputElements: JSON.parse(JSON.stringify(sourceElement.functionData.outputElementIds))
        });
        
        if (newElement) {
            // 使用与源元件相同的大小
            newElement.width = sourceElement.width;
            newElement.height = sourceElement.height;
            
            // 调整端口位置
            for (let i = 0; i < newElement.inputs.length; i++) {
                if (sourceElement.inputs[i]) {
                    newElement.inputs[i].x = sourceElement.inputs[i].x;
                    newElement.inputs[i].y = sourceElement.inputs[i].y;
                }
            }
            for (let i = 0; i < newElement.outputs.length; i++) {
                if (sourceElement.outputs[i]) {
                    newElement.outputs[i].x = sourceElement.outputs[i].x;
                    newElement.outputs[i].y = sourceElement.outputs[i].y;
                }
            }
        }
    } else {
        newElement = createElement(sourceElement.type, worldX, worldY);
        
        if (newElement) {
            // 复制状态（对于INPUT元件）
            if (sourceElement.type === 'INPUT') {
                newElement.state = sourceElement.state;
            }
            
            // 使用与源元件相同的大小
            newElement.width = sourceElement.width;
            newElement.height = sourceElement.height;
            
            // 调整端口位置
            for (let i = 0; i < newElement.inputs.length; i++) {
                if (sourceElement.inputs[i]) {
                    newElement.inputs[i].x = sourceElement.inputs[i].x;
                    newElement.inputs[i].y = sourceElement.inputs[i].y;
                }
            }
            for (let i = 0; i < newElement.outputs.length; i++) {
                if (sourceElement.outputs[i]) {
                    newElement.outputs[i].x = sourceElement.outputs[i].x;
                    newElement.outputs[i].y = sourceElement.outputs[i].y;
                }
            }
        }
    }
    
    if (newElement) {
        // 设置元素位置为鼠标位置（居中）
        newElement.x = worldX - newElement.width / 2;
        newElement.y = worldY - newElement.height / 2;
        
        // 设置为正在放置状态，跟随鼠标
        currentElementToPlace = newElement;
        isPlacingElement = true;
        isMiddleClickCopy = true; // 标记为中键复制连续放置模式
        lastMiddleClickElement = sourceElement; // 记住复制的源元件
        document.getElementById('status-bar').textContent = '中键复制成功，中键放置，ESC取消';
        
        return newElement;
    }
    return null;
}

function takeCircuitStateSnapshot() {
    const elementStates = new Map();
    for (const el of elements) {
        elementStates.set(el.id, !!el.state);
    }
    const wireStates = new Map();
    for (const wire of wires) {
        wireStates.set(wire.id, !!wire.state);
    }
    return { elementStates, wireStates };
}

function applyCircuitStateSnapshot(snapshot) {
    if (!snapshot) return;
    for (const el of elements) {
        const v = snapshot.elementStates.get(el.id);
        if (v !== undefined) el.state = v;
    }
    for (const wire of wires) {
        const v = snapshot.wireStates.get(wire.id);
        if (v !== undefined) wire.state = v;
    }
}

function getWireFlowInfo(wire) {
    if (!wire?.start?.elementId || !wire?.end?.elementId) return null;

    const startIsOutput = !wire.start.isInput;
    const endIsOutput = !wire.end.isInput;

    if (startIsOutput && wire.end.isInput) {
        return {
            wireId: wire.id,
            fromElementId: wire.start.elementId,
            toElementId: wire.end.elementId,
            fromX: wire.start.x,
            fromY: wire.start.y,
            toX: wire.end.x,
            toY: wire.end.y
        };
    }

    if (endIsOutput && wire.start.isInput) {
        return {
            wireId: wire.id,
            fromElementId: wire.end.elementId,
            toElementId: wire.start.elementId,
            fromX: wire.end.x,
            fromY: wire.end.y,
            toX: wire.start.x,
            toY: wire.start.y
        };
    }

    if (startIsOutput && endIsOutput) {
        return {
            wireId: wire.id,
            fromElementId: wire.start.elementId,
            toElementId: wire.end.elementId,
            fromX: wire.start.x,
            fromY: wire.start.y,
            toX: wire.end.x,
            toY: wire.end.y
        };
    }

    return {
        wireId: wire.id,
        fromElementId: wire.start.elementId,
        toElementId: wire.end.elementId,
        fromX: wire.start.x,
        fromY: wire.start.y,
        toX: wire.end.x,
        toY: wire.end.y
    };
}

function buildSignalAnimation(sourceElementId, beforeSnapshot, targetSnapshot) {
    const startTime = performance.now();

    const elementById = new Map();
    for (const el of elements) {
        elementById.set(el.id, el);
    }
    const wireById = new Map();
    for (const wire of wires) {
        wireById.set(wire.id, wire);
    }

    const outgoing = new Map();
    const directedWires = [];
    const changedWireStates = new Map();
    const changedElementStates = new Map();

    for (const el of elements) {
        const beforeValue = beforeSnapshot.elementStates.get(el.id) || false;
        const afterValue = targetSnapshot.elementStates.get(el.id) || false;
        changedElementStates.set(el.id, beforeValue !== afterValue);
    }
    for (const wire of wires) {
        const info = getWireFlowInfo(wire);
        if (!info) continue;
        const beforeValue = beforeSnapshot.wireStates.get(info.wireId) || false;
        const afterValue = targetSnapshot.wireStates.get(info.wireId) || false;
        const isChanged = beforeValue !== afterValue;
        changedWireStates.set(info.wireId, isChanged);
        if (!isChanged) continue;
        directedWires.push(info);
        if (!outgoing.has(info.fromElementId)) outgoing.set(info.fromElementId, []);
        outgoing.get(info.fromElementId).push(info);
    }


    const switchTimes = new Map();
    for (const el of elements) {
        switchTimes.set(el.id, Infinity);
    }
    switchTimes.set(sourceElementId, 0);

    const visited = new Set();
    while (true) {
        let currentId = null;
        let currentTime = Infinity;
        for (const [id, t] of switchTimes) {
            if (visited.has(id)) continue;
            if (t < currentTime) {
                currentTime = t;
                currentId = id;
            }
        }
        if (currentId === null || currentTime === Infinity) break;
        visited.add(currentId);

        const outs = outgoing.get(currentId) || [];
        for (const info of outs) {
            const length = distance(info.fromX, info.fromY, info.toX, info.toY);
            const travel = SIGNAL_ANIMATION_SETTINGS.wireBaseDelay + length / SIGNAL_ANIMATION_SETTINGS.wireSpeed;
            const nextTime = currentTime + SIGNAL_ANIMATION_SETTINGS.nodeEmitDelay + travel + SIGNAL_ANIMATION_SETTINGS.nodeLightDelay;
            if (nextTime < (switchTimes.get(info.toElementId) || Infinity)) {
                switchTimes.set(info.toElementId, nextTime);
            }
        }
    }

    const elementEvents = [];
    for (const [id, t] of switchTimes) {
        if (t === Infinity) continue;
        if (id === sourceElementId || changedElementStates.get(id)) {
            elementEvents.push({ id, time: t });
        }
    }
    elementEvents.sort((a, b) => a.time - b.time);

    const wireTravels = [];
    const wireEvents = [];
    let endTime = 0;

    for (const info of directedWires) {
        const fromTime = switchTimes.get(info.fromElementId);
        if (fromTime === undefined || fromTime === Infinity) continue;
        const startOffset = fromTime + SIGNAL_ANIMATION_SETTINGS.nodeEmitDelay;
        const length = distance(info.fromX, info.fromY, info.toX, info.toY);
        const duration = SIGNAL_ANIMATION_SETTINGS.wireBaseDelay + length / SIGNAL_ANIMATION_SETTINGS.wireSpeed;
        const endOffset = startOffset + duration;

        const targetWireState = targetSnapshot.wireStates.get(info.wireId) || false;
        const color = targetWireState ? '#00ff00' : '#ff0000';

        wireTravels.push({
            wireId: info.wireId,
            fromX: info.fromX,
            fromY: info.fromY,
            toX: info.toX,
            toY: info.toY,
            startOffset,
            duration,
            color
        });

        wireEvents.push({ id: info.wireId, time: endOffset });
        endTime = Math.max(endTime, endOffset);
    }

    for (const ev of elementEvents) {
        endTime = Math.max(endTime, ev.time);
    }

    wireEvents.sort((a, b) => a.time - b.time);

    return {
        active: true,
        startTime,
        endTime: endTime + 200,
        elementEvents,
        wireEvents,
        elementIndex: 0,
        wireIndex: 0,
        elementById,
        wireById,
        targetElementStates: targetSnapshot.elementStates,
        targetWireStates: targetSnapshot.wireStates,
        changedWireStates,
        changedElementStates,
        wireTravels
    };
}

function completeSignalAnimation() {
    if (!signalAnimation) return;
    for (const [id, state] of signalAnimation.targetElementStates) {
        const el = signalAnimation.elementById.get(id);
        if (el) el.state = state;
    }
    for (const [id, state] of signalAnimation.targetWireStates) {
        const wire = signalAnimation.wireById.get(id);
        if (wire) wire.state = state;
    }
    signalAnimation.active = false;
    signalAnimation = null;
    isSignalAnimating = false;
}

function updateSignalAnimation(now) {
    if (!signalAnimation || !signalAnimation.active) return;
    const t = now - signalAnimation.startTime;

    while (signalAnimation.elementIndex < signalAnimation.elementEvents.length &&
        t >= signalAnimation.elementEvents[signalAnimation.elementIndex].time) {
        const id = signalAnimation.elementEvents[signalAnimation.elementIndex].id;
        const el = signalAnimation.elementById.get(id);
        if (el) el.state = signalAnimation.targetElementStates.get(id) || false;
        signalAnimation.elementIndex++;
    }

    while (signalAnimation.wireIndex < signalAnimation.wireEvents.length &&
        t >= signalAnimation.wireEvents[signalAnimation.wireIndex].time) {
        const id = signalAnimation.wireEvents[signalAnimation.wireIndex].id;
        const wire = signalAnimation.wireById.get(id);
        if (wire) wire.state = signalAnimation.targetWireStates.get(id) || false;
        signalAnimation.wireIndex++;
    }

    if (t >= signalAnimation.endTime) {
        completeSignalAnimation();
    }
}

/**
 * 处理鼠标按下事件
 * @param {MouseEvent} e - 鼠标事件
 */
function handleMouseDown(e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    // 计算鼠标在世界坐标系中的位置
    const worldX = (mouseX - canvas.width / 2) / zoom + camera.x;
    const worldY = (mouseY - canvas.height / 2) / zoom + camera.y;

    if (isSignalAnimating) {
        completeSignalAnimation();
    }
    
    // 右键点击 - 始终启动拖动屏幕（无论点击哪里）
    // 只有 mousedown 事件会触发 panning，auxclick 不会
    if (e.button === 2 && e.type === 'mousedown') {
        e.preventDefault();
        isPanning = true;
        isSelecting = false; // 确保不会同时触发框选
        panOffset = { x: mouseX, y: mouseY };
        document.getElementById('status-bar').textContent = '正在拖动屏幕...';
        console.log('右键按下, 启动拖动屏幕, isPanning=true');
        return;
    }
    
    // 如果是 auxclick 事件且是右键，不执行后续逻辑（防止 panning 被重新触发）
    if (e.type === 'auxclick' && e.button === 2) {
        return;
    }
    
    // 如果不是左键且不是 auxclick（用于中键点击），则不处理后续逻辑
    if (e.button !== 0 && e.type !== 'auxclick') {
        return;
    }

    console.log('handleMouseDown:', { isPlacingElement, isPlacingFunction, isPasting, button: e.button, target: e.target?.id });

    // 如果点击的是工具栏按钮，不处理
    const target = e.target || e.srcElement;
    if (target && target.closest && target.closest('.toolbar')) {
        console.log('点击的是工具栏按钮，跳过');
        return;
    }

    // 如果处于任何放置状态，阻止事件冒泡
    if (isPlacingElement || isPlacingFunction || isPasting) {
        e.stopPropagation();
    }

    // 重置 shouldCreateNewElement
    shouldCreateNewElement = true;

    // 如果正在放置函数元件
    if (isPlacingFunction && currentFunctionToPlace && e.button === 0) {
        // 检查点击是否在 canvas 上（不在工具栏等其他UI元素上）
        const target = e.target || e.srcElement;
        if (target && target.id === 'canvas') {
            // 放置函数元件
            elements.push(currentFunctionToPlace);
            saveState();
            isPlacingFunction = false;
            currentFunctionToPlace = null;
            // 恢复函数面板的点击事件
            restoreFunctionPanelEvents();
            document.getElementById('status-bar').textContent = '函数元件已放置';
            elements = calculateCircuit(elements, wires);
            render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
        } else {
            // 点击的不是 canvas，取消放置状态，但不创建新元件
            shouldCreateNewElement = false;
            isPlacingFunction = false;
            currentFunctionToPlace = null;
        }
        return;
    }

    // 如果正在粘贴模式，左键点击执行粘贴
    if (isPasting && e.button === 0) {
        // 检查点击是否在 canvas 上
        const target = e.target || e.srcElement;
        if (target && target.id === 'canvas') {
            console.log('执行粘贴');
            executePaste();
        } else {
            // 点击不在 canvas 上，取消粘贴状态，但不创建新元件
            shouldCreateNewElement = false;
            isPasting = false;
        }
        return;
    }

    // 如果正在放置元素（点击工具栏按钮后），检查点击目标
    if (isPlacingElement && e.button === 0) {
        const target = e.target || e.srcElement;
        if (target && target.id === 'canvas') {
            // 点击的是 canvas，执行放置
            const elementToPlace = currentElementToPlace;
            elements.push(elementToPlace);
            saveState();
            isPlacingElement = false;
            currentElementToPlace = null;
            currentTool = 'select';
            document.querySelectorAll('.toolbar button').forEach(btn => btn.classList.remove('active'));
            document.getElementById('btn-select').classList.add('active');
            elements = calculateCircuit(elements, wires);
            document.getElementById('status-bar').textContent = `${elementToPlace.type} 元件已放置`;
            render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
        } else {
            // 点击的不是 canvas（可能是工具栏按钮），取消当前放置状态，但不创建新元件
            shouldCreateNewElement = false;
            isPlacingElement = false;
            currentElementToPlace = null;
        }
        return;
    }

    // 如果正在放置元素（仅用于中键复制后的跟随鼠标，不拦截左键点击）
    // 注意：这里不 return，让左键点击可以继续执行其他逻辑

    // 检查是否点击了端口
    for (const element of elements) {
        for (const input of element.inputs) {
            const portX = element.x + input.x;
            const portY = element.y + input.y;
            if (distance(worldX, worldY, portX, portY) < 10) {
                isDrawingWire = true;
                wireStart = { elementId: element.id, portId: input.id, x: portX, y: portY, isInput: true };
                document.getElementById('status-bar').textContent = '正在绘制导线...';
                return;
            }
        }
        for (const output of element.outputs) {
            const portX = element.x + output.x;
            const portY = element.y + output.y;
            if (distance(worldX, worldY, portX, portY) < 10) {
                isDrawingWire = true;
                wireStart = { elementId: element.id, portId: output.id, x: portX, y: portY, isInput: false };
                document.getElementById('status-bar').textContent = '正在绘制导线...';
                return;
            }
        }
    }
    
    // 检查是否点击了元件
    for (const element of elements) {
        if (worldX >= element.x && worldX <= element.x + element.width &&
            worldY >= element.y && worldY <= element.y + element.height) {
            
            console.log('点击元件: button=', e.button, 'type=', e.type);
            
            // 中键点击复制元素（auxclick事件，button === 1 表示中键）
            if (e.type === 'auxclick' && e.button === 1) {
                e.preventDefault(); // 阻止默认的中键行为
                e.stopPropagation(); // 阻止事件冒泡
                console.log('中键点击元素:', element.type);
                duplicateElement(element);
                return;
            }
            
            if (currentTool === 'input-toggle' && element.type === 'INPUT') {
                const beforeSnapshot = takeCircuitStateSnapshot();
                element.state = !element.state;
                saveState();

                elements = calculateCircuit(elements, wires);
                const targetSnapshot = takeCircuitStateSnapshot();

                applyCircuitStateSnapshot(beforeSnapshot);
                element.state = targetSnapshot.elementStates.get(element.id) || false;

                signalAnimation = buildSignalAnimation(element.id, beforeSnapshot, targetSnapshot);
                isSignalAnimating = true;

                document.getElementById('status-bar').textContent = `输入状态已切换为: ${element.state ? '1' : '0'}`;
                render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
                return;
            } else if (currentTool === 'delete') {
                // 删除工具：删除元件
                // 删除连接到该元件的所有导线
                wires = wires.filter(wire => 
                    wire.start.elementId !== element.id && 
                    wire.end.elementId !== element.id
                );
                // 删除元件
                elements = elements.filter(el => el.id !== element.id);
                selectedElement = null;
                saveState();
                elements = calculateCircuit(elements, wires);
                document.getElementById('status-bar').textContent = '元件已删除';
                render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
                return;
            } else {
                // 选择工具：选择并准备拖拽
                // 检查是否点击了已选中的多选元件之一
                if (selectedElements.length > 1 && selectedElements.includes(element)) {
                    // 开始集体拖动
                    isGroupDragging = true;
                    groupDragStart = { x: worldX, y: worldY };
                    groupDragOffsets = selectedElements.map(el => ({
                        element: el,
                        offsetX: worldX - el.x,
                        offsetY: worldY - el.y
                    }));
                    document.getElementById('status-bar').textContent = `集体拖动 ${selectedElements.length} 个元件`;
                } else {
                    // 单选模式
                    selectedElement = element;
                    selectedWire = null;
                    selectedElements = []; // 清除多选状态
                    dragOffset.x = worldX - element.x;
                    dragOffset.y = worldY - element.y;
                    isDragging = true;
                    document.getElementById('status-bar').textContent = `选中元件: ${element.type}`;
                }
                render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, [], null, false, zoom, camera);
                return;
            }
        }
    }
    
    // 检查是否点击了导线
    for (const wire of wires) {
        if (isPointOnWire(worldX, worldY, wire)) {
            if (currentTool === 'delete') {
                // 删除工具：删除导线
                wires = wires.filter(w => w.id !== wire.id);
                selectedWire = null;
                saveState();
                elements = calculateCircuit(elements, wires);
                document.getElementById('status-bar').textContent = '导线已删除';
                render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
                return;
            } else {
                // 选择工具：选择导线
                selectedWire = wire;
                selectedElement = null;
                document.getElementById('status-bar').textContent = '选中导线';
                return;
            }
        }
    }

    // 中键点击空白处且处于连续放置模式：直接放置副本
    if (e.type === 'auxclick' && e.button === 1 && isMiddleClickCopy && currentElementToPlace) {
        e.preventDefault();
        e.stopPropagation();
        
        // 更新位置到当前鼠标位置
        currentElementToPlace.x = worldX - currentElementToPlace.width / 2;
        currentElementToPlace.y = worldY - currentElementToPlace.height / 2;
        
        // 放置副本
        elements.push(currentElementToPlace);
        saveState();
        
        // 创建新的副本用于下一次放置
        const sourceElement = lastMiddleClickElement;
        if (sourceElement) {
            // 使用lastMiddleClickElement作为源来创建新副本
            const newElement = createElementForMiddleClickCopy(sourceElement, worldX, worldY);
            if (newElement) {
                currentElementToPlace = newElement;
                // 立即更新位置到鼠标位置
                currentElementToPlace.x = worldX - currentElementToPlace.width / 2;
                currentElementToPlace.y = worldY - currentElementToPlace.height / 2;
            }
        }
        
        document.getElementById('status-bar').textContent = '放置成功，继续中键放置，ESC取消';
        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
        return;
    }

    // 点击空白处
    console.log('点击空白处: currentTool=', currentTool, 'button=', e.button);
    if (currentTool === 'select' && e.button === 0) { // 左键 - 框选
        // 开始框选
        isSelecting = true;
        isPanning = false; // 确保不会同时触发
        selectionStart = { x: worldX, y: worldY };
        selectionEnd = { x: worldX, y: worldY };
        // 清除之前的单选状态
        selectedElement = null;
        selectedWire = null;
        selectedElements = [];
        document.getElementById('status-bar').textContent = '框选模式：拖动鼠标选择多个元件';
        console.log('开始框选, isSelecting=', isSelecting);
    } else {
        // 重置所有状态
        selectedElement = null;
        selectedWire = null;
        selectedElements = [];
        isPanning = false;
        isSelecting = false;
        document.getElementById('status-bar').textContent = '就绪';
    }
}

/**
 * 处理鼠标移动事件
 * @param {MouseEvent} e - 鼠标事件
 */
function handleMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    mousePos = { x: mouseX, y: mouseY };
    
    // 计算鼠标在世界坐标系中的位置
    const worldX = (mouseX - canvas.width / 2) / zoom + camera.x;
    const worldY = (mouseY - canvas.height / 2) / zoom + camera.y;
    
    // 如果正在放置函数元件
    if (isPlacingFunction && currentFunctionToPlace) {
        // 更新函数元件位置
        currentFunctionToPlace.x = worldX - currentFunctionToPlace.width / 2;
        currentFunctionToPlace.y = worldY - currentFunctionToPlace.height / 2;
        // 先渲染背景
        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
        // 绘制临时函数元件
        drawTemporaryElement(ctx, currentFunctionToPlace);
        return;
    }
    
    // 如果正在放置普通元件
    if (isPlacingElement && currentElementToPlace) {
        // 更新元件位置
        currentElementToPlace.x = worldX - currentElementToPlace.width / 2;
        currentElementToPlace.y = worldY - currentElementToPlace.height / 2;
        // 先渲染背景
        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
        // 绘制临时元件
        drawTemporaryElement(ctx, currentElementToPlace);
        return;
    }
    
    // 处理拖动屏幕 (Panning)
    if (isPanning) {
        // 计算偏移量（转换为世界坐标）
        const deltaX = (mouseX - panOffset.x) / zoom;
        const deltaY = (mouseY - panOffset.y) / zoom;
        
        // 更新相机位置
        camera.x -= deltaX;
        camera.y -= deltaY;
        
        // 更新网格背景位置，实现无限延伸效果
        const grid = document.getElementById('grid');
        if (grid) {
            // 获取当前的背景位置
            const currentBgPos = grid.style.backgroundPosition || '0px 0px';
            const matches = currentBgPos.match(/(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px/);
            let bgX = 0, bgY = 0;
            if (matches) {
                bgX = parseFloat(matches[1]);
                bgY = parseFloat(matches[2]);
            }
            
            // 更新背景位置
            grid.style.backgroundPosition = `${bgX + (mouseX - panOffset.x)}px ${bgY + (mouseY - panOffset.y)}px`;
        }
        
        // 更新偏移量
        panOffset = { x: mouseX, y: mouseY };
        
        // 重新渲染并返回
        render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, [], null, false, zoom, camera);
        
        // 如果正在放置元件，也要绘制预览
        if (isPlacingElement && currentElementToPlace) {
            drawTemporaryElement(ctx, currentElementToPlace);
        }
        
        return;
    }
    
    // 更新框选区域
    if (isSelecting) {
        selectionEnd = { x: worldX, y: worldY };
        updateSelection();
        render(ctx, elements, wires, selectedElement, selectedWire, getSelectionRect(), selectedElements, [], null, false, zoom, camera);
        return;
    }
    
    // 处理集体拖动
    if (isGroupDragging && selectedElements.length > 0) {
        for (const item of groupDragOffsets) {
            const el = item.element;
            el.x = worldX - item.offsetX;
            el.y = worldY - item.offsetY;
            
            // 更新连接到该元件的导线
            for (const wire of wires) {
                if (wire.start.elementId === el.id) {
                    const port = wire.start.isInput ? 
                        el.inputs.find(p => p.id === wire.start.portId) :
                        el.outputs.find(p => p.id === wire.start.portId);
                    if (port) {
                        wire.start.x = el.x + port.x;
                        wire.start.y = el.y + port.y;
                    }
                }
                if (wire.end.elementId === el.id) {
                    const port = wire.end.isInput ? 
                        el.inputs.find(p => p.id === wire.end.portId) :
                        el.outputs.find(p => p.id === wire.end.portId);
                    if (port) {
                        wire.end.x = el.x + port.x;
                        wire.end.y = el.y + port.y;
                    }
                }
            }
        }
        render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, [], null, false, zoom, camera);
        return;
    }
    
    // 更新粘贴预览位置
    if (isPasting) {
        pasteOffset = { x: worldX, y: worldY };
        render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, clipboardElements, pasteOffset, isPasting, zoom, camera);
        return;
    }
    
    if (isDragging && selectedElement) {
        selectedElement.x = worldX - dragOffset.x;
        selectedElement.y = worldY - dragOffset.y;
        // 更新连接到该元件的导线
        for (const wire of wires) {
            if (wire.start.elementId === selectedElement.id) {
                const element = selectedElement;
                const port = wire.start.isInput ? 
                    element.inputs.find(p => p.id === wire.start.portId) :
                    element.outputs.find(p => p.id === wire.start.portId);
                if (port) {
                    wire.start.x = element.x + port.x;
                    wire.start.y = element.y + port.y;
                }
            }
            if (wire.end.elementId === selectedElement.id) {
                const element = selectedElement;
                const port = wire.end.isInput ? 
                    element.inputs.find(p => p.id === wire.end.portId) :
                    element.outputs.find(p => p.id === wire.end.portId);
                if (port) {
                    wire.end.x = element.x + port.x;
                    wire.end.y = element.y + port.y;
                }
            }
        }
        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
    }
    
    if (isDrawingWire) {
        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);

        // 端口吸附
        let endX = worldX;
        let endY = worldY;
        const snapDistance = 15 / zoom; // 吸附距离（转换为世界坐标）

        // 查找最近的端口
        for (const element of elements) {
            if (element.id === wireStart.elementId) continue;

            for (const input of element.inputs) {
                const portX = element.x + input.x;
                const portY = element.y + input.y;
                if (distance(worldX, worldY, portX, portY) < snapDistance) {
                    endX = portX;
                    endY = portY;
                    break;
                }
            }
            if (endX !== worldX || endY !== worldY) break;

            for (const output of element.outputs) {
                const portX = element.x + output.x;
                const portY = element.y + output.y;
                if (distance(worldX, worldY, portX, portY) < snapDistance) {
                    endX = portX;
                    endY = portY;
                    break;
                }
            }
            if (endX !== worldX || endY !== worldY) break;
        }

        // 应用相机变换进行绘制
        ctx.save();
        ctx.translate(canvas.width / 2, canvas.height / 2);
        ctx.scale(zoom, zoom);
        ctx.translate(-camera.x, -camera.y);

        // 绘制临时导线
        ctx.beginPath();
        ctx.moveTo(wireStart.x, wireStart.y);
        ctx.lineTo(endX, endY);
        ctx.strokeStyle = '#00ffff';
        ctx.lineWidth = 2 / zoom;
        ctx.stroke();

        // 绘制吸附指示
        if (endX !== worldX || endY !== worldY) {
            ctx.fillStyle = '#00ffff';
            ctx.beginPath();
            ctx.arc(endX, endY, 5 / zoom, 0, Math.PI * 2);
            ctx.fill();
        }

        // 恢复上下文
        ctx.restore();
    }
    
    if (isPlacingElement && currentElementToPlace) {
        // 更新当前要放置的元素位置
        currentElementToPlace.x = worldX - currentElementToPlace.width / 2;
        currentElementToPlace.y = worldY - currentElementToPlace.height / 2;
        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
        // 绘制临时元素
        drawTemporaryElement(ctx, currentElementToPlace);
    }
}

/**
 * 绘制临时元素
 * @param {CanvasRenderingContext2D} ctx - 画布上下文
 * @param {object} element - 要绘制的临时元素
 */
function drawTemporaryElement(ctx, element) {
    // 绘制临时元件，使用与render函数相同的相机变换
    ctx.save();
    ctx.translate(ctx.canvas.width / 2, ctx.canvas.height / 2);
    ctx.scale(zoom, zoom);
    ctx.translate(-camera.x, -camera.y);
    
    // 绘制元件背景
    ctx.fillStyle = 'rgba(0, 255, 255, 0.2)';
    ctx.strokeStyle = 'rgba(0, 255, 255, 0.7)';
    ctx.lineWidth = 1 / zoom;
    ctx.beginPath();
    ctx.rect(element.x, element.y, element.width, element.height);
    ctx.fill();
    ctx.stroke();
    
    // 绘制元件符号
    ctx.fillStyle = '#00ffff';
    ctx.font = (14 / zoom) + 'px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    
    switch (element.type) {
        case 'AND':
            // 绘制与门符号
            ctx.strokeStyle = '#00ffff';
            ctx.lineWidth = 2 / zoom;
            // 简化与门：使用更小的尺寸，居中绘制
            const andCenterX = element.x + element.width / 2;
            const andCenterY = element.y + element.height / 2;
            const andSize = Math.min(element.width, element.height) * 0.7;
            
            ctx.beginPath();
            ctx.moveTo(andCenterX - andSize/2, andCenterY - andSize/3);
            ctx.lineTo(andCenterX - andSize/2, andCenterY + andSize/3);
            ctx.arc(andCenterX + andSize/4, andCenterY, andSize/3, Math.PI * 1.5, Math.PI * 0.5);
            ctx.closePath();
            ctx.stroke();
            break;
        case 'OR':
            // 绘制或门符号
            ctx.strokeStyle = '#00ffff';
            ctx.lineWidth = 2 / zoom;
            // 简化或门：使用更小的尺寸，居中绘制
            const orCenterX = element.x + element.width / 2;
            const orCenterY = element.y + element.height / 2;
            const orSize = Math.min(element.width, element.height) * 0.7;
            
            ctx.beginPath();
            ctx.moveTo(orCenterX - orSize/2, orCenterY - orSize/3);
            ctx.lineTo(orCenterX - orSize/2, orCenterY + orSize/3);
            ctx.arc(orCenterX + orSize/4, orCenterY, orSize/3, Math.PI * 1.5, Math.PI * 0.5);
            ctx.closePath();
            ctx.stroke();
            // 绘制或门的弯曲输入
            ctx.beginPath();
            ctx.arc(orCenterX - orSize/2, orCenterY, orSize/6, Math.PI * 0.5, Math.PI * 1.5);
            ctx.stroke();
            break;
        case 'NOT':
            // 绘制非门符号
            ctx.strokeStyle = '#00ffff';
            ctx.lineWidth = 2 / zoom;
            // 简化非门：使用更小的尺寸，居中绘制
            const notCenterX = element.x + element.width / 2;
            const notCenterY = element.y + element.height / 2;
            const notSize = Math.min(element.width, element.height) * 0.7;
            
            // 绘制主体矩形
            ctx.beginPath();
            ctx.rect(notCenterX - notSize/3, notCenterY - notSize/4, notSize/2, notSize/2);
            ctx.stroke();
            // 绘制输出线和圆圈
            ctx.beginPath();
            ctx.moveTo(notCenterX + notSize/6, notCenterY);
            ctx.lineTo(notCenterX + notSize/3, notCenterY);
            ctx.stroke();
            // 绘制非门的圆圈
            ctx.beginPath();
            ctx.arc(notCenterX + notSize/3 + notSize/12, notCenterY, notSize/12, 0, Math.PI * 2);
            ctx.fillStyle = '#00ffff';
            ctx.fill();
            break;
        case 'INPUT':
            // 绘制输入块
            ctx.fillText(element.state ? '1' : '0', element.x + element.width / 2, element.y + element.height / 2);
            break;
        case 'OUTPUT':
            // 绘制输出块
            ctx.fillText(element.state ? '1' : '0', element.x + element.width / 2, element.y + element.height / 2);
            break;
        case 'FUNCTION':
            // 绘制函数块边框
            ctx.strokeStyle = '#00ffff';
            ctx.lineWidth = 2 / zoom;
            ctx.setLineDash([5 / zoom, 5 / zoom]);
            ctx.strokeRect(element.x, element.y, element.width, element.height);
            ctx.setLineDash([]);
            // 绘制函数名称
            ctx.fillStyle = '#00ffff';
            ctx.font = (12 / zoom) + 'px Arial';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(element.name || 'Func', element.x + element.width / 2, element.y + element.height / 2);
            break;
    }
    
    // 绘制端口
    for (const input of element.inputs) {
        const portX = element.x + input.x;
        const portY = element.y + input.y;
        ctx.fillStyle = '#00ffff';
        ctx.beginPath();
        ctx.arc(portX, portY, 5 / zoom, 0, Math.PI * 2);
        ctx.fill();
    }
    
    for (const output of element.outputs) {
        const portX = element.x + output.x;
        const portY = element.y + output.y;
        ctx.fillStyle = '#00ffff';
        ctx.beginPath();
        ctx.arc(portX, portY, 5 / zoom, 0, Math.PI * 2);
        ctx.fill();
    }
    
    // 恢复上下文
    ctx.restore();
}

/**
 * 获取框选矩形
 * @returns {object|null} 框选矩形或null
 */
function getSelectionRect() {
    if (!isSelecting) return null;
    return {
        x: Math.min(selectionStart.x, selectionEnd.x),
        y: Math.min(selectionStart.y, selectionEnd.y),
        width: Math.abs(selectionEnd.x - selectionStart.x),
        height: Math.abs(selectionEnd.y - selectionStart.y)
    };
}

/**
 * 更新选中的元件列表
 */
function updateSelection() {
    const rect = getSelectionRect();
    if (!rect || rect.width < 5 || rect.height < 5) return; // 太小的框选忽略
    
    selectedElements = [];
    for (const element of elements) {
        // 检查元件是否在框选区域内
        const elementCenterX = element.x + element.width / 2;
        const elementCenterY = element.y + element.height / 2;
        
        if (elementCenterX >= rect.x && 
            elementCenterX <= rect.x + rect.width &&
            elementCenterY >= rect.y && 
            elementCenterY <= rect.y + rect.height) {
            selectedElements.push(element);
        }
    }
}

/**
 * 删除选中的元件和导线
 */
function deleteSelected() {
    if (selectedElements.length === 0) return;
    
    const elementIds = selectedElements.map(el => el.id);
    
    // 删除连接到选中元件的所有导线
    wires = wires.filter(wire => 
        !elementIds.includes(wire.start.elementId) && 
        !elementIds.includes(wire.end.elementId)
    );
    
    // 删除选中的元件
    elements = elements.filter(el => !elementIds.includes(el.id));
    
    // 清除选中状态
    selectedElements = [];
    selectedElement = null;
    selectedWire = null;
    
    saveState();
    elements = calculateCircuit(elements, wires);
    document.getElementById('status-bar').textContent = `已删除 ${elementIds.length} 个元件`;
    render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, [], null, false, zoom, camera);
}

/**
 * 复制选中的元件到剪贴板
 */
function copySelected() {
    if (selectedElements.length === 0) {
        document.getElementById('status-bar').textContent = '没有选中的元件可复制';
        return;
    }
    
    // 深拷贝选中的元件
    clipboardElements = selectedElements.map(el => {
        const newEl = {
            ...el,
            _originalId: el.id, // 保存原始ID用于导线映射
            id: generateId(), // 生成新ID
            inputs: el.inputs.map(input => ({ ...input })),
            outputs: el.outputs.map(output => ({ ...output }))
        };
        
        // 如果是函数元件，需要深拷贝 functionData
        if (el.type === 'FUNCTION' && el.functionData) {
            newEl.functionData = JSON.parse(JSON.stringify(el.functionData));
        }
        
        return newEl;
    });
    
    // 复制选中元件之间的导线
    const selectedIds = selectedElements.map(el => el.id);
    clipboardWires = wires.filter(wire => 
        selectedIds.includes(wire.start.elementId) && 
        selectedIds.includes(wire.end.elementId)
    ).map(wire => ({
        ...wire,
        id: generateId(),
        start: { ...wire.start },
        end: { ...wire.end }
    }));
    
    // 计算选中元件的中心点
    const centerX = selectedElements.reduce((sum, el) => sum + el.x + el.width / 2, 0) / selectedElements.length;
    const centerY = selectedElements.reduce((sum, el) => sum + el.y + el.height / 2, 0) / selectedElements.length;
    
    // 保存相对偏移量
    clipboardElements.forEach(el => {
        el._copyOffsetX = el.x - centerX;
        el._copyOffsetY = el.y - centerY;
    });
    
    document.getElementById('status-bar').textContent = `已复制 ${clipboardElements.length} 个元件和 ${clipboardWires.length} 条导线，按 Ctrl+V 粘贴`;
}

/**
 * 开始粘贴模式
 */
function startPaste() {
    if (clipboardElements.length === 0) {
        document.getElementById('status-bar').textContent = '剪贴板为空，先复制一些元件';
        return;
    }

    // 计算鼠标在世界坐标系中的位置
    const rect = canvas.getBoundingClientRect();
    const mouseX = mousePos.x;
    const mouseY = mousePos.y;
    const worldX = (mouseX - canvas.width / 2) / zoom + camera.x;
    const worldY = (mouseY - canvas.height / 2) / zoom + camera.y;

    isPasting = true;
    pasteOffset = { x: worldX, y: worldY };
    console.log('startPaste: isPasting =', isPasting, 'pasteOffset =', pasteOffset);
    document.getElementById('status-bar').textContent = '粘贴模式：点击鼠标左键放置，按 Esc 取消';
    render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, clipboardElements, pasteOffset, isPasting, zoom, camera);
}

/**
 * 执行粘贴
 */
function executePaste() {
    if (!isPasting || clipboardElements.length === 0) return;
    
    const newElements = [];
    const idMapping = {}; // 旧ID到新ID的映射
    
    // 创建新元件
    for (const template of clipboardElements) {
        let newElement;
        if (template.type === 'FUNCTION' && template.functionData) {
            // 函数元件需要特殊处理，传递 functionData
            newElement = createElement('FUNCTION', 0, 0, {
                name: template.name,
                functionElements: template.functionData.elements,
                functionWires: template.functionData.wires,
                inputElements: template.functionData.inputElementIds,
                outputElements: template.functionData.outputElementIds
            });
        } else {
            newElement = createElement(template.type, 0, 0);
        }
        
        if (newElement) {
            // 复制属性，不应用缩放，保持与新元件放置相同的行为
            newElement.x = pasteOffset.x + template._copyOffsetX;
            newElement.y = pasteOffset.y + template._copyOffsetY;
            newElement.state = template.state;
            
            // 使用与模板相同的大小，不进行缩放
            newElement.width = template.width;
            newElement.height = template.height;
            
            // 使用与模板相同的端口位置
            for (let i = 0; i < newElement.inputs.length; i++) {
                if (template.inputs[i]) {
                    newElement.inputs[i].x = template.inputs[i].x;
                    newElement.inputs[i].y = template.inputs[i].y;
                }
            }
            for (let i = 0; i < newElement.outputs.length; i++) {
                if (template.outputs[i]) {
                    newElement.outputs[i].x = template.outputs[i].x;
                    newElement.outputs[i].y = template.outputs[i].y;
                }
            }
            
            // 保存ID映射（用于后续连接导线）
            idMapping[template._originalId] = newElement.id;
            
            elements.push(newElement);
            newElements.push(newElement);
        }
    }
    
    // 创建导线连接
    for (const wireTemplate of clipboardWires) {
        const newStartElementId = idMapping[wireTemplate.start.elementId];
        const newEndElementId = idMapping[wireTemplate.end.elementId];
        
        if (newStartElementId && newEndElementId) {
            // 找到对应的元件
            const startElement = newElements.find(el => el.id === newStartElementId);
            const endElement = newElements.find(el => el.id === newEndElementId);
            
            if (startElement && endElement) {
                // 通过索引找到对应的端口（createElement创建的端口ID不同，但索引相同）
                const startElementTemplate = clipboardElements.find(el => el._originalId === wireTemplate.start.elementId);
                const endElementTemplate = clipboardElements.find(el => el._originalId === wireTemplate.end.elementId);
                
                if (startElementTemplate && endElementTemplate) {
                    // 找到端口索引
                    const startPortIndex = wireTemplate.start.isInput ?
                        startElementTemplate.inputs.findIndex(p => p.id === wireTemplate.start.portId) :
                        startElementTemplate.outputs.findIndex(p => p.id === wireTemplate.start.portId);
                    const endPortIndex = wireTemplate.end.isInput ?
                        endElementTemplate.inputs.findIndex(p => p.id === wireTemplate.end.portId) :
                        endElementTemplate.outputs.findIndex(p => p.id === wireTemplate.end.portId);
                    
                    // 通过索引获取新元件的端口
                    const startPort = wireTemplate.start.isInput ?
                        startElement.inputs[startPortIndex] :
                        startElement.outputs[startPortIndex];
                    const endPort = wireTemplate.end.isInput ?
                        endElement.inputs[endPortIndex] :
                        endElement.outputs[endPortIndex];
                    
                    if (startPort && endPort) {
                        const newWire = {
                            id: generateId(),
                            start: {
                                elementId: newStartElementId,
                                portId: startPort.id,
                                x: startElement.x + startPort.x,
                                y: startElement.y + startPort.y,
                                isInput: wireTemplate.start.isInput
                            },
                            end: {
                                elementId: newEndElementId,
                                portId: endPort.id,
                                x: endElement.x + endPort.x,
                                y: endElement.y + endPort.y,
                                isInput: wireTemplate.end.isInput
                            },
                            state: wireTemplate.state
                        };
                        wires.push(newWire);
                    }
                }
            }
        }
    }
    
    // 清除选中状态，选中新粘贴的元件
    selectedElements = newElements;
    selectedElement = null;
    selectedWire = null;
    
    isPasting = false;
    saveState();
    elements = calculateCircuit(elements, wires);
    document.getElementById('status-bar').textContent = `已粘贴 ${newElements.length} 个元件和 ${clipboardWires.length} 条导线`;
    render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, [], null, false, zoom, camera);
}

/**
 * 取消粘贴模式
 */
function cancelPaste() {
    if (isPasting) {
        isPasting = false;
        document.getElementById('status-bar').textContent = '已取消粘贴';
        render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, clipboardElements, pasteOffset, isPasting, zoom, camera);
    }
}

/**
 * 恢复函数面板的点击事件
 */
function restoreFunctionPanelEvents() {
    const functionPanel = document.getElementById('function-panel');
    const functionList = document.getElementById('function-list');
    const functionItems = document.querySelectorAll('.function-item');
    functionPanel.style.pointerEvents = 'none';
    functionList.style.pointerEvents = 'auto';
    functionItems.forEach(item => item.style.pointerEvents = 'auto');
}

/**
 * 处理鼠标释放事件
 * @param {MouseEvent} e - 鼠标事件
 */
function handleMouseUp(e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    // 计算鼠标在世界坐标系中的位置
    const worldX = (mouseX - canvas.width / 2) / zoom + camera.x;
    const worldY = (mouseY - canvas.height / 2) / zoom + camera.y;
    
    console.log('鼠标释放: button=', e.button, 'isPanning=', isPanning);
    
    // 处理右键释放 - 结束拖动屏幕
    if (e.button === 2) {
        console.log('检测到右键释放, isPanning=', isPanning);
        if (isPanning) {
            isPanning = false;
            saveState();
            document.getElementById('status-bar').textContent = '屏幕拖动完成';
            render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, [], null, false, zoom, camera);
        }
        return;
    }
    
    // 处理左键释放 - 处理框选结束、单选拖动结束、集体拖动结束
    if (e.button === 0) {
        // 处理框选结束
        if (isSelecting) {
            isSelecting = false;
            const rect = getSelectionRect();
            if (rect && rect.width >= 5 && rect.height >= 5) {
                updateSelection();
                if (selectedElements.length > 0) {
                    document.getElementById('status-bar').textContent = `已选中 ${selectedElements.length} 个元件，按 Ctrl+D 删除，Ctrl+C 复制`;
                } else {
                    document.getElementById('status-bar').textContent = '就绪';
                }
            }
            render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, [], null, false, zoom, camera);
        }
        
        // 处理单选拖动结束
        if (isDragging) {
            saveState();
            document.getElementById('status-bar').textContent = '元素移动完成';
            isDragging = false;
        }
        
        // 处理集体拖动结束
        if (isGroupDragging) {
            isGroupDragging = false;
            saveState();
            document.getElementById('status-bar').textContent = `集体移动完成，共 ${selectedElements.length} 个元件`;
        }
        
        // 处理放置元素
        if (isPlacingElement && currentElementToPlace) {
            // 检查点击的是否是工具栏按钮，如果是则不放置
            const target = e.target || e.srcElement;
            if (target && target.closest && target.closest('.toolbar')) {
                // 点击的是工具栏按钮，不执行放置，让工具栏按钮的处理函数来处理
            } else {
                // 放置元素
                elements.push(currentElementToPlace);
                saveState();
                
                if (isMiddleClickCopy) {
                    // 中键复制连续放置模式：保持状态，用户可以继续放置
                    document.getElementById('status-bar').textContent = '放置成功，继续中键放置，ESC取消';
                    render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
                } else {
                    // 普通工具栏放置模式：放置后退出放置状态
                    isPlacingElement = false;
                    currentElementToPlace = null;
                    document.getElementById('status-bar').textContent = '元件放置成功';
                    
                    // 切换回选择工具状态
                    currentTool = 'select';
                    document.querySelectorAll('.toolbar button').forEach(btn => btn.classList.remove('active'));
                    document.getElementById('btn-select').classList.add('active');
                    
                    render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
                }
            }
            return;
        }
        
        // 处理绘制导线
        if (isDrawingWire) {
            // 检查是否点击了目标端口
            for (const element of elements) {
                if (element.id === wireStart.elementId) continue;
                
                for (const input of element.inputs) {
                    const portX = element.x + input.x;
                    const portY = element.y + input.y;
                    if (distance(worldX, worldY, portX, portY) < 10 / zoom) {
                        // 确保不会将输入端口连接到输入端口
                        if (!wireStart.isInput) {
                            const wire = {
                                id: generateId(),
                                start: wireStart,
                                end: { elementId: element.id, portId: input.id, x: portX, y: portY, isInput: true }
                            };
                            wires.push(wire);
                            saveState();
                            elements = calculateCircuit(elements, wires);
                        }
                        isDrawingWire = false;
                        wireStart = null;
                        document.getElementById('status-bar').textContent = '导线连接成功';
                        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
                        return;
                    }
                }
                
                for (const output of element.outputs) {
                    const portX = element.x + output.x;
                    const portY = element.y + output.y;
                    if (distance(worldX, worldY, portX, portY) < 10 / zoom) {
                        // 确保不会将输出端口连接到输出端口
                        if (wireStart.isInput) {
                            const wire = {
                                id: generateId(),
                                start: wireStart,
                                end: { elementId: element.id, portId: output.id, x: portX, y: portY, isInput: false }
                            };
                            wires.push(wire);
                            saveState();
                            elements = calculateCircuit(elements, wires);
                        }
                        isDrawingWire = false;
                        wireStart = null;
                        document.getElementById('status-bar').textContent = '导线连接成功';
                        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
                        return;
                    }
                }
            }
            
            // 取消绘制导线
            isDrawingWire = false;
            wireStart = null;
            document.getElementById('status-bar').textContent = '取消绘制导线';
            render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
            return;
        }
        
        return;
    }
}

/**
 * 切换网格显示
 */
function toggleGrid() {
    gridEnabled = !gridEnabled;
    const grid = document.getElementById('grid');
    grid.style.display = gridEnabled ? 'block' : 'none';
    document.getElementById('status-bar').textContent = gridEnabled ? '网格已启用' : '网格已禁用';
}

/**
 * 撤销操作
 */
function undo() {
    if (historyIndex > 0) {
        historyIndex--;
        const state = history[historyIndex];
        elements = JSON.parse(state.elements);
        wires = JSON.parse(state.wires);
        selectedElement = null;
        selectedWire = null;
        document.getElementById('status-bar').textContent = '已撤销';
        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
    }
}

/**
 * 重做操作
 */
function redo() {
    if (historyIndex < history.length - 1) {
        historyIndex++;
        const state = history[historyIndex];
        elements = JSON.parse(state.elements);
        wires = JSON.parse(state.wires);
        selectedElement = null;
        selectedWire = null;
        document.getElementById('status-bar').textContent = '已重做';
        
        // 清除当前索引之后的历史记录（分支历史）
        history = history.slice(0, historyIndex + 1);
        
        // 保存到本地存储和服务器
        saveToLocalStorage();
        saveToServer();
        
        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
    }
}

/**
 * 保存状态到历史记录
 */
function saveState() {
    // 移除当前索引之后的历史记录
    history = history.slice(0, historyIndex + 1);
    // 添加新状态
    history.push({
        elements: JSON.stringify(elements),
        wires: JSON.stringify(wires)
    });
    // 取消历史记录长度限制
    historyIndex++;
    
    // 保存到本地存储
    saveToLocalStorage();
    
    // 保存到服务器
    saveToServer();
}

/**
 * 清空电路
 */
function clearCircuit() {
    // 清空元件和导线
    elements = [];
    wires = [];
    selectedElement = null;
    selectedWire = null;
    
    // 重置网格背景位置
    const grid = document.getElementById('grid');
    if (grid) {
        grid.style.backgroundPosition = '0px 0px';
    }
    
    // 保存状态
    saveState();
    
    // 更新状态提示
    document.getElementById('status-bar').textContent = '电路已清空';
    
    // 重新渲染
    render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
}

/**
 * 保存到本地存储
 */
function saveToLocalStorage() {
    try {
        localStorage.setItem('circuitElements', JSON.stringify(elements));
        localStorage.setItem('circuitWires', JSON.stringify(wires));
        
        // 保存网格大小
        let gridSize = 20;
        const grid = document.getElementById('grid');
        if (grid) {
            const currentBgSize = getComputedStyle(grid).backgroundSize;
            const sizeMatch = currentBgSize.match(/(\d+)px\s+(\d+)px/);
            if (sizeMatch) {
                gridSize = parseInt(sizeMatch[1]);
            }
        }
        localStorage.setItem('circuitGridSize', gridSize);
        
        // 保存网格位置（屏幕位置）
        let gridPosition = { x: 0, y: 0 };
        if (grid) {
            const currentBgPos = grid.style.backgroundPosition || '0px 0px';
            const posMatch = currentBgPos.match(/(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px/);
            if (posMatch) {
                gridPosition = {
                    x: parseFloat(posMatch[1]),
                    y: parseFloat(posMatch[2])
                };
            }
        }
        localStorage.setItem('circuitGridPosition', JSON.stringify(gridPosition));
    } catch (error) {
        console.error('保存到本地存储失败:', error);
    }
}

/**
 * 保存到服务器
 */
async function saveToServer() {
    lastSaveTime = Date.now(); // 更新保存时间戳
    try {
        // 获取网格大小
        let gridSize = 20;
        const grid = document.getElementById('grid');
        if (grid) {
            const currentBgSize = getComputedStyle(grid).backgroundSize;
            const sizeMatch = currentBgSize.match(/(\d+)px\s+(\d+)px/);
            if (sizeMatch) {
                gridSize = parseInt(sizeMatch[1]);
            }
        }
        
        // 获取网格背景位置（屏幕位置）
        let gridPosition = { x: 0, y: 0 };
        if (grid) {
            const currentBgPos = grid.style.backgroundPosition || '0px 0px';
            const posMatch = currentBgPos.match(/(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px/);
            if (posMatch) {
                gridPosition = {
                    x: parseFloat(posMatch[1]),
                    y: parseFloat(posMatch[2])
                };
            }
        }
        
        const response = await fetch('http://localhost:5000/api/save-circuit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                elements: elements,
                wires: wires,
                gridSize: gridSize,
                gridPosition: gridPosition
            })
        });
        const result = await response.json();
        console.log('保存到服务器:', result);
    } catch (error) {
        console.error('保存到服务器失败:', error);
    }
}

/**
 * 从服务器加载
 */
export async function loadFromServer() {
    try {
        const response = await fetch('http://localhost:5000/api/load-circuit');
        const result = await response.json();

        // 保存当前选中的元件ID
        const selectedElementIds = selectedElements.map(el => el.id);

        if (result.elements) {
            elements = result.elements;
        }
        if (result.wires) {
            wires = result.wires;
        }
        
        // 加载网格大小
        if (result.gridSize) {
            const grid = document.getElementById('grid');
            if (grid) {
                grid.style.backgroundSize = `${result.gridSize}px ${result.gridSize}px`;
            }
        }
        
        // 加载网格位置（屏幕位置）
        if (result.gridPosition) {
            const grid = document.getElementById('grid');
            if (grid) {
                grid.style.backgroundPosition = `${result.gridPosition.x}px ${result.gridPosition.y}px`;
            }
        }
        
        // 重新计算电路状态，确保导线颜色正确
        elements = calculateCircuit(elements, wires);

        // 恢复选中状态
        if (selectedElementIds.length > 0) {
            selectedElements = elements.filter(el => selectedElementIds.includes(el.id));
        }
        
        // 渲染更新
        render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
        
        console.log('从服务器加载:', result);
    } catch (error) {
        console.error('从服务器加载失败:', error);
    }
}

/**
 * 从本地存储加载
 */
function loadFromLocalStorage() {
    try {
        const savedElements = localStorage.getItem('circuitElements');
        const savedWires = localStorage.getItem('circuitWires');
        
        if (savedElements) {
            elements = JSON.parse(savedElements);
        }
        if (savedWires) {
            wires = JSON.parse(savedWires);
        }
        
        // 加载网格大小
        const savedGridSize = localStorage.getItem('circuitGridSize');
        if (savedGridSize) {
            const grid = document.getElementById('grid');
            if (grid) {
                grid.style.backgroundSize = `${parseInt(savedGridSize)}px ${parseInt(savedGridSize)}px`;
            }
        }
        
        // 加载网格位置（屏幕位置）
        const savedGridPosition = localStorage.getItem('circuitGridPosition');
        if (savedGridPosition) {
            const grid = document.getElementById('grid');
            if (grid) {
                const gridPosition = JSON.parse(savedGridPosition);
                grid.style.backgroundPosition = `${gridPosition.x}px ${gridPosition.y}px`;
            }
        }
        
        // 重新计算电路状态，确保导线颜色正确
        elements = calculateCircuit(elements, wires);
    } catch (error) {
        console.error('从本地存储加载失败:', error);
    }
}

/**
 * 处理鼠标滚轮事件，实现缩放功能
 * @param {WheelEvent} e - 鼠标滚轮事件
 */
function handleWheel(e) {
    e.preventDefault();
    
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    // 计算缩放因子
    const scaleFactor = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = zoom * scaleFactor;
    
    // 限制缩放范围
    if (newZoom < 0.1 || newZoom > 10) return;
    
    // 保存当前状态
    saveState();
    
    // 计算鼠标在世界坐标系中的位置
    const worldX = (mouseX - canvas.width / 2) / zoom + camera.x;
    const worldY = (mouseY - canvas.height / 2) / zoom + camera.y;
    
    // 更新缩放级别
    zoom = newZoom;
    
    // 调整相机位置，使鼠标指向的点在缩放后保持不变
    camera.x = worldX - (mouseX - canvas.width / 2) / zoom;
    camera.y = worldY - (mouseY - canvas.height / 2) / zoom;
    
    // 调整网格大小和位置
    const grid = document.getElementById('grid');
    if (grid) {
        // 计算新的网格大小
        const newGridSize = Math.max(5, Math.min(100, 20 * zoom));
        
        // 更新网格大小
        grid.style.backgroundSize = `${newGridSize}px ${newGridSize}px`;
        
        // 更新网格位置，使其与相机同步
        const gridX = -camera.x * zoom % newGridSize;
        const gridY = -camera.y * zoom % newGridSize;
        grid.style.backgroundPosition = `${gridX}px ${gridY}px`;
    }
    
    // 重新渲染
    render(ctx, elements, wires, selectedElement, selectedWire, null, [], [], null, false, zoom, camera);
    
    // 绘制临时元素
    if (isPlacingElement && currentElementToPlace) {
        drawTemporaryElement(ctx, currentElementToPlace);
    }
}

/**
 * 初始化函数面板
 */
async function initFunctionPanel() {
    // 从服务器加载保存的函数
    await loadFunctionsFromServer();
    
    // 绑定命名弹窗事件
    document.getElementById('confirm-save-function').addEventListener('click', async () => {
        const nameInput = document.getElementById('function-name-input');
        const name = nameInput.value.trim();
        if (!name) {
            alert('请输入函数名称');
            nameInput.focus();
            return;
        }
        
        const success = await saveSelectedAsFunction(name);
        if (success) {
            document.getElementById('name-modal').classList.remove('show');
            nameInput.value = '';
            isNameModalOpen = false;
        } else {
            // 保存失败时用 alert 提示
            const statusText = document.getElementById('status-bar').textContent;
            alert(statusText);
            nameInput.focus();
            nameInput.select();
        }
    });
    
    document.getElementById('cancel-save-function').addEventListener('click', () => {
        document.getElementById('name-modal').classList.remove('show');
        document.getElementById('function-name-input').value = '';
        isNameModalOpen = false;
    });
    
    document.getElementById('function-name-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.getElementById('confirm-save-function').click();
        }
    });
}

/**
 * 保存选中的元件为函数
 * @returns {boolean} 是否保存成功
 */
async function saveSelectedAsFunction(name) {
    // 检查名字是否为空
    if (!name || name.trim() === '') {
        document.getElementById('status-bar').textContent = '函数名称不能为空';
        return false;
    }
    
    // 检查名字是否已存在
    const nameExists = savedFunctions.some(func => func.name === name);
    if (nameExists) {
        document.getElementById('status-bar').textContent = `函数 "${name}" 已存在，请使用其他名称`;
        return false;
    }
    
    // 检查选中的元件中是否有输入和输出
    const hasInput = selectedElements.some(el => el.type === 'INPUT');
    const hasOutput = selectedElements.some(el => el.type === 'OUTPUT');
    
    if (!hasInput || !hasOutput) {
        document.getElementById('status-bar').textContent = '选中的模块需要包含至少一个输入和一个输出';
        return false;
    }
    
    // 获取选中元件之间的导线
    const selectedIds = selectedElements.map(el => el.id);
    const selectedWires = wires.filter(wire => 
        selectedIds.includes(wire.start.elementId) && 
        selectedIds.includes(wire.end.elementId)
    );
    
    // 获取输入和输出元件ID列表
    const inputElementIds = selectedElements
        .filter(el => el.type === 'INPUT')
        .map(el => el.id);
    const outputElementIds = selectedElements
        .filter(el => el.type === 'OUTPUT')
        .map(el => el.id);
    
    if (outputElementIds.length === 0) {
        document.getElementById('status-bar').textContent = '需要一个输出元件';
        return false;
    }
    
    // 创建函数数据
    const functionData = {
        id: generateId(),
        name: name,
        elements: JSON.parse(JSON.stringify(selectedElements)),
        wires: JSON.parse(JSON.stringify(selectedWires)),
        inputElementIds: inputElementIds,
        outputElementIds: outputElementIds
    };
    
    // 保存到本地数组
    savedFunctions.push(functionData);
    
    // 保存到服务器
    await saveFunctionToServer(functionData);
    
    // 更新函数面板
    updateFunctionPanel();
    
    document.getElementById('status-bar').textContent = `函数 "${name}" 已保存`;
    return true;
}

/**
 * 更新函数面板显示
 */
function updateFunctionPanel() {
    const listContainer = document.getElementById('function-list');
    listContainer.innerHTML = '';
    
    savedFunctions.forEach((func, index) => {
        const item = document.createElement('div');
        item.className = 'function-item';
        
        // 左侧名称区域（点击放置函数）
        const nameSpan = document.createElement('span');
        nameSpan.textContent = func.name;
        nameSpan.style.cssText = 'flex: 1; cursor: pointer;';
        nameSpan.addEventListener('click', (e) => {
            e.stopPropagation();
            startPlaceFunction(func);
        });
        
        // 右侧删除按钮
        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = '×';
        deleteBtn.className = 'function-delete-btn';
        deleteBtn.style.cssText = 'background: rgba(255,0,0,0.2); border: 1px solid rgba(255,0,0,0.4); color: #ff6666; padding: 2px 8px; border-radius: 4px; cursor: pointer; font-size: 14px; line-height: 1;';
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteFunction(index);
        });
        
        item.appendChild(nameSpan);
        item.appendChild(deleteBtn);
        item.style.cssText = 'display: flex; align-items: center; justify-content: space-between;';
        listContainer.appendChild(item);
    });
}

/**
 * 删除函数
 */
async function deleteFunction(index) {
    if (index >= 0 && index < savedFunctions.length) {
        const funcName = savedFunctions[index].name;
        savedFunctions.splice(index, 1);
        await saveFunctionsToServer();
        updateFunctionPanel();
        document.getElementById('status-bar').textContent = `函数 "${funcName}" 已删除`;
    }
}

/**
 * 保存所有函数到服务器
 */
async function saveFunctionsToServer() {
    try {
        const response = await fetch('http://localhost:5000/api/save-functions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ functions: savedFunctions })
        });
        const result = await response.json();
        console.log('函数列表保存到服务器:', result);
    } catch (error) {
        console.error('保存函数列表到服务器失败:', error);
    }
}

/**
 * 开始放置函数元件
 */
function startPlaceFunction(funcData) {
    console.log('startPlaceFunction called with:', funcData.name);
    
    // 获取画布中心位置（作为默认放置位置）
    const canvasCenterX = canvas.width / 2;
    const canvasCenterY = canvas.height / 2;
    
    // 创建函数元件
    const funcElement = createElement('FUNCTION', canvasCenterX, canvasCenterY, {
        name: funcData.name,
        functionElements: JSON.parse(JSON.stringify(funcData.elements)),
        functionWires: JSON.parse(JSON.stringify(funcData.wires)),
        inputElements: JSON.parse(JSON.stringify(funcData.inputElementIds)),
        outputElements: JSON.parse(JSON.stringify(funcData.outputElementIds))
    });
    console.log('funcElement created:', funcElement);
    
    if (funcElement) {
        currentFunctionToPlace = funcElement;
        isPlacingFunction = true;
        console.log('isPlacingFunction set to true');
        
        // 禁用函数面板的点击事件，让点击可以传到 canvas
        const functionPanel = document.getElementById('function-panel');
        const functionList = document.getElementById('function-list');
        const functionItems = document.querySelectorAll('.function-item');
        functionPanel.style.pointerEvents = 'none';
        functionList.style.pointerEvents = 'none';
        functionItems.forEach(item => item.style.pointerEvents = 'none');
        
        document.getElementById('status-bar').textContent = `请点击放置函数 "${funcData.name}"（ESC取消）`;
    }
}

/**
 * 保存函数到服务器
 */
async function saveFunctionToServer(funcData) {
    try {
        const response = await fetch('http://localhost:5000/api/save-function', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(funcData)
        });
        const result = await response.json();
        console.log('函数保存到服务器:', result);
    } catch (error) {
        console.error('保存函数到服务器失败:', error);
    }
}

/**
 * 从服务器加载函数
 */
async function loadFunctionsFromServer() {
    try {
        const response = await fetch('http://localhost:5000/api/load-functions');
        const result = await response.json();
        if (result.functions) {
            // Only update if functions have changed to prevent UI flicker
            if (JSON.stringify(savedFunctions) !== JSON.stringify(result.functions)) {
                savedFunctions = result.functions;
                updateFunctionPanel();
                console.log('从服务器加载并更新函数:', savedFunctions);
            }
        }
    } catch (error) {
        console.error('从服务器加载函数失败:', error);
    }
}

// 持续渲染循环（帧率刷新）
function startRenderLoop() {
    function loop() {
        if (isSignalAnimating) {
            updateSignalAnimation(performance.now());
        }

        // 根据当前状态确定框选矩形
        let selectionRect = null;
        if (isSelecting) {
            selectionRect = {
                x: Math.min(selectionStart.x, selectionEnd.x),
                y: Math.min(selectionStart.y, selectionEnd.y),
                width: Math.abs(selectionEnd.x - selectionStart.x),
                height: Math.abs(selectionEnd.y - selectionStart.y)
            };
        }
        
        // 根据当前状态确定临时元素（放置中或粘贴中）
        let tempElement = null;
        if (isPlacingElement && currentElementToPlace) {
            tempElement = currentElementToPlace;
        } else if (isPlacingFunction && currentFunctionToPlace) {
            tempElement = currentFunctionToPlace;
        }
        
        // 基础渲染
        render(ctx, elements, wires, selectedElement, selectedWire, selectionRect, selectedElements, [], null, false, zoom, camera, signalAnimation);
        
        // 绘制临时元素（正在放置的元件）
        if (tempElement) {
            drawTemporaryElement(ctx, tempElement);
        }
        
        // 绘制粘贴预览
        if (isPasting && clipboardElements.length > 0 && pasteOffset) {
            // 获取当前缩放比例
            let gridSize = 20;
            const grid = document.getElementById('grid');
            if (grid) {
                const currentBgSize = getComputedStyle(grid).backgroundSize;
                const sizeMatch = currentBgSize.match(/(\d+)px\s+(\d+)px/);
                if (sizeMatch) {
                    gridSize = parseInt(sizeMatch[1]);
                }
            }
            const currentScale = gridSize / 20;
            
            for (const template of clipboardElements) {
                const copyScale = template._scaleFactor || 1;
                const scaleRatio = currentScale / copyScale;
                
                const x = pasteOffset.x + template._copyOffsetX * scaleRatio;
                const y = pasteOffset.y + template._copyOffsetY * scaleRatio;
                const width = template.width * scaleRatio;
                const height = template.height * scaleRatio;
                
                ctx.strokeStyle = 'rgba(0, 255, 255, 0.7)';
                ctx.fillStyle = 'rgba(0, 255, 255, 0.1)';
                ctx.lineWidth = 2;
                ctx.setLineDash([5, 5]);
                
                ctx.beginPath();
                ctx.rect(x, y, width, height);
                ctx.fill();
                ctx.stroke();
                
                ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
                ctx.font = `${14 * scaleRatio}px Arial`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                
                switch (template.type) {
                    case 'AND':
                        ctx.strokeStyle = 'rgba(0, 255, 255, 0.7)';
                        ctx.lineWidth = 2;
                        const andCenterX = x + width / 2;
                        const andCenterY = y + height / 2;
                        const andSize = Math.min(width, height) * 0.7;
                        
                        ctx.beginPath();
                        ctx.moveTo(andCenterX - andSize/2, andCenterY - andSize/3);
                        ctx.lineTo(andCenterX - andSize/2, andCenterY + andSize/3);
                        ctx.arc(andCenterX + andSize/4, andCenterY, andSize/3, Math.PI * 1.5, Math.PI * 0.5);
                        ctx.closePath();
                        ctx.stroke();
                        break;
                    case 'OR':
                        ctx.strokeStyle = 'rgba(0, 255, 255, 0.7)';
                        ctx.lineWidth = 2;
                        const orCenterX = x + width / 2;
                        const orCenterY = y + height / 2;
                        const orSize = Math.min(width, height) * 0.7;
                        
                        ctx.beginPath();
                        ctx.moveTo(orCenterX - orSize/2, orCenterY - orSize/3);
                        ctx.lineTo(orCenterX - orSize/2, orCenterY + orSize/3);
                        ctx.arc(orCenterX + orSize/4, orCenterY, orSize/3, Math.PI * 1.5, Math.PI * 0.5);
                        ctx.closePath();
                        ctx.stroke();
                        ctx.beginPath();
                        ctx.arc(orCenterX - orSize/2, orCenterY, orSize/6, Math.PI * 0.5, Math.PI * 1.5);
                        ctx.stroke();
                        break;
                    case 'NOT':
                        ctx.strokeStyle = 'rgba(0, 255, 255, 0.7)';
                        ctx.lineWidth = 2;
                        const notCenterX = x + width / 2;
                        const notCenterY = y + height / 2;
                        const notSize = Math.min(width, height) * 0.7;
                        
                        ctx.beginPath();
                        ctx.rect(notCenterX - notSize/3, notCenterY - notSize/4, notSize/2, notSize/2);
                        ctx.stroke();
                        ctx.beginPath();
                        ctx.moveTo(notCenterX + notSize/6, notCenterY);
                        ctx.lineTo(notCenterX + notSize/3, notCenterY);
                        ctx.stroke();
                        ctx.beginPath();
                        ctx.arc(notCenterX + notSize/3 + notSize/12, notCenterY, notSize/12, 0, Math.PI * 2);
                        ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
                        ctx.fill();
                        break;
                    case 'INPUT':
                        ctx.fillText(template.state ? '1' : '0', x + width / 2, y + height / 2);
                        break;
                    case 'OUTPUT':
                        ctx.fillText(template.state ? '1' : '0', x + width / 2, y + height / 2);
                        break;
                    case 'FUNCTION':
                        ctx.font = `${12 * scaleRatio}px Arial`;
                        ctx.fillText(template.name || 'Func', x + width / 2, y + height / 2);
                        break;
                }
                
                for (const input of template.inputs) {
                    const portX = x + input.x * scaleRatio;
                    const portY = y + input.y * scaleRatio;
                    ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
                    ctx.beginPath();
                    ctx.arc(portX, portY, 5 * scaleRatio, 0, Math.PI * 2);
                    ctx.fill();
                }
                
                for (const output of template.outputs) {
                    const portX = x + output.x * scaleRatio;
                    const portY = y + output.y * scaleRatio;
                    ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
                    ctx.beginPath();
                    ctx.arc(portX, portY, 5 * scaleRatio, 0, Math.PI * 2);
                    ctx.fill();
                }
            }
            ctx.setLineDash([]);
        }
        
        // 绘制正在绘制的导线
        if (isDrawingWire && wireStart) {
            const canvasWidth = ctx.canvas.width;
            const canvasHeight = ctx.canvas.height;
            const endX = (mousePos.x - canvasWidth / 2) / zoom + camera.x;
            const endY = (mousePos.y - canvasHeight / 2) / zoom + camera.y;

            ctx.save();
            ctx.translate(canvasWidth / 2, canvasHeight / 2);
            ctx.scale(zoom, zoom);
            ctx.translate(-camera.x, -camera.y);

            ctx.beginPath();
            ctx.moveTo(wireStart.x, wireStart.y);
            ctx.lineTo(endX, endY);
            ctx.strokeStyle = '#00ffff';
            ctx.lineWidth = 2 / zoom;
            ctx.stroke();

            ctx.restore();
        }
        
        requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
}

// 初始化应用
(async function() {
    await init();
    startRenderLoop();
})();
