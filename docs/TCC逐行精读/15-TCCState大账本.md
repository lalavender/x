# 15 · TCCState：整台编译器的大账本

> **一句话**：前五篇的"零件"（`TokenSym`/`Sym`/`Section`/值栈/符号栈）不散落各处，
> 它们要么挂在全局变量上，要么挂在**一个 `TCCState`** 结构上。
> `TCCState` 就是"一次编译会话"的全部状态。
>
> 对应源码：`src/core/tcc.h:640`（结构，约 180 行）、
> `src/core/libtcc.c:682`（`tcc_new` 建账本）、`src/core/libtcc.c:669`（`tcc_cleanup` 销账本）、
> `src/core/tcc.h:1087`（全局 `tcc_state`）。

---

## 第 0 站：为什么要有这个结构

TCC 可以**同时/反复**编译多个文件、甚至被当作库嵌进别的程序（libtcc）。
如果所有状态都用全局变量，第二次编译就会污染第一次。
所以 TCC 把"一次编译会变化的东西"收进 `TCCState`：

- 选项（`verbose`、`static_link`、`warn_*`…）；
- 所有 `Section`（第 14 篇）；
- include 栈、`#if` 栈（第 08 篇）；
- 符号表、错误跳转点、输出类型……
- 命令行收集的文件列表。

而 `TokenSym` 表、符号池、宏栈等**在单次编译内是全局的**，就放在 `tccpp.c`/`tccgen.c` 的全局变量里。
**分工：会话级状态进 `TCCState`；编译过程级状态用全局变量。**

---

## 第 1 站：账本的主要栏目（`tcc.h:640`）

### 1a. 选项（`:642-704`）

```c
/* src/core/tcc.h:642-704（节选）*/
    int verbose;          /* -v：打印过程信息 */
    int nostdinc;         /* -nostdinc */
    int nostdlib;         /* -nostdlib */
    int nocommon;         /* 不用 common 符号 */
    int static_link;      /* 静态链接 */
    int rdynamic;         /* 导出所有符号 */
    ...
    int output_type;      /* ★ 输出什么：内存/可执行/目标/预处理 */
    int output_format;    /* ELF/PE/COFF */
    int char_is_unsigned; /* char 是否有符号 */
    int do_debug;         /* -g */
    ...
    char *tcc_lib_path;   /* 库/头文件目录 */
```

`output_type` 的取值（`tcc.h` 里 `TCC_OUTPUT_*`）决定最后走哪条出口：

| 值 | 含义 |
|---|---|
| `TCC_OUTPUT_MEMORY` | `-run`：编完直接在内存里跑 |
| `TCC_OUTPUT_EXE` | 可执行文件 |
| `TCC_OUTPUT_DLL` | 动态库 |
| `TCC_OUTPUT_OBJ` | 目标文件 `.o` |
| `TCC_OUTPUT_PREPROCESS` | `-E`：只预处理 |

### 1b. 搜索路径（`:706-723`）

```c
    char **include_paths;    int nb_include_paths;
    char **sysinclude_paths; int nb_sysinclude_paths;
    char **library_paths;    int nb_library_paths;
    char **crt_paths;        int nb_crt_paths;
    char **cmd_include_files; int nb_cmd_include_files;  /* -include */
```

全是"动态数组 + 个数"的配对。`dynarray_add` 负责追加。

### 1c. 错误处理（`:725-730`）

```c
    void (*error_func)(void *opaque, const char *msg);
    jmp_buf error_jmp_buf;   /* ★ setjmp 的跳转点 */
    int nb_errors;
```

`error_jmp_buf` 就是第 01 篇说的"按电梯回大厅"。
`tcc_compile` 里 `setjmp(s1->error_jmp_buf)`，任何 `tcc_error` 都 `longjmp` 回这里。
`error_func` 让嵌入 libtcc 的程序能自定义"错误往哪报"。

### 1d. 编译过程状态（`:746-767`）

```c
    BufferedFile *include_stack[INCLUDE_STACK_SIZE];
    BufferedFile **include_stack_ptr;      /* #include 栈 */

    int ifdef_stack[IFDEF_STACK_SIZE];
    int *ifdef_stack_ptr;                  /* #if 开关栈 */

    int cached_includes_hash[CACHED_INCLUDES_HASH_SIZE];
    CachedInclude **cached_includes;       /* 头文件保护缓存 */

    int pack_stack[PACK_STACK_SIZE];       /* #pragma pack */

    struct InlineFunc **inline_fns;        /* 待编译的 inline 函数 */
    int nb_inline_fns;
```

