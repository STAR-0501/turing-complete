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
        inputs: [
            { id: generateId(), x: -5, y: 15 },
            { id: generateId(), x: -5, y: 45 }
        ],
        outputs: [
            { id: generateId(), x: 85, y: 30 }
        ],
        state: false
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
        inputs: [
            { id: generateId(), x: -5, y: 15 },
            { id: generateId(), x: -5, y: 45 }
        ],
        outputs: [
            { id: generateId(), x: 85, y: 30 }
        ],
        state: false
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
        inputs: [
            { id: generateId(), x: -5, y: 30 }
        ],
        outputs: [
            { id: generateId(), x: 85, y: 30 }
        ],
        state: false
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
        inputs: [],
        outputs: [
            { id: generateId(), x: 65, y: 30 }
        ],
        state: false
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
        inputs: [
            { id: generateId(), x: -5, y: 30 }
        ],
        outputs: [],
        state: false
    };
}

/**
 * 根据类型创建元件
 * @param {string} type - 元件类型
 * @param {number} x - x坐标
 * @param {number} y - y坐标
 * @returns {object} 元件对象
 */
export function createElement(type, x, y) {
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
        default:
            return null;
    }
}