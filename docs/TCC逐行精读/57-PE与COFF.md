# 57 · PE / COFF：Windows 输出（选读）

> **一句话**：TCC 在 Windows 上输出 PE 格式（`.exe`/`.dll`），在部分平台还能读
> COFF 目标文件。这套代码和 ELF 那套**并列**：同样的 `Section` 体系，
> 换成 PE 的节头/导入表/导出表写法。
>
> 对应源码：`src/formats/tccpe.c`（1947 行，`pe_output_file` `:1941`）、
> `src/formats/tcccoff.c`（948 行，读 COFF）、`src/formats/coff.h`、
> `src/core/tccelf.c:2236`（`tcc_output_file` 里的分派）。另见 PE 专属代码散布在
> `tcc.h`（`TCC_TARGET_PE` 条件编译）和 `x86_64-gen.c`。

---

## 第 0 站：哪里分叉

```c
/* src/core/tccelf.c:2233-2243（重贴）*/
LIBTCCAPI int tcc_output_file(TCCState *s, const char *filename)
{
    int ret;
#ifdef TCC_TARGET_PE
    if (s->output_type != TCC_OUTPUT_OBJ) {
        ret = pe_output_file(s, filename);    /* Windows：PE */
    } else
#endif
        ret = elf_output_file(s, filename);   /* 其它：ELF */
    return ret;
}
```

**同一个 `TCCState`、同一套 `Section`，只是最后打包规则不同。**

---

## 第 1 站：编译期就已经分叉的地方

`TCC_TARGET_PE` 在源码里出现很多次。关键差异：

| 主题 | ELF（Linux/mac） | PE（Windows） |
|---|---|---|
| 传参寄存器 | `rdi/rsi/rdx/rcx/r8/r9` | `rcx/rdx/r8/r9`（前 4 个） |
| 浮点寄存器 | `xmm0..7` | 对应整数寄存器位置 |
| 调用约定 | 统一 SysV | `cdecl`/`stdcall`，符号有 `@N` 后缀 |
| 全局变量访问 | GOT（PIE） | 直接重定位 |
| `long double` | 16 字节 x87 | 等同 `double` |
| 符号前缀 | 无 | 可选前导下划线 |
| 动态加载 | `.interp` + `.dynamic` | 导入表（Import Table） |

**同一份 `TCCState`/`tccgen.c`，靠 `#ifdef` 适配。**

---

## 第 2 站：`pe_output_file`（`tccpe.c:1941`）

和 `elf_output_file` 结构类似但细节不同：

```
PE 文件
  ├─ DOS 头 + PE 签名
  ├─ COFF 文件头
  ├─ Optional Header（入口、镜像基址、节表…）
  ├─ 节表 + 节内容（.text/.data/.rdata/.bss/.idata…）
  ├─ 导入表（Import Table）：依赖哪些 DLL、哪些函数
  ├─ 导出表（Export Table）：DLL 导出哪些符号
  └─ 重定位表（Relocation Table）
```

`tccpe.c` 里几个关键点：

- **导入表**：把 `printf`、`malloc` 等映射到 `msvcrt.dll`/`kernel32.dll`；
  对应 `#ifdef TCC_TARGET_PE` 分支里的 `pe_getimport`、`ST_PE_IMPORT` 等。
- **导出表**：DLL 的 `__declspec(dllexport)`。
- **`.def` 文件**：TCC 支持通过 `.def` 指定导出/导入（`tcc_load_ldscript` 的 PE 版本）。

---

## 第 3 站：符号名字的特殊处理

Windows 上有些历史包袱：

```c
/* src/core/tccgen.c:392-407（重贴）*/
#ifdef TCC_TARGET_PE
        if (sym_type == STT_FUNC && sym->type.ref) {
            Sym *ref = sym->type.ref;
            if (ref->f.func_call == FUNC_STDCALL && can_add_underscore) {
                sprintf(buf1, "_%s@%d", name, ref->f.func_args * PTR_SIZE);
                name = buf1;                 /* __stdcall: _foo@8 */
                other |= ST_PE_STDCALL;
                can_add_underscore = 0;
            }
        }
#endif
        if (tcc_state->leading_underscore && can_add_underscore) {
            buf1[0] = '_';
            pstrcpy(buf1 + 1, ..., name);
            name = buf1;                     /* 32 位 Windows：_foo */
        }
```

`__stdcall` 的函数名会变成 `_foo@8`（8 = 参数总字节）。这是 32 位 Windows 的 ABI。
64 位 Windows 只有一种调用约定，简单些。

---

## 第 4 站：COFF 读取（`tcccoff.c`）

`tcccoff.c` 让 TCC 能读 **MSVC 产出的 COFF `.obj`**（`cl /c` 的输出），
把它们合并进 TCC 的节体系。它不是默认编译进来的（需要 `--with-coff` 之类配置）。

---

## 第 5 站：跨平台时要注意什么

如果你在 macOS/Linux 上用 TCC 交叉编译 Windows 程序（`tcc -target` 等）：

- 头文件要用 Windows 的头；
- 库要用 Windows 的 `.lib`（或 TCC 自带的 `libtcc1` PE 版）；
- 输出是 PE，不能在 macOS/Linux 直接运行。

**TCC 的交叉编译能力有限**（不如 GCC 完整），但能编译简单程序。

---

## 【动手小实验】

1. 如果你有 Windows 环境：`tcc hello.c -o hello.exe`，用 `dumpbin /headers hello.exe`
   看 PE 结构。
2. 交叉编译：`tcc -target` 的选项见 `tcc.1` 或 `tcc -h`。
3. 搜 `TCC_TARGET_PE`，统计它在仓库里出现多少次（体会平台适配的分散性）。
4. 读 `tccpe.c` 的 `pe_output_file`，和 `elf_output_file` 对比结构。

## 【通关暗号】

```bash
# 在 Linux/mac 上，只能验证"PE 代码存在且被条件编译排除"
grep -c 'TCC_TARGET_PE' /Users/lavender/Documents/x/src/core/tcc.h
# 期望：一个正数（说明平台分叉是编译期条件，不影响本地构建）
```

## 【常见卡点】

- **PE/ELF 并列**，共用 `Section` 和前端，只是打包不同。
- **传参/调用约定/符号修饰**在 Windows 上不同。
- **导入表/导出表**对应 Windows 的动态链接。
- **COFF 读取是可选功能**。

---

## 【第八部小结】

| 篇 | 主题 |
|---|---|
| 51 | 纸带管理与节 |
| 52 | 符号表 |
| 53 | 重定位 |
| 54 | 写出 ELF 文件 |
| 55 | 内存重定位与 `-run` |
| 56 | 读 `.o`/`.a`/`.so` |
| 57 | PE/COFF（选读） |

**下一步（第九部）**：链接器——符号解析、公共符号、段合并、GOT/PLT。

**下一篇**：`58-链接总流程.md`。