**注意 `include_stack` 和 `ifdef_stack` 是定长数组**（32 和 64），
指针 `*_ptr` 指向栈顶。第 08 篇用的就是这个。

### 1e. 纸带与符号表（`:769-788`）

```c
    Section **sections;       int nb_sections;        /* 所有节 */
    Section **priv_sections;  int nb_priv_sections;   /* 私有节 */
    Section *got;  Section *plt;                      /* GOT/PLT（第 61 篇） */
    Section *dynsymtab_section;
    Section *dynsym;
    Section *symtab;                                  /* 全局符号表 */
    struct sym_attr *sym_attrs; int nb_sym_attrs;     /* 符号附加属性 */
```

### 1f. 命令行收集（`:810-822`）

```c
    struct filespec **files;   int nb_files;   int nb_libraries;
    int filetype;
    char *outfile;
    int option_r, do_bench, gen_deps, option_pthread;
    int argc; char **argv;
```

这些只在 `main`/`tcc_parse_args` 里用，编译核心不碰。

---

## 第 2 站：建账本 —— `tcc_new`（`libtcc.c:682`）

```c
/* src/core/libtcc.c:682-722（节选）*/
LIBTCCAPI TCCState *tcc_new(void) {
  TCCState *s;

  tcc_cleanup();                 /* 先清掉上一次的全局状态 */

  s = tcc_mallocz(sizeof(TCCState));   /* ★ 分配并清零 */
  if (!s) return NULL;
  tcc_state = s;                 /* ★ 挂到全局 tcc_state */
  ++nb_states;

  s->alacarte_link = 1;
  s->nocommon = 1;
  s->warn_implicit_function_declaration = 1;
  s->ms_extensions = 1;
  ...
  tcc_set_lib_path(s, CONFIG_TCCDIR);

  tccelf_new(s);                 /* ★ 造标准纸带（第 14 篇） */
  tccpp_new(s);                  /* ★ 造 TokenSym 表、关键字表（第 03 篇） */

  /* 内置宏的占位符（让 defined() 能用） */
  define_push(TOK___LINE__, MACRO_OBJ, NULL, NULL);
  define_push(TOK___FILE__, MACRO_OBJ, NULL, NULL);
  define_push(TOK___DATE__, MACRO_OBJ, NULL, NULL);
  define_push(TOK___TIME__, MACRO_OBJ, NULL, NULL);
  define_push(TOK___COUNTER__, MACRO_OBJ, NULL, NULL);
  {
    /* __TINYC__ = 版本号 */
    char buffer[32];
    int a, b, c;
    sscanf(TCC_VERSION, "%d.%d.%d", &a, &b, &c);
    sprintf(buffer, "%d", a * 10000 + b * 100 + c);
    tcc_define_symbol(s, "__TINYC__", buffer);
  }

  /* 标准宏 */
  tcc_define_symbol(s, "__STDC__", NULL);
  tcc_define_symbol(s, "__STDC_VERSION__", "199901L");
  tcc_define_symbol(s, "__STDC_HOSTED__", NULL);

  /* 目标平台宏 */
#if defined(TCC_TARGET_X86_64)
  tcc_define_symbol(s, "__x86_64__", NULL);
#elif defined(TCC_TARGET_I386)
  tcc_define_symbol(s, "__i386__", NULL);
  ...
#endif
  ...
}
```

建账本的顺序很重要：

1. **`tcc_cleanup()`**：保证没有上一次的残留（因为很多状态是全局的）。
2. **`tcc_mallocz` + `tcc_state = s`**：账本分配、清零、挂到全局。
3. **`tccelf_new`**：造出 `.text`/`.data`/`.bss`/`.symtab` 等纸带。
4. **`tccpp_new`**：造 `TokenSym` 哈希表、分配器、登记关键字。
5. **`define_push` 一批内置宏**：`__LINE__`、`__FILE__`…

**注意：`__TINYC__`、`__STDC__`、`__x86_64__` 都是"内置 #define"**，
内容就是普通的宏字符串（第 06 篇）。所以 `#ifdef __x86_64__` 能工作，
并不是词法器特判，而是 `tcc_new` 早就 `#define` 好了。

---

## 第 3 站：销账本 —— `tcc_cleanup`（`libtcc.c:669`）

