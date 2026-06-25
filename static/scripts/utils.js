/**
 * 工具函数模块
 * 包含通用的工具函数
 */

/**
 * 生成唯一 ID
 * @returns {string} 唯一 ID
 */
export function generateId() {
  return Math.random().toString(36).substr(2, 9);
}

/**
 * 计算两点之间的距离
 * @param {number} x1 - 第一个点的 x 坐标
 * @param {number} y1 - 第一个点的 y 坐标
 * @param {number} x2 - 第二个点的 x 坐标
 * @param {number} y2 - 第二个点的 y 坐标
 * @returns {number} 两点之间的距离
 */
export function distance(x1, y1, x2, y2) {
  return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
}

/**
 * 检查点是否在导线上
 * @param {number} x - 点的 x 坐标
 * @param {number} y - 点的 y 坐标
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

/**
 * 将数值钳制在指定范围内
 * @param {number} v - 要钳制的值
 * @param {number} min - 最小值
 * @param {number} max - 最大值
 * @returns {number} 钳制后的值
 */
export function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

/**
 * 将屏幕坐标转换为画布世界坐标
 * @param {number} mx - 鼠标屏幕 x 坐标
 * @param {number} my - 鼠标屏幕 y 坐标
 * @param {HTMLCanvasElement} canvas - Canvas 元素
 * @param {number} zoom - 当前缩放级别
 * @param {{x:number, y:number}} camera - 相机偏移
 * @returns {{x:number, y:number}} 世界坐标
 */
export function screenToWorld(mx, my, canvas, zoom, camera) {
  return {
    x: (mx - canvas.width / 2) / zoom + camera.x,
    y: (my - canvas.height / 2) / zoom + camera.y,
  };
}

/**
 * 计算框选矩形
 * @param {{x:number, y:number}} p1 - 起点
 * @param {{x:number, y:number}} p2 - 终点
 * @returns {{x:number, y:number, width:number, height:number}} 标准化矩形
 */
export function getSelectionRect(p1, p2) {
  return {
    x: Math.min(p1.x, p2.x),
    y: Math.min(p1.y, p2.y),
    width: Math.abs(p2.x - p1.x),
    height: Math.abs(p2.y - p1.y),
  };
}

/**
 * 复制元件的端口位置
 * @param {object} dest - 目标元件
 * @param {object} src - 源元件
 */
export function copyPortPositions(dest, src) {
  for (let i = 0; i < dest.inputs.length; i++) {
    if (src.inputs[i]) {
      dest.inputs[i].x = src.inputs[i].x;
      dest.inputs[i].y = src.inputs[i].y;
    }
  }
  for (let i = 0; i < dest.outputs.length; i++) {
    if (src.outputs[i]) {
      dest.outputs[i].x = src.outputs[i].x;
      dest.outputs[i].y = src.outputs[i].y;
    }
  }
}

/**
 * DOM 快捷获取
 * @param {string} id - 元素 ID
 * @returns {HTMLElement|null}
 */
export function $(id) {
  return document.getElementById(id);
}
