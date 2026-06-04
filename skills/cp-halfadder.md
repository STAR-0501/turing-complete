---
id: cp-halfadder
name: Half Adder Circuit Pattern
description: 半加器 — 两个输入位相加，输出 SUM（和）与 CARRY（进位）
tags: [circuit, pattern, half-adder]
---

### CP-HalfAdder
- **用途**: 半加器 — 两个输入位相加，输出 SUM（和）与 CARRY（进位）
- **输入**: A, B
- **输出**: SUM, CARRY
- **实现**: 1×XOR + 1×AND
- **构建命令** (~6 条):
  ```
  ADD XOR 240 60 ha_xor
  ADD AND 240 140 ha_and
  WIRE $input1 0 ha_xor 0
  WIRE $input2 0 ha_xor 1
  WIRE $input1 0 ha_and 0
  WIRE $input2 0 ha_and 1
  DEFINE_MODULE HalfAdder
  ```
- **验证** (4 用例):
  ```
  00→SUM=0,CARRY=0  01→SUM=1,CARRY=0  10→SUM=1,CARRY=0  11→SUM=0,CARRY=1
  ```
- **复用**: 注册后可用 `ADD MODULE <x> <y> <alias> HalfAdder`