```c
/* src/core/libtcc.c:668-680 */
static void tcc_cleanup(void) {
  if (NULL == tcc_state)
    return;
  while (file)                 /* 关掉所有还没关的文件 */
    tcc_close();
  tccpp_delete(tcc_state);     /* 释放 TokenSym 表、分配器（第 03 篇） */
  tcc_state = NULL;
  /* 释放符号池 */
  dynarray_reset(&sym_pools, &nb_sym_pools);
  sym_free_first = NULL;
}
```

**它清理的是"全局状态"**（`file`、`TokenSym` 表、符号池），
`TCCState` 自己的内存由 `tcc_delete`（`libtcc.c:853`）释放。
所以 `tcc_new` 一进来先 `tcc_cleanup`，把上一局的残留清干净。

---

## 第 4 站：`main` 怎么用它（串起第 01 篇）

回到 `tcc.c` 的 `main`（第 01 篇讲过骨架）：

```c
/* src/core/tcc.c 附近 */
  s = tcc_new();                       /* 建账本 */
  opt = tcc_parse_args(s, &argc, &argv, 1);  /* 解析命令行，写进账本 */
  set_environment(s);                  /* 读环境变量，补搜索路径 */
  if (s->output_type == 0)
    s->output_type = TCC_OUTPUT_EXE;   /* 默认输出可执行文件 */
  tcc_set_output_type(s, s->output_type);

  for (...) {
    tcc_add_file(s, f->name);          /* 每个输入文件喂一次 */
  }

  if (s->output_type == TCC_OUTPUT_MEMORY)
      tcc_run(s, argc, argv);          /* -run：内存执行 */
  else
      tcc_output_file(s, s->outfile);  /* 否则写文件 */
```

**`s` 从建账本到编译到输出，一路传下去。** 这就是为什么几乎每个核心函数
要么以 `TCCState *s1` 为参数，要么通过全局 `tcc_state` 拿到它。

---

## 【六个零件在大账本里的位置】

```
TCCState s
 ├─ s->sections[] ──► Section(.text/.data/.bss/.symtab...)   ← 第14篇
 ├─ s->symtab     ──► 符号表 Section
 ├─ s->include_stack[] ──► BufferedFile* 数组                ← 第01篇
 ├─ s->ifdef_stack[]  ──► int 数组                            ← 第08篇
 ├─ s->error_jmp_buf  ──► setjmp 跳转点                      ← 第01篇
 └─ 全局 tcc_state ──► 就是它

全局（不在账本里，但单次编译内有效）：
 ├─ hash_ident[] / table_ident ──► TokenSym                  ← 第03、10篇
 ├─ file / ch / tok / tokc      ──► 当前输入                  ← 第01、02篇
 ├─ global_stack / local_stack / define_stack ──► Sym 栈      ← 第10、13篇
 ├─ __vstack[] / vtop            ──► 值栈                     ← 第12篇
 └─ sections 的全局别名 text_section/data_section/...         ← 第14篇
```

---

## 【动手小实验】

1. 在 `tcc_new` 末尾加 `printf("sections=%d\n", s->nb_sections);`，
   看标准纸带造了几条。
2. 编译 `-nostdinc` 的程序，看 `s->nostdinc` 怎么影响 include 搜索（第 08 篇）。
3. 用 libtcc 写个小程序调 `tcc_new()`/`tcc_delete()` 两次，体会"会话"的概念。

## 【通关暗号】

```bash
./tcc -v -c /tmp/g.c -o /tmp/g.o 2>&1 | head -5
# 期望：能打印出过程信息（verbose 选项生效，说明账本读到位了）
```

## 【常见卡点】

- **不是所有状态都在 `TCCState`**：单次编译内的全局状态（TokenSym 表、值栈、符号栈）不在。
- **`tcc_new` 先 `tcc_cleanup`**：因为全局状态必须干净才能开始新一局。
- **内置宏就是普通 `#define`**：`__STDC__` 等不是硬编码特判。
- **`output_type` 决定出口**：第 01 篇的"分发"就靠它。

---

## 【第二部小结】

| 篇 | 零件 | 一句话 |
|---|---|---|
| 10 | `TokenSym` | 一个名字，四个抽屉 |
| 11 | `CType` | 一个 int 装下所有类型，套娃 |
| 12 | `SValue` | 值栈上的便利贴，TCC 的中间表示 |
| 13 | `Sym` | 三条链织出作用域/成员/同名历史 |
| 14 | `Section` | 会生长的纸带，所有输出都写它 |
| 15 | `TCCState` | 大账本，一次编译的全部状态 |

**下一步（第三部）**：进入 `tccgen.c` 的心脏——`unary()`、值栈、`gv()`、`gen_op()`，
看便利贴怎么变成机器码。
