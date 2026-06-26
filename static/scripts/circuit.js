/**
 * 电路计算模块
 * 负责电路的逻辑计算
 */

/**
 * 获取连接到元件输入端口的源元件状态
 * @param {Array} elements - 元件数组
 * @param {Array} wires - 导线数组
 * @param {string} targetElementId - 目标元件 ID
 * @param {string} targetPortId - 目标输入端口 ID
 * @returns {boolean|null} 源元件的状态，如果没有连接则返回 null
 */
function getInputSourceState(elements, wires, targetElementId, targetPortId) {
  // 查找连接到该输入端口的导线
  // 导线可能有两种方向：
  // 1. start (输出) -> end (输入): end.elementId === targetElementId
  // 2. start (输入) -> end (输出): start.elementId === targetElementId

  for (const wire of wires) {
    // 情况1：导线的终点连接到目标元件的输入端口
    if (wire.end.elementId === targetElementId && wire.end.portId === targetPortId) {
      const sourceElement = elements.find((e) => e.id === wire.start.elementId);
      if (sourceElement) {
        if (sourceElement.type === 'FUNCTION') {
          const outputs = sourceElement.outputs || [];
          const outIdx = outputs.findIndex((p) => p.id === wire.start.portId);
          const outputStates = sourceElement.outputStates || [];
          if (outIdx >= 0 && outIdx < outputStates.length) {
            return outputStates[outIdx];
          }
          return outputStates.length > 0 ? outputStates[0] : sourceElement.state;
        }
        if (sourceElement.type === 'BYTE_INPUT') {
          const outputs = sourceElement.outputs || [];
          const outIdx = outputs.findIndex((p) => p.id === wire.start.portId);
          const portStates = sourceElement.portStates || [];
          if (outIdx >= 0 && outIdx < portStates.length) {
            return portStates[outIdx];
          }
          return false;
        }
        return sourceElement.state;
      }
    }
    // 情况2：导线的起点连接到目标元件的输入端口（方向相反）
    if (wire.start.elementId === targetElementId && wire.start.portId === targetPortId) {
      const sourceElement = elements.find((e) => e.id === wire.end.elementId);
      if (sourceElement) {
        if (sourceElement.type === 'FUNCTION') {
          const outputs = sourceElement.outputs || [];
          const outIdx = outputs.findIndex((p) => p.id === wire.end.portId);
          const outputStates = sourceElement.outputStates || [];
          if (outIdx >= 0 && outIdx < outputStates.length) {
            return outputStates[outIdx];
          }
          return outputStates.length > 0 ? outputStates[0] : sourceElement.state;
        }
        if (sourceElement.type === 'BYTE_INPUT') {
          const outputs = sourceElement.outputs || [];
          const outIdx = outputs.findIndex((p) => p.id === wire.end.portId);
          const portStates = sourceElement.portStates || [];
          if (outIdx >= 0 && outIdx < portStates.length) {
            return portStates[outIdx];
          }
          return false;
        }
        return sourceElement.state;
      }
    }
  }

  return null; // 没有连接
}

/**
 * 检查是否有导线连接到指定的输入端口
 * @param {Array} wires - 导线数组
 * @param {string} targetElementId - 目标元件 ID
 * @param {string} targetPortId - 目标输入端口 ID
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
 * 计算模块元件的内部电路（支持递归嵌套模块）
 * @param {object} moduleElement - 模块元件
 * @param {Array} elements - 主电路元件数组
 * @param {Array} wires - 主电路导线数组
 * @param {Map} functionCache - 模块计算缓存，避免重复计算
 * @returns {Array} 模块元件各输出端口的状态数组
 */
