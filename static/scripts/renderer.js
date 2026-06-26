/**
 * 渲染模块
 * 负责画布的渲染
 */

/**
 * 渲染画布
 * @param {CanvasRenderingContext2D} ctx - 画布上下文
 * @param {Array} elements - 元件数组
 * @param {Array} wires - 导线数组
 * @param {object} selectedElement - 选中的元件
 * @param {object} selectedWire - 选中的导线
 * @param {object} selectionRect - 框选矩形
 * @param {Array} selectedElements - 多选状态下的选中元件数组
 * @param {Array} clipboardElements - 剪贴板中的元件（粘贴预览）
 * @param {object} pasteOffset - 粘贴位置偏移量
 * @param {boolean} isPasting - 是否正在粘贴模式
 */
export function render(
  ctx,
  elements,
  wires,
  selectedElement,
  selectedWire,
  selectionRect = null,
  selectedElements = [],
  clipboardElements = [],
  pasteOffset = null,
  isPasting = false,
  zoom = 1,
  camera = { x: 0, y: 0 },
  signalAnimation = null,
) {
  // 清空画布
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);

  // 应用相机变换
  ctx.save();
  ctx.translate(ctx.canvas.width / 2, ctx.canvas.height / 2);
  ctx.scale(zoom, zoom);
  ctx.translate(-camera.x, -camera.y);

  // 绘制导线
  for (const wire of wires) {
    // 确定导线状态
    let wireColor;

    // 检查导线是否已连接（两端都有元件）
    const isConnected = wire.start.elementId && wire.end.elementId;

    if (isConnected) {
      // 已连接的导线，根据信号状态显示颜色
      const wireState = wire.state || false;
      wireColor = wireState ? '#00ff00' : '#ff0000';
    } else {
      // 未连接的导线，显示灰色
      wireColor = '#888888';
    }

    ctx.beginPath();
    ctx.moveTo(wire.start.x, wire.start.y);
    ctx.lineTo(wire.end.x, wire.end.y);
    ctx.strokeStyle = wireColor;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  if (signalAnimation && signalAnimation.active && Array.isArray(signalAnimation.wireTravels)) {
    const now = performance.now();
    const t = now - signalAnimation.startTime;
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    for (const travel of signalAnimation.wireTravels) {
      const local = t - travel.startOffset;
      if (local <= 0) continue;
      const progress = Math.min(1, local / travel.duration);
      if (progress <= 0 || progress >= 1) continue;
      const x = travel.fromX + (travel.toX - travel.fromX) * progress;
      const y = travel.fromY + (travel.toY - travel.fromY) * progress;

      ctx.beginPath();
      ctx.moveTo(travel.fromX, travel.fromY);
      ctx.lineTo(x, y);
      ctx.strokeStyle = travel.color;
      ctx.lineWidth = 4 / zoom;
      ctx.stroke();

      ctx.fillStyle = travel.color;
      ctx.beginPath();
      ctx.arc(x, y, 4 / zoom, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // 绘制元件
  for (const element of elements) {
    // 确定元件状态
    const elementState = element.state || false;
    const isByteElement = element.type === 'BYTE_INPUT' || element.type === 'BYTE_OUTPUT';
    let elementColor;
    if (isByteElement) {
      elementColor = '#4488ff';
    } else {
      elementColor = elementState ? '#00ff00' : '#ff0000';
    }

    // 检查是否被多选选中
    const isMultiSelected = selectedElements.includes(element);

    // 绘制元件背景
    if (isMultiSelected) {
      // 多选高亮 - 使用青色边框
      ctx.fillStyle = isByteElement
        ? 'rgba(68, 136, 255, 0.2)'
        : `rgba(${elementState ? '0, 255, 0' : '255, 0, 0'}, 0.2)`;
      ctx.strokeStyle = '#00ffff';
      ctx.lineWidth = 3;
    } else {
      ctx.fillStyle = isByteElement
        ? 'rgba(68, 136, 255, 0.1)'
        : `rgba(${elementState ? '0, 255, 0' : '255, 0, 0'}, 0.1)`;
      ctx.strokeStyle = elementColor;
      ctx.lineWidth = 1;
    }
    ctx.beginPath();
    ctx.rect(element.x, element.y, element.width, element.height);
    ctx.fill();
    ctx.stroke();

    // 如果是多选选中，绘制额外的选中标记
    if (isMultiSelected) {
      ctx.strokeStyle = '#00ffff';
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.rect(element.x - 3, element.y - 3, element.width + 6, element.height + 6);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 绘制元件符号
    ctx.fillStyle = elementColor;
    ctx.font = '14px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    // 清空填充颜色（只保留文字，不覆盖背景色块）
    ctx.fillStyle = elementColor;
    ctx.font = 'bold 22px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    switch (element.type) {
      case 'AND':
        ctx.fillText('AND', element.x + element.width / 2, element.y + element.height / 2);
        break;
      case 'OR':
        ctx.fillText('OR', element.x + element.width / 2, element.y + element.height / 2);
        break;
      case 'NOT':
        ctx.fillText('NOT', element.x + element.width / 2, element.y + element.height / 2);
        break;
      case 'INPUT':
        ctx.fillText('IN', element.x + element.width / 2, element.y + element.height / 2);
        break;
      case 'OUTPUT':
        ctx.fillText('OUT', element.x + element.width / 2, element.y + element.height / 2);
        break;
      case 'BYTE_INPUT':
        // 绘制 BYTE_INPUT 边框（双线）
        ctx.strokeStyle = elementColor;
        ctx.lineWidth = 2;
        ctx.strokeRect(element.x, element.y, element.width, element.height);
        // 绘制字节数值
        ctx.fillStyle = '#ffff00';
        ctx.font = 'bold 28px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const inVal = (element.byteValue !== undefined ? element.byteValue : 0);
        ctx.fillText(inVal.toString(), element.x + element.width / 2, element.y + element.height / 2 - 6);
        // 绘制 "BIN" 标签
        ctx.fillStyle = elementColor;
        ctx.font = '10px Arial';
        ctx.fillText('BIN', element.x + element.width / 2, element.y + element.height / 2 + 20);
        break;
      case 'BYTE_OUTPUT':
        // 绘制 BYTE_OUTPUT 边框（双线）
        ctx.strokeStyle = elementColor;
        ctx.lineWidth = 2;
        ctx.strokeRect(element.x, element.y, element.width, element.height);
        // 绘制字节数值
        ctx.fillStyle = '#ffff00';
        ctx.font = 'bold 28px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const outVal = (element.byteValue !== undefined ? element.byteValue : 0);
        ctx.fillText(outVal.toString(), element.x + element.width / 2, element.y + element.height / 2 - 6);
        // 绘制 "BOUT" 标签
        ctx.fillStyle = elementColor;
        ctx.font = '10px Arial';
        ctx.fillText('BOUT', element.x + element.width / 2, element.y + element.height / 2 + 20);
        break;
      case 'FUNCTION':
        // 绘制模块块边框
        ctx.strokeStyle = elementColor;
        ctx.lineWidth = 2;
        ctx.strokeRect(element.x, element.y, element.width, element.height);
        // 绘制模块名称
        ctx.fillStyle = elementColor;
        ctx.font = '12px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(element.name || 'Func', element.x + element.width / 2, element.y + element.height / 2);
        break;
    }

    // 绘制端口
    for (const input of element.inputs) {
      const portX = element.x + input.x;
      const portY = element.y + input.y;
      // 输入端口状态与元件状态一致
      ctx.fillStyle = elementColor;
      ctx.beginPath();
      ctx.arc(portX, portY, 5, 0, Math.PI * 2);
      ctx.fill();
    }

    for (const output of element.outputs) {
      const portX = element.x + output.x;
      const portY = element.y + output.y;

      // 模块元件：根据 outputStates 显示各输出端口状态
      let portState = false;
      if (element.type === 'FUNCTION' && element.outputStates) {
        const outputIndex = element.outputs.indexOf(output);
        portState = element.outputStates[outputIndex] || false;
      } else if (element.type === 'BYTE_INPUT' && element.portStates) {
        const outputIndex = element.outputs.indexOf(output);
        portState = element.portStates[outputIndex] || false;
      } else {
        // 非模块元件：输出端口状态与元件状态一致
        portState = element.state || false;
      }

      // BYTE 元件端口使用蓝色，非 BYTE 元件使用红绿
      if (element.type === 'BYTE_INPUT' || element.type === 'BYTE_OUTPUT') {
        ctx.fillStyle = portState ? '#66aaff' : '#224488';
      } else {
        ctx.fillStyle = portState ? '#00ff00' : '#ff0000';
      }
      ctx.beginPath();
      ctx.arc(portX, portY, 5, 0, Math.PI * 2);
      ctx.fill();
    }

    // 绘制元件注释（黄色文字，绘制在元件右侧）
    if (element.comment && element.comment.trim()) {
      ctx.save();
      ctx.font = 12 / zoom + 'px Arial';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      const commentX = element.x + element.width + 10;
      const commentY = element.y;
      ctx.fillStyle = '#ffff00';
      const lines = element.comment.split('\n');
      for (let i = 0; i < lines.length; i++) {
        ctx.fillText(lines[i], commentX, commentY + i * (16 / zoom));
      }
      ctx.restore();
    }
  }

  // 绘制框选矩形
  if (selectionRect && selectionRect.width > 0 && selectionRect.height > 0) {
    ctx.strokeStyle = '#00ffff';
    ctx.lineWidth = 1 / zoom;
    ctx.setLineDash([5 / zoom, 5 / zoom]);
    ctx.strokeRect(selectionRect.x, selectionRect.y, selectionRect.width, selectionRect.height);
    ctx.setLineDash([]);

    // 填充半透明背景
    ctx.fillStyle = 'rgba(0, 255, 255, 0.1)';
    ctx.fillRect(selectionRect.x, selectionRect.y, selectionRect.width, selectionRect.height);
  }

  // 绘制粘贴预览
  if (isPasting && clipboardElements.length > 0 && pasteOffset) {
    for (const template of clipboardElements) {
      // 不进行缩放，使用原始大小
      const x = pasteOffset.x + template._copyOffsetX;
      const y = pasteOffset.y + template._copyOffsetY;
      const width = template.width;
      const height = template.height;

      // 绘制预览元件（半透明虚线）
      ctx.strokeStyle = 'rgba(0, 255, 255, 0.7)';
      ctx.fillStyle = 'rgba(0, 255, 255, 0.1)';
      ctx.lineWidth = 2 / zoom;
      ctx.setLineDash([5 / zoom, 5 / zoom]);

      // 绘制元件背景
      ctx.beginPath();
      ctx.rect(x, y, width, height);
      ctx.fill();
      ctx.stroke();

      // 绘制元件符号（文字标签，大小随框大小变化，与红绿色元件一致）
      ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      switch (template.type) {
        case 'AND':
          ctx.font = 'bold ' + Math.max(10, Math.min(22, height * 0.35)) + 'px sans-serif';
          ctx.fillText('AND', x + width / 2, y + height / 2);
          break;
        case 'OR':
          ctx.font = 'bold ' + Math.max(10, Math.min(22, height * 0.35)) + 'px sans-serif';
          ctx.fillText('OR', x + width / 2, y + height / 2);
          break;
        case 'NOT':
          ctx.font = 'bold ' + Math.max(10, Math.min(22, height * 0.35)) + 'px sans-serif';
          ctx.fillText('NOT', x + width / 2, y + height / 2);
          break;
        case 'INPUT':
          ctx.font = 'bold ' + Math.max(10, Math.min(22, height * 0.35)) + 'px sans-serif';
          ctx.fillText('IN', x + width / 2, y + height / 2);
          break;
        case 'OUTPUT':
          ctx.font = 'bold ' + Math.max(10, Math.min(22, height * 0.35)) + 'px sans-serif';
          ctx.fillText('OUT', x + width / 2, y + height / 2);
          break;
        case 'BYTE_INPUT':
        case 'BYTE_OUTPUT':
          ctx.font = 'bold ' + Math.max(14, Math.min(28, height * 0.25)) + 'px monospace';
          const bv = (template.byteValue !== undefined ? template.byteValue : 0);
          ctx.fillText(bv.toString(), x + width / 2, y + height / 2);
          break;
        case 'FUNCTION':
          ctx.font = 'bold ' + Math.max(8, Math.min(14, height * 0.25)) + 'px sans-serif';
          ctx.fillText(template.name || 'Func', x + width / 2, y + height / 2);
          break;
      }

      // 绘制端口
      for (const input of template.inputs) {
        const portX = x + input.x;
        const portY = y + input.y;
        ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
        ctx.beginPath();
        ctx.arc(portX, portY, 5 / zoom, 0, Math.PI * 2);
        ctx.fill();
      }

      for (const output of template.outputs) {
        const portX = x + output.x;
        const portY = y + output.y;
        ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
        ctx.beginPath();
        ctx.arc(portX, portY, 5 / zoom, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.setLineDash([]);
  }

  // 恢复上下文
  ctx.restore();
}
