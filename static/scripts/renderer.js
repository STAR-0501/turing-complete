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
 */
export function render(ctx, elements, wires, selectedElement, selectedWire) {
    // 清空画布
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    
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
    
    // 绘制元件
    for (const element of elements) {
        // 确定元件状态
        const elementState = element.state || false;
        const elementColor = elementState ? '#00ff00' : '#ff0000';
        
        // 绘制元件背景
        ctx.fillStyle = `rgba(${elementState ? '0, 255, 0' : '255, 0, 0'}, 0.1)`;
        ctx.strokeStyle = elementColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.rect(element.x, element.y, element.width, element.height);
        ctx.fill();
        ctx.stroke();
        
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
            // 输出端口状态与元件状态一致
            ctx.fillStyle = elementColor;
            ctx.beginPath();
            ctx.arc(portX, portY, 5, 0, Math.PI * 2);
            ctx.fill();
        }
    }
}