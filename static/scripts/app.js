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
    
    // 事件监听
    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseup', handleMouseUp);
    canvas.addEventListener('auxclick', handleMouseDown); // 支持中键点击
    // 阻止中键默认的滚动行为
    canvas.addEventListener('mousedown', (e) => {
        if (e.button === 1) {
            e.preventDefault();
        }
    });
    window.addEventListener('resize', resizeCanvas);
    
    // 辅助函数：设置工具状态
    function setTool(toolName, buttonId, statusText) {
        currentTool = toolName;
        document.getElementById('status-bar').textContent = statusText;
        // 重置所有按钮状态
        document.querySelectorAll('.toolbar button').forEach(btn => btn.classList.remove('active'));
        document.getElementById(buttonId).classList.add('active');
    }
    
    // 辅助函数：添加元件
    function addElementButtonHandler(type) {
        return function() {
            addElement(type);
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
    // 如果正在放置元素，不处理其他事件
    if (isPlacingElement) {
        return;
    }
    
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
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
                selectedElement = element;
                selectedWire = null;
                dragOffset.x = mouseX - element.x;
                dragOffset.y = mouseY - element.y;
                isDragging = true;
                document.getElementById('status-bar').textContent = `选中元件: ${element.type}`;
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
    if (currentTool === 'select') {
        // 开始拖动屏幕
        isPanning = true;
        panOffset = { x: mouseX, y: mouseY };
        document.getElementById('status-bar').textContent = '正在拖动屏幕...';
    } else {
        selectedElement = null;
        selectedWire = null;
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
            
            // 更新背景位置（与拖动方向相反，产生视差效果）
            grid.style.backgroundPosition = `${bgX - deltaX}px ${bgY - deltaY}px`;
        }
        
        // 更新偏移量
        panOffset = { x: mouseX, y: mouseY };
        
        // 重新渲染
        render(ctx, elements, wires, selectedElement, selectedWire);
        
        // 绘制临时元素
        if (isPlacingElement && currentElementToPlace) {
            drawTemporaryElement(ctx, currentElementToPlace);
        }
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
            ctx.beginPath();
            ctx.moveTo(element.x + 20, element.y + 10);
            ctx.lineTo(element.x + 20, element.y + 50);
            ctx.arc(element.x + 60, element.y + 30, 20, Math.PI * 1.5, Math.PI * 0.5);
            ctx.closePath();
            ctx.stroke();
            break;
        case 'OR':
            // 绘制或门符号
            ctx.beginPath();
            ctx.moveTo(element.x + 20, element.y + 10);
            ctx.lineTo(element.x + 20, element.y + 50);
            ctx.arc(element.x + 60, element.y + 30, 20, Math.PI * 1.5, Math.PI * 0.5);
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(element.x + 20, element.y + 30, 10, Math.PI * 0.5, Math.PI * 1.5);
            ctx.stroke();
            break;
        case 'NOT':
            // 绘制非门符号
            ctx.beginPath();
            ctx.moveTo(element.x + 20, element.y + 10);
            ctx.lineTo(element.x + 20, element.y + 50);
            ctx.arc(element.x + 50, element.y + 30, 10, Math.PI * 1.5, Math.PI * 0.5);
            ctx.lineTo(element.x + 70, element.y + 30);
            ctx.arc(element.x + 75, element.y + 30, 5, 0, Math.PI * 2);
            ctx.stroke();
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
 * 处理鼠标释放事件
 * @param {MouseEvent} e - 鼠标事件
 */
function handleMouseUp(e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    if (isPlacingElement && currentElementToPlace) {
        // 放置元素
        elements.push(currentElementToPlace);
        saveState();
        isPlacingElement = false;
        currentElementToPlace = null;
        document.getElementById('status-bar').textContent = '元件放置成功';
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
    
    // 如果刚刚完成了拖拽操作，保存状态（记录元素最终位置）
    if (isDragging) {
        saveState();
        document.getElementById('status-bar').textContent = '元素移动完成';
    }
    
    isDragging = false;
    
    if (isPanning) {
        isPanning = false;
        saveState();
        document.getElementById('status-bar').textContent = '屏幕拖动完成';
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
    } catch (error) {
        console.error('保存到本地存储失败:', error);
    }
}

/**
 * 保存到服务器
 */
async function saveToServer() {
    try {
        const response = await fetch('http://localhost:5000/api/save-circuit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                elements: elements,
                wires: wires
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
async function loadFromServer() {
    try {
        const response = await fetch('http://localhost:5000/api/load-circuit');
        const result = await response.json();
        if (result.elements) {
            elements = result.elements;
        }
        if (result.wires) {
            wires = result.wires;
        }
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
    } catch (error) {
        console.error('从本地存储加载失败:', error);
    }
}

// 初始化应用
(async function() {
    await init();
})();