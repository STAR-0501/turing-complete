/**
 * 工具函数模块
 * 包含一些通用的工具函数
 */

/**
 * 生成唯一ID
 * @returns {string} 唯一ID
 */
export function generateId() {
    return Math.random().toString(36).substr(2, 9);
}

/**
 * 计算两点之间的距离
 * @param {number} x1 - 第一个点的x坐标
 * @param {number} y1 - 第一个点的y坐标
 * @param {number} x2 - 第二个点的x坐标
 * @param {number} y2 - 第二个点的y坐标
 * @returns {number} 两点之间的距离
 */
export function distance(x1, y1, x2, y2) {
    return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
}

/**
 * 检查点是否在导线上
 * @param {number} x - 点的x坐标
 * @param {number} y - 点的y坐标
 * @param {object} wire - 导线对象
 * @returns {boolean} 是否在导线上
 */
export function isPointOnWire(x, y, wire) {
    const threshold = 5;
    const dx = wire.end.x - wire.start.x;
    const dy = wire.end.y - wire.start.y;
    const length = Math.sqrt(dx * dx + dy * dy);
    const t = ((x - wire.start.x) * dx + (y - wire.start.y) * dy) / (length * length);
    const closestX = wire.start.x + t * dx;
    const closestY = wire.start.y + t * dy;
    return distance(x, y, closestX, closestY) < threshold && t >= 0 && t <= 1;
}