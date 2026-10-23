# yh-link Mach-O 出口与编译器汇编步替换（2026-10-04）

> 后续：2026-10-07 工具链按职责归位后，本文描述的汇编器实现源码路径
> 从 `link/src/...` 变为 `asm/src/...`，验收门从 `link/tests/...` 变为
> `asm/tests/...`；`link/` 改为链接器项目。见
> [归位记录](yh汇编器与链接器项目归位-2026-10-07.md)。

## 结论

编译器**逐模块汇编步**（`clang -c`）已由 `yh_link asm -t darwin` 顶替，
`make selfhost-native` 全绿（退出 0，零失败），期间 `yh_link` 被真实调用
**106 次**。最终链接步（`clang -o`）仍在用系统链接器——替换它需要 Mach-O
可执行文件链接器，属 TC8–TC10，未做。

## 为什么必须走 Mach-O

宿主是 macOS arm64，编译器实际发射的也是 Darwin 方言（`@PAGE`/`@PAGEOFF`、
`_` 前缀符号）。要把 `link/` 接进 yh 工具链，产出必须是 Mach-O 可重定位
对象，而不是 ELF。ELF 侧此前只用于容器里的差分验证。

## 做了什么

### 1. Mach-O arm64 `MH_OBJECT` 写出器

新文件 `link/src/obj/50_macho.yh`（常量与重定位映射）、
`link/src/obj/51_macho_emit.yh`（布局与写出）。入口
`obj.macho_write(c, out)`，由 `yh_link asm -t darwin` 触发。

映射表全部**实测自 clang**，不是查手册抄的：

| 汇编层类别 | Mach-O 类型 | pcrel | length |
|---|---|---|---|
| ABS64 (257) | UNSIGNED (0) | 0 | 3 |
| ADR_PREL_PG_HI21 (275) | PAGE21 (3) | 1 | 2 |
| ADD_ABS_LO12_NC (277) | PAGEOFF12 (4) | 0 | 2 |
| LDST8/16/32/64 (278/284/285/286) | PAGEOFF12 (4) | 0 | 2 |
| JUMP26 (282) / CALL26 (283) | BRANCH26 (2) | 1 | 2 |
| LD64_GOTPAGE_LO21 (311) | GOT_LOAD_PAGE21 (5) | 1 | 2 |
| LD64_GOT_LO12_NC (312) | GOT_LOAD_PAGEOFF12 (6) | 0 | 2 |
| CONDBR19 (280) | 无对应类型 → 报错 | | |

要点：

- **PAGEOFF12 的 length 一律 2**。Mach-O 的 length 表示「立即数字段占几字节」，
  与访问宽度无关，所以 `ldr x`/`ldr w`/`ldrb w` 加 `add` 四种形态同值，
  不需要像 ELF 的 LDST* 那样按 1/2/4/8 字节分派。
- **Mach-O 对象只有一个无名段**（segname 全 0），全部节挂在它下面，节的
  segname 记录链接时要去哪个段。这跟可执行文件里的 `__TEXT`/`__DATA` 段
  是两回事。
- 节映射：`.text`→`__TEXT,__text`（flags 0x80000400）、`.rodata`→
  `__TEXT,__const`、`.data`→`__DATA,__data`、`.bss`→`__DATA,__bss`（ZEROFILL）。
- `Section.align` 在上下文里是**字节**对齐，Mach-O 的 `section_64.align`
  存的是 **2 的幂次数**，写出时用 `mo_log2` 换算。节大小也不能读 `memsz`
  （PROGBITS 节不维护 memsz），要读 `data.len`。
- 符号表按 `local → 已定义 global → 未定义 global` 排（`LC_DYSYMTAB` 的
  三个区间靠顺序表达），重定位按节分组、**节内按地址降序**。
- 条件分支在 Mach-O 里只能跳本节局部标签，clang 直接报
  `conditional branch requires assembler-local label`；`yh_link -t darwin`
  同样在写出阶段拒绝，不产出非法对象。

### 2. 补 `ucvtf`

替换编译器工具链暴露出的唯一子集缺口：编译器发射浮点窄化时用 `ucvtf`
（无符号），而 `link/` 只实现了 `scvtf`。机器码只差 bit16
（`0x1e220000` → `0x1e230000`）。新增 `e_ucvtf` 与 5 条编码器向量，
定向语料 `tests/asm/09-ucvtf.s`。

### 3. 编译器接入

`compiler/cmd/link_cache.yh` 的 `mb_asm_tool` 按顺序找自研汇编器：

1. 环境变量 `YH_LINK`（显式指定，优先级最高）；
2. `PATH` 上的 `yh_link`；
3. 编译器可执行文件同目录下的 `yh_link`；
4. 都找不到才回落 `clang`（Darwin）/ `gcc`（Linux）。

