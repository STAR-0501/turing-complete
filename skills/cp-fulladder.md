---
id: cp-fulladder
name: Full Adder Circuit Pattern
description: 全加器 — 三个输入（A, B, CarryIn）相加，输出 SUM 与 CARRY
tags: [circuit, pattern, full-adder]
---

### CP-FullAdder
- **用途**: 全加器 — 三个输入（A, B, CarryIn）相加，输出 SUM 与 CARRY
- **输入**: A, B, CarryIn
- **输出**: SUM, CARRY
- **实现**: 2×HalfAdder + 1×OR（自动检测到 HalfAdder 后会一并注册）
- **构建命令** (~15 条):
  ```
  ADD XOR 240 60 fa_xor1
  ADD AND 240 140 fa_and1
  WIRE $input1 0 fa_xor1 0
  WIRE $input2 0 fa_xor1 1
  WIRE $input1 0 fa_and1 0
  WIRE $input2 0 fa_and1 1
  ADD XOR 400 60 fa_xor2
  ADD AND 400 140 fa_and2
  WIRE fa_xor1 0 fa_xor2 0
  WIRE $input3 0 fa_xor2 1
  WIRE fa_xor1 0 fa_and2 0
  WIRE $input3 0 fa_and2 1
  ADD OR 560 140 fa_or
  WIRE fa_and1 0 fa_or 0
  WIRE fa_and2 0 fa_or 1
  DEFINE_MODULE FullAdder
  ```
- **验证** (8 用例):
  ```
  000→SUM=0,CARRY=0  001→SUM=1,CARRY=0  010→SUM=1,CARRY=0  011→SUM=0,CARRY=1
  100→SUM=1,CARRY=0  101→SUM=0,CARRY=1  110→SUM=0,CARRY=1  111→SUM=1,CARRY=1
  ```
- **复用**: 注册后可用 `ADD MODULE <x> <y> <alias> FullAdder`
