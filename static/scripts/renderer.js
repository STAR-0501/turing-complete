/**
 * 渲染模块
 * 负责画布的渲染
 */

/**
 * 渲染函数
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
export function render(ctx, elements, wires, selectedElement, selectedWire, selectionRect = null, selectedElements = [], clipboardElements = [], pasteOffset = null, isPasting = false, zoom = 1, camera = { x: 0, y: 0 }, signalAnimation = null) {
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
        const elementColor = elementState ? '#00ff00' : '#ff0000';
        
        // 检查是否被多选选中
        const isMultiSelected = selectedElements.includes(element);
        
        // 绘制元件背景
        if (isMultiSelected) {
            // 多选高亮 - 使用青色边框
            ctx.fillStyle = `rgba(${elementState ? '0, 255, 0' : '255, 0, 0'}, 0.2)`;
            ctx.strokeStyle = '#00ffff';
            ctx.lineWidth = 3;
        } else {
            ctx.fillStyle = `rgba(${elementState ? '0, 255, 0' : '255, 0, 0'}, 0.1)`;
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
        
        switch (element.type) {
            case 'AND':
                // 绘制与门符号
                ctx.strokeStyle = elementColor;
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
                ctx.strokeStyle = elementColor;
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
                ctx.strokeStyle = elementColor;
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
                ctx.fillStyle = elementColor;
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
                ctx.strokeStyle = elementColor;
                ctx.lineWidth = 2;
                ctx.strokeRect(element.x, element.y, element.width, element.height);
                // 绘制函数名称
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
            
            // 函数元件：根据 outputStates 显示各输出端口状态
            let portState = false;
            if (element.type === 'FUNCTION' && element.outputStates) {
                const outputIndex = element.outputs.indexOf(output);
                portState = element.outputStates[outputIndex] || false;
            }
            
            // 根据端口状态显示不同颜色
            ctx.fillStyle = portState ? '#00ff00' : '#666666';
            ctx.beginPath();
            ctx.arc(portX, portY, 5, 0, Math.PI * 2);
            ctx.fill();
        }
        
        // 绘制元件注释
        if (element.comment && element.comment.trim()) {
            ctx.save();
            ctx.font = (12 / zoom) + 'px Arial';
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
            
            // 绘制元件符号
            ctx.fillStyle = 'rgba(0, 255, 255, 0.7)';
            ctx.font = (14 / zoom) + 'px Arial';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            
            switch (template.type) {
                case 'AND':
                    ctx.strokeStyle = 'rgba(0, 255, 255, 0.7)';
                    ctx.lineWidth = 2 / zoom;
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
                    ctx.lineWidth = 2 / zoom;
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
                    ctx.lineWidth = 2 / zoom;
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
                    ctx.font = (12 / zoom) + 'px Arial';
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
