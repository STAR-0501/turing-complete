/**
 * 电路计算模块
 * 负责电路的逻辑计算
 */

/**
 * 获取连接到元件输入端口的源元件状态
 * @param {Array} elements - 元件数组
 * @param {Array} wires - 导线数组
 * @param {string} targetElementId - 目标元件ID
 * @param {string} targetPortId - 目标输入端口ID
 * @returns {boolean|null} 源元件的状态，如果没有连接则返回null
 */
function getInputSourceState(elements, wires, targetElementId, targetPortId) {
    // 查找连接到该输入端口的导线
    // 导线可能有两种方向：
    // 1. start (输出) -> end (输入): end.elementId === targetElementId
    // 2. start (输入) -> end (输出): start.elementId === targetElementId
    
    for (const wire of wires) {
        // 情况1：导线的终点连接到目标元件的输入端口
        if (wire.end.elementId === targetElementId && wire.end.portId === targetPortId) {
            const sourceElement = elements.find(e => e.id === wire.start.elementId);
            if (sourceElement) {
                return sourceElement.state;
            }
        }
        // 情况2：导线的起点连接到目标元件的输入端口（方向相反）
        if (wire.start.elementId === targetElementId && wire.start.portId === targetPortId) {
            const sourceElement = elements.find(e => e.id === wire.end.elementId);
            if (sourceElement) {
                return sourceElement.state;
            }
        }
    }
    
    return null; // 没有连接
}

/**
 * 检查是否有导线连接到指定的输入端口
 * @param {Array} wires - 导线数组
 * @param {string} targetElementId - 目标元件ID
 * @param {string} targetPortId - 目标输入端口ID
 * @returns {boolean} 是否有连接
 */
function hasInputConnection(wires, targetElementId, targetPortId) {
    for (const wire of wires) {
        // 情况1：导线的终点连接到目标端口
        if (wire.end.elementId === targetElementId && wire.end.portId === targetPortId) {
            return true;
        }
        // 情况2：导线的起点连接到目标端口（方向相反）
        if (wire.start.elementId === targetElementId && wire.start.portId === targetPortId) {
            return true;
        }
    }
    return false;
}

/**
 * 计算电路
 * @param {Array} elements - 元件数组
 * @param {Array} wires - 导线数组
 * @returns {Array} 更新后的元件数组
 */
export function calculateCircuit(elements, wires) {
    let changed = true;
    // 重复计算直到所有元件状态稳定
    while (changed) {
        changed = false;
        
        // 计算逻辑门和输出元件
        for (const element of elements) {
            if (element.type === 'INPUT') {
                // 输入元件状态保持不变
                continue;
            }
            
            let newState = element.state;
            
            if (element.type === 'AND') {
                // 与门：所有输入为true时输出为true
                let allTrue = true;
                let allConnected = true;
                for (const input of element.inputs) {
                    if (hasInputConnection(wires, element.id, input.id)) {
                        const inputState = getInputSourceState(elements, wires, element.id, input.id);
                        if (inputState !== true) {
                            allTrue = false;
                            break;
                        }
                    } else {
                        allConnected = false;
                        break;
                    }
                }
                // 如果不是所有输入都有连接，或有输入为false，与门输出false
                newState = allConnected && allTrue;
            } else if (element.type === 'OR') {
                // 或门：任何输入为true时输出为true
                let anyTrue = false;
                let hasInput = false;
                for (const input of element.inputs) {
                    if (hasInputConnection(wires, element.id, input.id)) {
                        hasInput = true;
                        const inputState = getInputSourceState(elements, wires, element.id, input.id);
                        if (inputState === true) {
                            anyTrue = true;
                            break;
                        }
                    }
                }
                // 如果没有输入连接，或门输出false
                newState = hasInput ? anyTrue : false;
            } else if (element.type === 'NOT') {
                // 非门：输入为true时输出为false，反之亦然
                let inputTrue = false;
                let hasInput = false;
                for (const input of element.inputs) {
                    if (hasInputConnection(wires, element.id, input.id)) {
                        hasInput = true;
                        const inputState = getInputSourceState(elements, wires, element.id, input.id);
                        if (inputState === true) {
                            inputTrue = true;
                            break;
                        }
                    }
                }
                // 如果没有输入连接，非门输出false
                newState = hasInput ? !inputTrue : false;
            } else if (element.type === 'OUTPUT') {
                // 输出元件：显示输入状态
                let inputTrue = false;
                for (const input of element.inputs) {
                    if (hasInputConnection(wires, element.id, input.id)) {
                        const inputState = getInputSourceState(elements, wires, element.id, input.id);
                        if (inputState === true) {
                            inputTrue = true;
                            break;
                        }
                    }
                }
                newState = inputTrue;
            }
            
            // 检查状态是否改变
            if (element.state !== newState) {
                element.state = newState;
                changed = true;
            }
        }
    }
    
    // 更新导线状态
    for (const wire of wires) {
        // 确定导线状态：如果连接的是输出端口，使用源元件的状态
        let wireState = false;
        
        // 查找连接到导线起点的元件
        const startElement = elements.find(e => e.id === wire.start.elementId);
        if (startElement) {
            // 如果起点是输出端口，使用源元件的状态
            if (!wire.start.isInput) {
                wireState = startElement.state;
            }
        }
        
        // 查找连接到导线终点的元件
        const endElement = elements.find(e => e.id === wire.end.elementId);
        if (endElement) {
            // 如果终点是输出端口，使用目标元件的状态
            if (!wire.end.isInput) {
                wireState = endElement.state;
            }
        }
        
        wire.state = wireState;
    }
    
    return elements;
}
