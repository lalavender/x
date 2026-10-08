# yh-link 独立项目 TC1–TC3 交付（ELF 对象出口贯通）

日期：2026-10-03。状态：**TC1 + TC2 整数子集 + TC3 ELF 对象出口完成并验收**。

按用户决定，工具链在仓库根 `link/` 作为**独立项目**开发（`link/project.toml`，
`name = "yh_link"`），模块划分与实施方案的 `compiler/obj|asm|link` 一一对应。
设计契约见 [yh-link 独立项目与首版汇编子集契约](../03-design/yh-link独立项目与首版汇编子集契约.md)，
项目说明见 [link/README.md](../../link/README.md)。

## 交付内容

### TC1 obj 模块

- `10_bytes.yh`：带容量检查的 `Buf`、NUL 分隔名称池 `Names`、小端读写、
  `itoa`/`hex64`、`align_up`/`mul_chk`/`add_chk`。
- `20_model.yh`：`TargetSpec`、`Section`（PROGBITS/NOBITS，文件尺寸与内存
  尺寸分离）、`Symbol`、`Reloc`、`Ctx`，以及全部 `ctx_*`/`sec_*` 接口与诊断。
- `40_elf.yh` + `41_elf_emit.yh`（TC3）：节布局、符号编号（local 在前）、
  `$x`/`$d` 映射符号、重定位表、ELF64 头与节头写出。

### TC2 asm 模块

- 扫描器 `20_scan.yh`：记号表、行列号、`//` 与 `/* */` 注释、`0x` 十六进制、
  `.L1` 这类点号开头的词法、`%`/`@`/`:` 记号。
- 编码器 `31/32/33_enc_*.yh`：加减（立即/寄存器/扩展）、逻辑（立即/寄存器）、
  位域、乘除、访存全形态（含 `ldur/stur` 与前后索引写回）、分支、`adr/adrp`。
- 解析器 `40/51/52/53_parse_*.yh`：表达式、寄存器、各指令族、伪指令、语句循环。
- `60_assemble.yh`：局部位域回填 + 重定位白名单映射。

## 本记录新增的能力（相对 TC1–TC2 竖切片）

1. **ELF 对象出口贯通**：`yh_link asm -o out.o in.s` 产出结构完整的
   `ET_REL` 对象，`llvm-readobj`/`obj2yaml` 均可正常解析。
2. **访存 `lo12` 重定位补全**：按访问宽度映射到
   `LDST8/16/32/64_ABS_LO12_NC`(278/284/285/286)，imm12 存「字节偏移 ÷ 宽度」；
   同节目标汇编期直接回填。
3. **重定位类型号纠正**：契约原记录的 `ADD_ABS_LO12_NC=258`、`CONDBR19=305`、
   `TSTBR14=307` 三处有误，实测应为 `277`/`280`/`280`（`cbz/cbnz` 用 CONDBR19）。
   契约 §6 已同步。
4. **SP 参与 64 位加减改用扩展寄存器形式**：`sub sp, sp, x9` 这类指令的
   移位寄存器形式里编号 31 是 `xzr`，原实现会编成 `sub xzr, xzr, x9`。
   现在按操作数是否写成 `sp` 选择 UXTX 扩展形式。
5. **`adrp` 回填保留操作码**：原掩码 `0x1f00001f` 丢掉 bit31，页寻址回填后
   `adrp` 退化成 `adr`。
6. **`uxtw x, w` 规范编码**：改用 `UBFM Xd, Xn, #0, #31`，与 llvm-mc 一致。
7. **点号开头的符号一律局部**：前向引用 `.L1` 时原先被登记成全局符号，
   跨目标文件会互相冲突。
8. **代码节对齐填充用 NOP**：`.balign`/`.p2align` 落在 `.text` 时填
   `0xd503201f`，原先填 `0x1f` 字节会得到不可执行内容。
9. **`hs`/`lo` 条件码别名**。
10. **`memcpy` 返回值误用修正**：`memcpy` 返回目的地址（非 0），
    不能当成功码判断，原先导致 `.rela.<sec>` 节名退化成 `.text`。

## 验证

参照物是系统 LLVM 的独立汇编器 `/opt/homebrew/opt/llvm/bin/llvm-mc`。

| 门 | 命令 | 结果 |
| --- | --- | --- |
| 构建 | `cd link && ../yh run` | 通过 |
| 三层自检 | `./.build/yh_link` | 退出码 0（编码器 107 + 公共层 36 + 端到端 15） |
| 编码器向量 | `python3 tests/check_enc.py` | 107 条，不一致 0 |
| 全量语料 | `python3 tests/check_corpus.py` | 61 个文件：汇编成功 44，**逐字节不一致 0**，跳过 17 |
| 定向语料 | `python3 tests/check_corpus.py tests/asm` | 5 个文件，不一致 0 |
| 结构与确定性 | `python3 tests/check_obj.py ./.build/yh_link ../tmp/inv` | 44 个对象，结构问题 0，非确定 0 |

语料是 `tests/yh-run/` 下 61 个 `.yh` 用例经 `yh --emit-asm` 的真实后端输出。

比对方法：`llvm-mc` 参照对象先做一遍「本地重定位回填」，把两边统一成链接后
的形态，再逐字节比 `.text`/`.data`；指向外部符号的重定位两边都必须逐条相同
（偏移、类型、目标）。局部目标两边写法不同（本工具用「具名局部符号 + 0 addend」，
llvm-mc 用「节符号 + addend」），按「(节, 节内偏移)」归一化后比较。

自检具备变异测试证据：把 `adrp` 掩码改回错误值，自检返回 19；
把访存 `lo12` 的 addend 用法改回错误值，自检返回 21。

## 未覆盖（不阻塞 TC1–TC3 验收）

- **浮点标量**：10 个语料文件（`fadd/fmul/fmov/scvtf/fcvtzs/fcvt/fcmp`）。
- **GOT 重定位**：7 个语料文件（`@GOTPAGE`/`@GOTPAGEOFF`）。
- 静态链接与可执行映像（TC4）、Mach-O 出口（TC8）。

两者都已在 `link/README.md` 与 `docs/todo.md` 登记。

## 与既有 `asm/` 项目的关系

仓库根的 `asm/` 是上一轮 TC1–TC2 竖切片的独立项目（无 ELF 出口）。
本轮按用户要求改为在 `link/` 立项并推进到 TC3，`asm/` 未改动、未删除，
两者不互相依赖。后续接入主编译器时以 `link/` 为准。

> 后续：2026-10-07 目录整理按职责归位——本文这套**汇编器**实现从 `link/`
> 整体迁到 `asm/` 项目（`asm/README.md`、`asm/tests/`），`link/` 清空为
> **链接器**项目并保留入口骨架；两者互不依赖，只通过标准对象文件交接。
> 见 [归位记录](yh汇编器与链接器项目归位-2026-10-07.md)。
