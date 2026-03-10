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
        ctx.beginPath();
        ctx.moveTo(wire.start.x, wire.start.y);
        ctx.lineTo(wire.end.x, wire.end.y);
        ctx.strokeStyle = wire === selectedWire ? '#ff00ff' : '#00ffff';
        ctx.lineWidth = wire === selectedWire ? 3 : 2;
        ctx.stroke();
    }
    
    // 绘制元件
    for (const element of elements) {
        // 绘制元件背景
        ctx.fillStyle = element === selectedElement ? 'rgba(0, 255, 255, 0.3)' : 'rgba(0, 255, 255, 0.1)';
        ctx.strokeStyle = 'rgba(0, 255, 255, 0.5)';
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
}