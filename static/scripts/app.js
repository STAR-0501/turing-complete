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
let mousePos = { x: 0, y: 0 };
let isPanning = false;
let panOffset = { x: 0, y: 0 };
let canvasOffset = { x: 0, y: 0 };

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
    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseup', handleMouseUp);
    window.addEventListener('mouseup', handleMouseUp);
    canvas.addEventListener('auxclick', handleMouseDown); // 支持中键点击
    // 阻止右键菜单
    canvas.addEventListener('contextmenu', (e) => {
        e.preventDefault();
    });
    // 阻止中键默认的滚动行为
    canvas.addEventListener('mousedown', (e) => {
        if (e.button === 1) {
            e.preventDefault();
        }
    });
    // 添加滚轮缩放功能
    canvas.addEventListener('wheel', handleWheel);
    window.addEventListener('resize', resizeCanvas);
    
    // 定期从服务器同步状态 (为了AI指令系统的实时性)
    setInterval(async () => {
        // 如果正在操作中，或者刚保存完（防止覆盖最新的本地改动），不从服务器加载
        const now = Date.now();
        if (!isDragging && !isDrawingWire && !isPlacingElement && !isPanning && (now - lastSaveTime > 3000)) {
            await loadFromServer();
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
        return function() {
            // 取消当前正在放置的元件
            if (isPlacingElement) {
                isPlacingElement = false;
                currentElementToPlace = null;
            }
            
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
    
    // 添加键盘事件监听器
    window.addEventListener('keydown', handleKeyDown);
    
    // 处理键盘按下事件
    function handleKeyDown(e) {
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
        
        // Esc 取消粘贴模式
        if (e.key === 'Escape') {
            cancelPaste();
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
    render(ctx, elements, wires, selectedElement, selectedWire);
}

/**
 * 调整画布大小
 */
function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    render(ctx, elements, wires, selectedElement, selectedWire);
}

/**
 * 添加元件
 * @param {string} type - 元件类型
 */
function addElement(type) {
    // 创建临时元素
    const element = createElement(type, mousePos.x, mousePos.y);
    if (element) {
        // 设置元素位置为鼠标位置
        element.x = mousePos.x - element.width / 2;
        element.y = mousePos.y - element.height / 2;
        currentElementToPlace = element;
        isPlacingElement = true;
        document.getElementById('status-bar').textContent = '请点击鼠标左键放置元件';
    }
}

/**
 * 复制元素 - 使用跟随鼠标模式
 * @param {object} sourceElement - 要复制的源元素
 */
function duplicateElement(sourceElement) {
    // 创建临时元素，位置在鼠标附近
    const newElement = createElement(sourceElement.type, mousePos.x, mousePos.y);
    if (newElement) {
        // 复制状态（对于INPUT元件）
        if (sourceElement.type === 'INPUT') {
            newElement.state = sourceElement.state;
        }
        
        // 设置元素位置为鼠标位置（居中）
        newElement.x = mousePos.x - newElement.width / 2;
        newElement.y = mousePos.y - newElement.height / 2;
        
        // 设置为正在放置状态，跟随鼠标
        currentElementToPlace = newElement;
        isPlacingElement = true;
        document.getElementById('status-bar').textContent = '请点击鼠标左键放置复制的元件';
        
        return newElement;
    }
    return null;
}

/**
 * 处理鼠标按下事件
 * @param {MouseEvent} e - 鼠标事件
 */
function handleMouseDown(e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
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
    
    // 如果正在放置元素，不处理其他左键事件
    if (isPlacingElement) {
        return;
    }
    
    // 如果正在粘贴模式，左键点击执行粘贴
    if (isPasting && e.button === 0) {
        executePaste();
        return;
    }
    
    // 检查是否点击了端口
    for (const element of elements) {
        for (const input of element.inputs) {
            const portX = element.x + input.x;
            const portY = element.y + input.y;
            if (distance(mouseX, mouseY, portX, portY) < 10) {
                isDrawingWire = true;
                wireStart = { elementId: element.id, portId: input.id, x: portX, y: portY, isInput: true };
                document.getElementById('status-bar').textContent = '正在绘制导线...';
                return;
            }
        }
        for (const output of element.outputs) {
            const portX = element.x + output.x;
            const portY = element.y + output.y;
            if (distance(mouseX, mouseY, portX, portY) < 10) {
                isDrawingWire = true;
                wireStart = { elementId: element.id, portId: output.id, x: portX, y: portY, isInput: false };
                document.getElementById('status-bar').textContent = '正在绘制导线...';
                return;
            }
        }
    }
    
    // 检查是否点击了元件
    for (const element of elements) {
        if (mouseX >= element.x && mouseX <= element.x + element.width &&
            mouseY >= element.y && mouseY <= element.y + element.height) {
            
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
                // 输入切换工具：切换输入状态
                element.state = !element.state;
                saveState();
                elements = calculateCircuit(elements, wires);
                document.getElementById('status-bar').textContent = `输入状态已切换为: ${element.state ? '1' : '0'}`;
                render(ctx, elements, wires, selectedElement, selectedWire);
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
                render(ctx, elements, wires, selectedElement, selectedWire);
                return;
            } else {
                // 选择工具：选择并准备拖拽
                // 检查是否点击了已选中的多选元件之一
                if (selectedElements.length > 1 && selectedElements.includes(element)) {
                    // 开始集体拖动
                    isGroupDragging = true;
                    groupDragStart = { x: mouseX, y: mouseY };
                    groupDragOffsets = selectedElements.map(el => ({
                        element: el,
                        offsetX: mouseX - el.x,
                        offsetY: mouseY - el.y
                    }));
                    document.getElementById('status-bar').textContent = `集体拖动 ${selectedElements.length} 个元件`;
                } else {
                    // 单选模式
                    selectedElement = element;
                    selectedWire = null;
                    selectedElements = []; // 清除多选状态
                    dragOffset.x = mouseX - element.x;
                    dragOffset.y = mouseY - element.y;
                    isDragging = true;
                    document.getElementById('status-bar').textContent = `选中元件: ${element.type}`;
                }
                render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements);
                return;
            }
        }
    }
    
    // 检查是否点击了导线
    for (const wire of wires) {
        if (isPointOnWire(mouseX, mouseY, wire)) {
            if (currentTool === 'delete') {
                // 删除工具：删除导线
                wires = wires.filter(w => w.id !== wire.id);
                selectedWire = null;
                saveState();
                elements = calculateCircuit(elements, wires);
                document.getElementById('status-bar').textContent = '导线已删除';
                render(ctx, elements, wires, selectedElement, selectedWire);
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
    
    // 点击空白处
    console.log('点击空白处: currentTool=', currentTool, 'button=', e.button);
    if (currentTool === 'select' && e.button === 0) { // 左键 - 框选
        // 开始框选
        isSelecting = true;
        isPanning = false; // 确保不会同时触发
        selectionStart = { x: mouseX, y: mouseY };
        selectionEnd = { x: mouseX, y: mouseY };
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
    
    // 处理拖动屏幕 (Panning)
    if (isPanning) {
        // 计算偏移量
        const deltaX = mouseX - panOffset.x;
        const deltaY = mouseY - panOffset.y;
        
        // 更新所有元件的位置
        for (const element of elements) {
            element.x += deltaX;
            element.y += deltaY;
        }
        
        // 更新所有导线的位置
        for (const wire of wires) {
            wire.start.x += deltaX;
            wire.start.y += deltaY;
            wire.end.x += deltaX;
            wire.end.y += deltaY;
        }
        
        // 更新临时元素的位置
        if (currentElementToPlace) {
            currentElementToPlace.x += deltaX;
            currentElementToPlace.y += deltaY;
        }
        
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
            grid.style.backgroundPosition = `${bgX + deltaX}px ${bgY + deltaY}px`;
        }
        
        // 更新偏移量
        panOffset = { x: mouseX, y: mouseY };
        
        // 重新渲染并返回
        render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements);
        
        // 如果正在放置元件，也要绘制预览
        if (isPlacingElement && currentElementToPlace) {
            drawTemporaryElement(ctx, currentElementToPlace);
        }
        
        return;
    }
    
    // 更新框选区域
    if (isSelecting) {
        selectionEnd = { x: mouseX, y: mouseY };
        updateSelection();
        render(ctx, elements, wires, selectedElement, selectedWire, getSelectionRect(), selectedElements);
        return;
    }
    
    // 处理集体拖动
    if (isGroupDragging && selectedElements.length > 0) {
        for (const item of groupDragOffsets) {
            const el = item.element;
            el.x = mouseX - item.offsetX;
            el.y = mouseY - item.offsetY;
            
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
        render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements);
        return;
    }
    
    // 更新粘贴预览位置
    if (isPasting) {
        pasteOffset = { x: mouseX, y: mouseY };
        render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, clipboardElements, pasteOffset, isPasting);
        return;
    }
    
    if (isDragging && selectedElement) {
        selectedElement.x = mouseX - dragOffset.x;
        selectedElement.y = mouseY - dragOffset.y;
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
        render(ctx, elements, wires, selectedElement, selectedWire);
    }
    
    if (isDrawingWire) {
        render(ctx, elements, wires, selectedElement, selectedWire);
        // 绘制临时导线
        ctx.beginPath();
        ctx.moveTo(wireStart.x, wireStart.y);
        ctx.lineTo(mouseX, mouseY);
        ctx.strokeStyle = '#00ffff';
        ctx.lineWidth = 2;
        ctx.stroke();
    }
    
    if (isPlacingElement && currentElementToPlace) {
        // 更新当前要放置的元素位置
        currentElementToPlace.x = mouseX - currentElementToPlace.width / 2;
        currentElementToPlace.y = mouseY - currentElementToPlace.height / 2;
        render(ctx, elements, wires, selectedElement, selectedWire);
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
    // 绘制元件背景
    ctx.fillStyle = 'rgba(0, 255, 255, 0.2)';
    ctx.strokeStyle = 'rgba(0, 255, 255, 0.7)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.rect(element.x, element.y, element.width, element.height);
    ctx.fill();
    ctx.stroke();
    
    // 绘制元件符号
    ctx.fillStyle = '#00ffff';
    ctx.font = '14px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    
    switch (element.type) {
        case 'AND':
            // 绘制与门符号
            ctx.strokeStyle = '#00ffff';
            ctx.lineWidth = 2;
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
            ctx.lineWidth = 2;
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
            ctx.lineWidth = 2;
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
    }
    
    // 绘制端口
    for (const input of element.inputs) {
        const portX = element.x + input.x;
        const portY = element.y + input.y;
        ctx.fillStyle = '#00ffff';
        ctx.beginPath();
        ctx.arc(portX, portY, 5, 0, Math.PI * 2);
        ctx.fill();
    }
    
    for (const output of element.outputs) {
        const portX = element.x + output.x;
        const portY = element.y + output.y;
        ctx.fillStyle = '#00ffff';
        ctx.beginPath();
        ctx.arc(portX, portY, 5, 0, Math.PI * 2);
        ctx.fill();
    }
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
    render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements);
}

/**
 * 复制选中的元件到剪贴板
 */
function copySelected() {
    if (selectedElements.length === 0) {
        document.getElementById('status-bar').textContent = '没有选中的元件可复制';
        return;
    }
    
    // 获取当前网格大小作为缩放参考
    let gridSize = 20;
    const grid = document.getElementById('grid');
    if (grid) {
        const currentBgSize = getComputedStyle(grid).backgroundSize;
        const sizeMatch = currentBgSize.match(/(\d+)px\s+(\d+)px/);
        if (sizeMatch) {
            gridSize = parseInt(sizeMatch[1]);
        }
    }
    const scaleFactor = gridSize / 20; // 相对于默认20px的缩放比例
    
    // 深拷贝选中的元件
    clipboardElements = selectedElements.map(el => ({
        ...el,
        _originalId: el.id, // 保存原始ID用于导线映射
        id: generateId(), // 生成新ID
        inputs: el.inputs.map(input => ({ ...input })),
        outputs: el.outputs.map(output => ({ ...output }))
    }));
    
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
    
    // 保存相对偏移量和缩放比例
    clipboardElements.forEach(el => {
        el._copyOffsetX = el.x - centerX;
        el._copyOffsetY = el.y - centerY;
        el._scaleFactor = scaleFactor;
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
    
    isPasting = true;
    pasteOffset = { x: mousePos.x, y: mousePos.y };
    document.getElementById('status-bar').textContent = '粘贴模式：点击鼠标左键放置，按 Esc 取消';
    render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, clipboardElements, pasteOffset, isPasting);
}

/**
 * 执行粘贴
 */
function executePaste() {
    if (!isPasting || clipboardElements.length === 0) return;
    
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
    
    const newElements = [];
    const idMapping = {}; // 旧ID到新ID的映射
    
    // 创建新元件
    for (const template of clipboardElements) {
        const newElement = createElement(template.type, 0, 0);
        if (newElement) {
            // 计算缩放比例（当前缩放 / 复制时的缩放）
            const copyScale = template._scaleFactor || 1;
            const scaleRatio = currentScale / copyScale;
            
            // 复制属性，应用缩放
            newElement.x = pasteOffset.x + template._copyOffsetX * scaleRatio;
            newElement.y = pasteOffset.y + template._copyOffsetY * scaleRatio;
            newElement.state = template.state;
            
            // 缩放元件大小
            newElement.width = template.width * scaleRatio;
            newElement.height = template.height * scaleRatio;
            
            // 缩放端口位置
            for (let i = 0; i < newElement.inputs.length; i++) {
                if (template.inputs[i]) {
                    newElement.inputs[i].x = template.inputs[i].x * scaleRatio;
                    newElement.inputs[i].y = template.inputs[i].y * scaleRatio;
                }
            }
            for (let i = 0; i < newElement.outputs.length; i++) {
                if (template.outputs[i]) {
                    newElement.outputs[i].x = template.outputs[i].x * scaleRatio;
                    newElement.outputs[i].y = template.outputs[i].y * scaleRatio;
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
    render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements);
}

/**
 * 取消粘贴模式
 */
function cancelPaste() {
    if (isPasting) {
        isPasting = false;
        document.getElementById('status-bar').textContent = '已取消粘贴';
        render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements, clipboardElements, pasteOffset, isPasting);
    }
}

/**
 * 处理鼠标释放事件
 * @param {MouseEvent} e - 鼠标事件
 */
function handleMouseUp(e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    console.log('鼠标释放: button=', e.button, 'isPanning=', isPanning);
    
    // 处理右键释放 - 结束拖动屏幕
    if (e.button === 2) {
        console.log('检测到右键释放, isPanning=', isPanning);
        if (isPanning) {
            isPanning = false;
            saveState();
            document.getElementById('status-bar').textContent = '屏幕拖动完成';
            render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements);
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
            render(ctx, elements, wires, selectedElement, selectedWire, null, selectedElements);
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
        
        return;
    }
    
    if (isPlacingElement && currentElementToPlace) {
        // 放置元素
        elements.push(currentElementToPlace);
        saveState();
        isPlacingElement = false;
        currentElementToPlace = null;
        document.getElementById('status-bar').textContent = '元件放置成功';
        
        // 切换回选择工具状态
        currentTool = 'select';
        document.querySelectorAll('.toolbar button').forEach(btn => btn.classList.remove('active'));
        document.getElementById('btn-1').classList.add('active');
        
        render(ctx, elements, wires, selectedElement, selectedWire);
        return;
    }
    
    if (isDrawingWire) {
        // 检查是否点击了目标端口
        for (const element of elements) {
            if (element.id === wireStart.elementId) continue;
            
            for (const input of element.inputs) {
                const portX = element.x + input.x;
                const portY = element.y + input.y;
                if (distance(mouseX, mouseY, portX, portY) < 10) {
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
                    render(ctx, elements, wires, selectedElement, selectedWire);
                    return;
                }
            }
            
            for (const output of element.outputs) {
                const portX = element.x + output.x;
                const portY = element.y + output.y;
                if (distance(mouseX, mouseY, portX, portY) < 10) {
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
                    render(ctx, elements, wires, selectedElement, selectedWire);
                    return;
                }
            }
        }
        
        // 取消绘制导线
        isDrawingWire = false;
        wireStart = null;
        document.getElementById('status-bar').textContent = '取消绘制导线';
        render(ctx, elements, wires, selectedElement, selectedWire);
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
        render(ctx, elements, wires, selectedElement, selectedWire);
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
        
        render(ctx, elements, wires, selectedElement, selectedWire);
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
    render(ctx, elements, wires, selectedElement, selectedWire);
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
        
        // 渲染更新
        render(ctx, elements, wires, selectedElement, selectedWire);
        
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
    
    // 保存当前状态
    saveState();
    
    // 缩放所有元件
    for (const element of elements) {
        // 计算元件相对于鼠标的位置
        const relX = element.x - mouseX;
        const relY = element.y - mouseY;
        
        // 缩放元件位置
        element.x = mouseX + relX * scaleFactor;
        element.y = mouseY + relY * scaleFactor;
        
        // 缩放元件大小
        element.width *= scaleFactor;
        element.height *= scaleFactor;
        
        // 缩放端口位置
        for (const input of element.inputs) {
            input.x *= scaleFactor;
            input.y *= scaleFactor;
        }
        for (const output of element.outputs) {
            output.x *= scaleFactor;
            output.y *= scaleFactor;
        }
    }
    
    // 缩放所有导线
    for (const wire of wires) {
        // 计算导线相对于鼠标的位置
        const relStartX = wire.start.x - mouseX;
        const relStartY = wire.start.y - mouseY;
        const relEndX = wire.end.x - mouseX;
        const relEndY = wire.end.y - mouseY;
        
        // 缩放导线位置
        wire.start.x = mouseX + relStartX * scaleFactor;
        wire.start.y = mouseY + relStartY * scaleFactor;
        wire.end.x = mouseX + relEndX * scaleFactor;
        wire.end.y = mouseY + relEndY * scaleFactor;
    }
    
    // 缩放临时元素
    if (currentElementToPlace) {
        // 计算临时元素相对于鼠标的位置
        const relX = currentElementToPlace.x - mouseX;
        const relY = currentElementToPlace.y - mouseY;
        
        // 缩放临时元素位置
        currentElementToPlace.x = mouseX + relX * scaleFactor;
        currentElementToPlace.y = mouseY + relY * scaleFactor;
        
        // 缩放临时元素大小
        currentElementToPlace.width *= scaleFactor;
        currentElementToPlace.height *= scaleFactor;
        
        // 缩放临时元素端口位置
        for (const input of currentElementToPlace.inputs) {
            input.x *= scaleFactor;
            input.y *= scaleFactor;
        }
        for (const output of currentElementToPlace.outputs) {
            output.x *= scaleFactor;
            output.y *= scaleFactor;
        }
    }
    
    // 调整网格大小和位置
    const grid = document.getElementById('grid');
    if (grid) {
        // 获取当前网格大小
        const currentBgSize = getComputedStyle(grid).backgroundSize;
        const sizeMatch = currentBgSize.match(/(\d+)px\s+(\d+)px/);
        let gridSize = 20; // 默认网格大小
        if (sizeMatch) {
            gridSize = parseInt(sizeMatch[1]);
        }
        
        // 计算新的网格大小
        const newGridSize = Math.max(5, Math.min(100, gridSize * scaleFactor));
        
        // 获取当前网格位置
        const currentBgPos = grid.style.backgroundPosition || '0px 0px';
        const posMatch = currentBgPos.match(/(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px/);
        let bgX = 0, bgY = 0;
        if (posMatch) {
            bgX = parseFloat(posMatch[1]);
            bgY = parseFloat(posMatch[2]);
        }
        
        // 计算新的网格位置，确保网格与元件保持对齐
        // 鼠标位置相对于网格的偏移应该保持不变
        const gridOffsetX = (mouseX - bgX) / gridSize;
        const gridOffsetY = (mouseY - bgY) / gridSize;
        const newBgX = mouseX - gridOffsetX * newGridSize;
        const newBgY = mouseY - gridOffsetY * newGridSize;
        
        // 更新网格大小和位置
        grid.style.backgroundSize = `${newGridSize}px ${newGridSize}px`;
        grid.style.backgroundPosition = `${newBgX}px ${newBgY}px`;
    }
    
    // 重新渲染
    render(ctx, elements, wires, selectedElement, selectedWire);
    
    // 绘制临时元素
    if (isPlacingElement && currentElementToPlace) {
        drawTemporaryElement(ctx, currentElementToPlace);
    }
}

// 初始化应用
(async function() {
    await init();
})();