找到就用 `yh_link asm -t darwin -o obj src`，没找到维持原样。命令前缀进了
对象缓存键，换工具链必然换键，不会拿 cc 产出的旧对象当命中。

仓库侧加了 `make yh-link`：用刚构建出的 `yh` 冷编 `link/`，把产物拷到
仓库根的 `yh_link`（macOS 上 codesign）。`yh` 与 `yh_link` 同目录即自动
生效，无需任何配置。

`tests/selfhost/link-cache.py` 改成与汇编器无关：wrapper 同时覆盖 `gcc`、
`clang` 和 `yh_link`（`$1 = asm` 也算 assemble），计数按 assemble/link
两类统计。门要验的是**缓存边界**，不是用哪个汇编器。

## 验证

| 门 | 结果 |
|---|---|
| `yh_link` 自检 | 退出 0 |
| `tests/check_enc.py` | 134 条，不一致 0 |
| `tests/check_corpus.py ../tmp/inv`（ELF） | 61 个，不一致 0，跳过 0 |
| `tests/check_corpus.py tests/asm`（ELF） | 9 个，不一致 0，跳过 0 |
| `tests/macho_corpus_check.py`（对 clang 差分） | 70 个，一致 69，跳过 1，不一致 0 |
| `tests/macho_link_run.py ../tmp/inv` | 61 个，一致 61，不一致 0，跳过 0 |
| 两代固定点（都用 yh_link 汇编） | `.s` 与 `.s.i` 逐字节相同 |
| `make selfhost-native` | 退出 0，零失败，yh_link 调用 106 次 |

`macho_link_run.py` 是最强的一道：我们的对象经 `ld -lSystem` 链成可执行文件
后，与 clang 对象链出来的**运行行为和输出**逐个一致。Mach-O 对象不可能与
clang 逐字节相同（符号与节排序不同），所以语义差分比的是节集合与大小、
符号及其**节内偏移**、每节的重定位三元组。

跳过的 1 个是 `tests/asm/03-mem-reloc.s`——它用 `beq _g` 跳外部符号，
Mach-O 表达不了。ELF 侧继续覆盖它。

## 踩到的两个坑

**同节分支在 Mach-O 里不发重定位，但汇编期必须回填偏移。** 链接跑飞、
结构却全对，就栽在这：Mach-O 的 BRANCH26 只用于外部与跨节符号，同节分支
（哪怕目标是 **global**）汇编期就定死；我们原先照 ELF 的规则留了重定位、
没回填立即数，指令字节是 0。修法是让 `asm_assemble` 的「同节可定死」判定
按目标格式分派：ELF 仍要求 local，Mach-O 只要求符号在本节有定义。这条与
`mo_reloc_kept` 共用 `obj.mo_sym_in_sec`，两处必须同时成立，否则会再次出现
「不发重定位也没回填」。

**`ptr + i` 不是本项目用的指针算术。** 结构体数组上应写 `&arr[i]`；写成
`c.secs + i` 会拿到错的东西，表现为部分符号被判成「所在节不参与输出」或
段错误。同理符号表必须按 `symmap` 编号写，不能按上下文下标写。

## 顺带发现的编译器问题（未修）

1. **`pub const` 的整数字面量按 32 位有符号折叠。** `0xfeedfacf` 折成
   `-17958193`，再赋给 `u32` 报「字面量超出目标类型可表示范围」；
   `0x80000000` 折成一个空的负号直接失败。函数体里的字面量不受影响，所以
   `link/` 里头魔数和节属性标志写成了 `mo_magic()` / `mo_attr_pure_instructions()`
   两个函数（带 `ponytail:` 注释说明）。上游修掉折叠宽度后可以改回 const。
2. **上一代种子编译器编不了 `link/`。** `bin/yh` 在含 `e`/`E` 的十六进制
   字面量上会命中浮点指数的解析路径，报「浮点与整数之间需要 .to_type」。
   `link/` 用到了新语言特性，本来也只能用 `$(YH)` 冷编，所以没当成缺口
   处理；`make yh-link` 显式依赖 `$(YH)`。

## 没做什么

- **最终链接步**仍是 `clang -o`。替换它要 Mach-O 可执行文件链接器：分段
  布局、符号解析、stub 与惰性绑定、`LC_DYLD_CHAINED_FIXUPS`、以及 arm64
  macOS 强制的 ad-hoc 代码签名。这是 TC8–TC10。
- **静态 ELF 链接器**（TC4）仍未做。
- 容器差分门（`elf_link_check.py`）本轮未动。