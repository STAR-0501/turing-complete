/**
 * 元件模块
 * 负责元件的创建和管理
 */
import { generateId } from './utils.js';

/**
 * 创建与门元件
 * @param {number} x - x坐标
 * @param {number} y - y坐标
 * @returns {object} 与门元件对象
 */
export function createANDGate(x, y) {
    return {
        id: generateId(),
        type: 'AND',
        x, y,
        width: 80,
        height: 60,
        realWidth: 80,
        realHeight: 60,
        inputs: [
            { id: generateId(), x: -5, y: 15, realX: -5, realY: 15 },
            { id: generateId(), x: -5, y: 45, realX: -5, realY: 45 }
        ],
        outputs: [
            { id: generateId(), x: 85, y: 30, realX: 85, realY: 30 }
        ],
        state: false,
        comment: ''
    };
}

/**
 * 创建或门元件
 * @param {number} x - x坐标
 * @param {number} y - y坐标
 * @returns {object} 或门元件对象
 */
export function createORGate(x, y) {
    return {
        id: generateId(),
        type: 'OR',
        x, y,
        width: 80,
        height: 60,
        realWidth: 80,
        realHeight: 60,
        inputs: [
            { id: generateId(), x: -5, y: 15, realX: -5, realY: 15 },
            { id: generateId(), x: -5, y: 45, realX: -5, realY: 45 }
        ],
        outputs: [
            { id: generateId(), x: 85, y: 30, realX: 85, realY: 30 }
        ],
        state: false,
        comment: ''
    };
}

/**
 * 创建非门元件
 * @param {number} x - x坐标
 * @param {number} y - y坐标
 * @returns {object} 非门元件对象
 */
export function createNOTGate(x, y) {
    return {
        id: generateId(),
        type: 'NOT',
        x, y,
        width: 80,
        height: 60,
        realWidth: 80,
        realHeight: 60,
        inputs: [
            { id: generateId(), x: -5, y: 30, realX: -5, realY: 30 }
        ],
        outputs: [
            { id: generateId(), x: 85, y: 30, realX: 85, realY: 30 }
        ],
        state: false,
        comment: ''
    };
}

/**
 * 创建输入元件
 * @param {number} x - x坐标
 * @param {number} y - y坐标
 * @returns {object} 输入元件对象
 */
export function createInputBlock(x, y) {
    return {
        id: generateId(),
        type: 'INPUT',
        x, y,
        width: 60,
        height: 60,
        realWidth: 60,
        realHeight: 60,
        inputs: [],
        outputs: [
            { id: generateId(), x: 65, y: 30, realX: 65, realY: 30 }
        ],
        state: false,
        comment: ''
    };
}

/**
 * 创建输出元件
 * @param {number} x - x坐标
 * @param {number} y - y坐标
 * @returns {object} 输出元件对象
 */
export function createOutputBlock(x, y) {
    return {
        id: generateId(),
        type: 'OUTPUT',
        x, y,
        width: 60,
        height: 60,
        realWidth: 60,
        realHeight: 60,
        inputs: [
            { id: generateId(), x: -5, y: 30, realX: -5, realY: 30 }
        ],
        outputs: [],
        state: false,
        comment: ''
    };
}

/**
 * 创建函数元件
 * @param {number} x - x坐标
 * @param {number} y - y坐标
 * @param {string} name - 函数名称
 * @param {Array} functionElements - 函数内部的元件
 * @param {Array} functionWires - 函数内部的导线
 * @param {Array} inputElements - 函数的输入元件ID列表
 * @param {Array} outputElements - 函数的输出元件ID列表
 * @returns {object} 函数元件对象
 */
export function createFunctionElement(x, y, name, functionElements, functionWires, inputElements, outputElements) {
    const inputCount = inputElements.length;
    const outputCount = outputElements.length;
    const height = Math.max(60, Math.max(inputCount, outputCount) * 25 + 20);
    const inputs = [];
    
    for (let i = 0; i < inputCount; i++) {
        inputs.push({
            id: generateId(),
            x: -5,
            y: 20 + i * 25,
            realX: -5,
            realY: 20 + i * 25
        });
    }
    
    const outputs = [];
    for (let i = 0; i < outputCount; i++) {
        outputs.push({
            id: generateId(),
            x: 105,
            y: 20 + i * 25,
            realX: 105,
            realY: 20 + i * 25
        });
    }
    
    return {
        id: generateId(),
        type: 'FUNCTION',
        name: name,
        x, y,
        width: 100,
        height: height,
        realWidth: 100,
        realHeight: height,
        inputs: inputs,
        outputs: outputs,
        state: false,
        comment: '',
        functionData: {
            elements: functionElements,
            wires: functionWires,
            inputElementIds: inputElements,
            outputElementIds: outputElements
        }
    };
}

/**
 * 根据类型创建元件
 * @param {string} type - 元件类型
 * @param {number} x - x坐标
 * @param {number} y - y坐标
 * @param {object} options - 额外选项（用于函数元件）
 * @returns {object} 元件对象
 */
export function createElement(type, x, y, options = {}) {
    switch (type) {
        case 'AND':
            return createANDGate(x, y);
        case 'OR':
            return createORGate(x, y);
        case 'NOT':
            return createNOTGate(x, y);
        case 'INPUT':
            return createInputBlock(x, y);
        case 'OUTPUT':
            return createOutputBlock(x, y);
        case 'FUNCTION':
            return createFunctionElement(
                x, y,
                options.name,
                options.functionElements,
                options.functionWires,
                options.inputElements,
                options.outputElements
            );
        default:
            return null;
    }
}