// 将模块元件的输入端口值赋给内部的 INPUT 元件
function calculateModuleElement(moduleElement, elements, wires, functionCache = new Map(), depth = 0) {
  if (!moduleElement.moduleData) {
    return [];
  }
  if (depth >= 10) {
    return [];
  }

  // 深拷贝模块内部的元件和导线
  const subElements = JSON.parse(JSON.stringify(moduleElement.moduleData.elements));
  const subWires = JSON.parse(JSON.stringify(moduleElement.moduleData.wires));
  const inputElementIds = moduleElement.moduleData.inputElementIds;
  const outputElementIds = moduleElement.moduleData.outputElementIds || [];

  // 将模块元件的输入端口值赋给内部的 INPUT 元件
  for (let i = 0; i < moduleElement.inputs.length; i++) {
    const inputPort = moduleElement.inputs[i];
    const inputState = getInputSourceState(elements, wires, moduleElement.id, inputPort.id);

    if (i < inputElementIds.length) {
      const inputElement = subElements.find((el) => el.id === inputElementIds[i]);
      if (inputElement) {
        inputElement.state = inputState !== null ? inputState : false;
      }
    }
  }

  // 计算模块内部电路（支持递归嵌套模块）
  let changed = true;
  while (changed) {
    changed = false;

    for (const element of subElements) {
      if (element.type === 'INPUT') {
        continue;
      }

      let newState = element.state;

      if (element.type === 'AND') {
        let allTrue = true;
        let allConnected = true;
        for (const input of element.inputs) {
          if (hasInputConnection(subWires, element.id, input.id)) {
            const inputState = getInputSourceState(subElements, subWires, element.id, input.id);
            if (inputState !== true) {
              allTrue = false;
              break;
            }
          } else {
            allConnected = false;
            break;
          }
        }
        newState = allConnected && allTrue;
      } else if (element.type === 'OR') {
        let anyTrue = false;
        let hasInput = false;
        for (const input of element.inputs) {
          if (hasInputConnection(subWires, element.id, input.id)) {
            hasInput = true;
            const inputState = getInputSourceState(subElements, subWires, element.id, input.id);
            if (inputState === true) {
              anyTrue = true;
              break;
            }
          }
        }
        newState = hasInput ? anyTrue : false;
      } else if (element.type === 'NOT') {
        let inputTrue = false;
        let hasInput = false;
        for (const input of element.inputs) {
          if (hasInputConnection(subWires, element.id, input.id)) {
            hasInput = true;
            const inputState = getInputSourceState(subElements, subWires, element.id, input.id);
            if (inputState === true) {
              inputTrue = true;
              break;
            }
          }
        }
        newState = hasInput ? !inputTrue : false;
      } else if (element.type === 'OUTPUT') {
        let inputTrue = false;
        for (const input of element.inputs) {
          if (hasInputConnection(subWires, element.id, input.id)) {
            const inputState = getInputSourceState(subElements, subWires, element.id, input.id);
            if (inputState === true) {
              inputTrue = true;
              break;
            }
          }
        }
        newState = inputTrue;
      } else if (element.type === 'BYTE_INPUT') {
        // 字节输入器：将 byteValue 分解为 8 个输出位
        const portStates = [];
        const bv = element.byteValue || 0;
        for (let i = 0; i < 8; i++) {
          portStates.push((bv & (1 << i)) !== 0);
        }
        element.portStates = portStates;
        newState = false;
      } else if (element.type === 'BYTE_OUTPUT') {
        // 字节显示器：读取 8 个输入位合并为 byteValue
        const portStates = [];
        let byteVal = 0;
        for (let i = 0; i < element.inputs.length && i < 8; i++) {
          const input = element.inputs[i];
          let bitState = false;
          if (hasInputConnection(subWires, element.id, input.id)) {
            const s = getInputSourceState(subElements, subWires, element.id, input.id);
            bitState = s === true;
          }
          portStates.push(bitState);
          if (bitState) byteVal |= (1 << i);
        }
        element.byteValue = byteVal;
        element.portStates = portStates;
        newState = false;
      } else if (element.type === 'FUNCTION') {
        // 递归计算嵌套的模块元件
        const oldOutputStates = element.outputStates || [];
        const nestedOutputStates = calculateModuleElement(element, subElements, subWires, functionCache, depth + 1);
        newState = nestedOutputStates.length > 0 ? nestedOutputStates[0] : false;
        element.outputStates = nestedOutputStates;
        if (
          oldOutputStates.length !== nestedOutputStates.length ||
          oldOutputStates.some((v, i) => v !== nestedOutputStates[i])
        ) {
          changed = true;
        }
      }

      if (element.state !== newState) {
        element.state = newState;
        changed = true;
      }
    }
  }

  // 获取所有输出元件的状态
  const outputStates = outputElementIds.map((outputId) => {
    const outputElement = subElements.find((el) => el.id === outputId);
    return outputElement ? outputElement.state : false;
  });

  return outputStates;
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
      } else if (element.type === 'BYTE_INPUT') {
        // 字节输入器：将 byteValue 分解为 8 个输出位
        const portStates = [];
        const bv = element.byteValue || 0;
        for (let i = 0; i < 8; i++) {
          portStates.push((bv & (1 << i)) !== 0);
        }
        element.portStates = portStates;
        newState = false;
      } else if (element.type === 'BYTE_OUTPUT') {
        // 字节显示器：读取 8 个输入位合并为 byteValue
        const portStates = [];
        let byteVal = 0;
        for (let i = 0; i < element.inputs.length && i < 8; i++) {
          const input = element.inputs[i];
          let bitState = false;
          if (hasInputConnection(wires, element.id, input.id)) {
            const s = getInputSourceState(elements, wires, element.id, input.id);
            bitState = s === true;
          }
          portStates.push(bitState);
          if (bitState) byteVal |= (1 << i);
        }
        element.byteValue = byteVal;
        element.portStates = portStates;
        newState = false;
      } else if (element.type === 'FUNCTION') {
        // 模块元件：计算内部电路
        const oldOutputStates = element.outputStates || [];
        const outputStates = calculateModuleElement(element, elements, wires);
        newState = outputStates.length > 0 ? outputStates[0] : false;
        element.outputStates = outputStates;
        if (oldOutputStates.length !== outputStates.length || oldOutputStates.some((v, i) => v !== outputStates[i])) {
          changed = true;
        }
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
    const startElement = elements.find((e) => e.id === wire.start.elementId);
    if (startElement) {
      // 如果起点是输出端口，使用源元件的状态
      if (!wire.start.isInput) {
        if (startElement.type === 'FUNCTION') {
          // 模块元件需要根据输出端口索引获取状态
          const outputStates = startElement.outputStates || [];
          wireState =
            wire.start.portIndex !== undefined && wire.start.portIndex < outputStates.length
              ? outputStates[wire.start.portIndex]
              : outputStates[0] || false;
        } else if (startElement.type === 'BYTE_INPUT') {
          // BYTE_INPUT 元件根据 portStates 获取各输出端口状态
          const portStates = startElement.portStates || [];
          wireState =
            wire.start.portIndex !== undefined && wire.start.portIndex < portStates.length
              ? portStates[wire.start.portIndex]
              : false;
        } else {
          wireState = startElement.state;
        }
      }
    }

    // 查找连接到导线终点的元件
    const endElement = elements.find((e) => e.id === wire.end.elementId);
    if (endElement) {
      // 如果终点是输出端口，使用目标元件的状态
      if (!wire.end.isInput) {
        if (endElement.type === 'FUNCTION') {
          const outputStates = endElement.outputStates || [];
          wireState =
            wire.end.portIndex !== undefined && wire.end.portIndex < outputStates.length
              ? outputStates[wire.end.portIndex]
              : outputStates[0] || false;
        } else if (endElement.type === 'BYTE_INPUT') {
          const portStates = endElement.portStates || [];
          wireState =
            wire.end.portIndex !== undefined && wire.end.portIndex < portStates.length
              ? portStates[wire.end.portIndex]
              : false;
        } else {
          wireState = endElement.state;
        }
      }
    }

    wire.state = wireState;
  }

  return elements;
}
