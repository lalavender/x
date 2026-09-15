# 64 · libtcc API：把编译器当库用

> **一句话**：`libtcc.h` 只暴露约 20 个函数，就能在你自己的程序里
> 编译 C 字符串、加符号、链接、取出函数指针直接调用。
> 这就是 TCC 作为"嵌入式编译器"的接口。
>
> 对应源码：`src/core/libtcc.h`（API 声明，102 行）、
> `src/core/libtcc.c`（实现，含 `tcc_new`/`tcc_delete`/`tcc_compile_string`/`tcc_add_symbol`）。

---

## 第 0 站：API 全貌（`libtcc.h`）

```c
/* src/core/libtcc.h:12-96（分类整理） */

/* 生命周期 */
TCCState *tcc_new(void);                    /* 建一个编译会话 */
void tcc_delete(TCCState *s);               /* 销毁 */

/* 配置 */
void tcc_set_lib_path(TCCState *s, const char *path);
void tcc_set_error_func(TCCState *s, void *opaque, void (*)(...));
void tcc_set_options(TCCState *s, const char *str);     /* 等效命令行选项 */

/* 预处理 */
int  tcc_add_include_path(TCCState *s, const char *pathname);
int  tcc_add_sysinclude_path(TCCState *s, const char *pathname);
void tcc_define_symbol(TCCState *s, const char *sym, const char *value);
void tcc_undefine_symbol(TCCState *s, const char *sym);

/* 编译 */
int  tcc_add_file(TCCState *s, const char *filename);
int  tcc_compile_string(TCCState *s, const char *buf);   /* ★ 编译字符串 */

/* 链接 */
int  tcc_set_output_type(TCCState *s, int output_type);  /* 必须先调！ */
int  tcc_add_library_path(TCCState *s, const char *pathname);
int  tcc_add_library(TCCState *s, const char *libraryname);
int  tcc_add_symbol(TCCState *s, const char *name, const void *val);  /* ★ 注入符号 */

/* 输出/执行 */
int  tcc_output_file(TCCState *s, const char *filename); /* 写 ELF/PE */
int  tcc_run(TCCState *s, int argc, char **argv);        /* 内存执行 */
int  tcc_relocate(TCCState *s1, void *ptr);              /* 内存重定位 */

/* 取值 */
void *tcc_get_symbol(TCCState *s, const char *name);     /* ★ 取函数/变量地址 */
```

---

## 第 1 站：最小示例——编译字符串并调用

```c
#include <libtcc.h>
#include <stdio.h>

int main(void)
{
    TCCState *s = tcc_new();                      /* ① 建会话 */

    tcc_set_output_type(s, TCC_OUTPUT_MEMORY);    /* ② 内存输出 */
    tcc_compile_string(s,                         /* ③ 编译字符串 */
        "int add(int a, int b) { return a + b; }\n");

    tcc_relocate(s, TCC_RELOCATE_AUTO);           /* ④ 布局到内存 */

    int (*add)(int, int) = tcc_get_symbol(s, "add");   /* ⑤ 取函数指针 */
    printf("%d\n", add(3, 4));                    /* ⑥ 调用：7 */

    tcc_delete(s);                                /* ⑦ 销毁 */
    return 0;
}
```

编译这个程序：
```bash
cc mylibtcc.c -ltcc -o mylibtcc       # 需要 libtcc
```

**七步就是 libtcc 的全部套路。**

---

## 第 2 站：注入宿主程序的符号 —— `tcc_add_symbol`

被编译的代码可能想调用你程序里的函数。用 `tcc_add_symbol` 把地址告诉它：

```c
#include <libtcc.h>

int my_print(const char *s) { puts(s); return 0; }

int main(void) {
    TCCState *s = tcc_new();
    tcc_set_output_type(s, TCC_OUTPUT_MEMORY);

    /* ★ 把 my_print 注入进去，编译的代码就能调用它 */
    tcc_add_symbol(s, "host_print", my_print);

    tcc_compile_string(s,
        "int host_print(const char *);\n"
        "void hello(void) { host_print(\"hi from compiled code\"); }\n");

    tcc_relocate(s, TCC_RELOCATE_AUTO);
    void (*hello)(void) = tcc_get_symbol(s, "hello");
    hello();                         /* 输出 hi from compiled code */
    tcc_delete(s);
}
```

**这是插件系统/脚本引擎的常见模式**：宿主用 C 写好 API，用户传 C 源码，
运行时编译并调用。

---

## 第 3 站：常用配置

```c
TCCState *s = tcc_new();

/* 头文件搜索路径（等效 -I） */
tcc_add_include_path(s, "/usr/local/include");

/* 定义宏（等效 -D） */
tcc_define_symbol(s, "DEBUG", "1");
tcc_undefine_symbol(s, "NDEBUG");

/* 一次性设置多个选项（等效命令行） */
tcc_set_options(s, "-Wall -O2 -g");

/* 自定义错误输出（默认打 stderr） */
void on_err(void *opaque, const char *msg) { fprintf(logfile, "%s\n", msg); }
tcc_set_error_func(s, NULL, on_err);

/* 库搜索路径（等效 -L / -l） */
tcc_add_library_path(s, "/usr/lib");
tcc_add_library(s, "m");           /* 链接 libm */
```

`tcc_set_options` 传的是**命令行字符串**，内部调用和 `main` 一样的
`tcc_parse_args`，所以支持大部分 TCC 选项。

---

## 第 4 站：输出成文件（不做内存执行）

```c
TCCState *s = tcc_new();
tcc_set_output_type(s, TCC_OUTPUT_EXE);    /* 可执行文件 */
tcc_add_file(s, "prog.c");
tcc_output_file(s, "prog");                 /* 等价 tcc prog.c -o prog */
tcc_delete(s);
```

也可以 `TCC_OUTPUT_OBJ` / `TCC_OUTPUT_DLL`。

---

## 第 5 站：实现位置（想看源码时）

| API | 实现在 |
|---|---|
| `tcc_new` / `tcc_delete` | `libtcc.c:682` / `:853` |
| `tcc_set_options` | `libtcc.c`（内部调 `tcc_parse_args`） |
| `tcc_compile_string` | `libtcc.c`（造内存文件，调 `tcc_compile`） |
| `tcc_add_symbol` | `libtcc.c`（造 ELF 符号） |
| `tcc_output_file` | `tccelf.c:2233`（第 54 篇） |
| `tcc_relocate` / `tcc_run` | `tccrun.c:59/116`（第 62 篇） |
| `tcc_get_symbol` | `tccelf.c:475`（第 52 篇） |

**API 层很薄，主要工作都在前面各部讲过的核心函数里。**

---

## 第 6 站：可以用 libtcc 做什么

- **配置语言/脚本引擎**：把用户写的 C 片段编译进程序；
- **JIT 编译器**：运行时生成机器码并执行（`TCC_RELOCATE_AUTO` + 函数指针）；
- **教学工具**：演示编译过程；
- **插件加载器**：编译插件源码，用 `tcc_add_symbol` 提供宿主 API；
- **快速原型**：改代码后立刻 `-run`，省去编译链接等待。

---

## 【完整可编译的示例】

```c
/* demo.c —— 用 libtcc 做一个 C 表达式求值器 */
#include <libtcc.h>
#include <stdio.h>

int main(int argc, char **argv) {
    if (argc < 2) return 1;

    TCCState *s = tcc_new();
    tcc_set_output_type(s, TCC_OUTPUT_MEMORY);

    /* 把命令行表达式包成函数 */
    char src[1024];
    snprintf(src, sizeof(src), "int eval(void){ return %s; }", argv[1]);

    if (tcc_compile_string(s, src) < 0) return 2;
    if (tcc_relocate(s, TCC_RELOCATE_AUTO) < 0) return 3;

    int (*eval)(void) = tcc_get_symbol(s, "eval");
    printf("%d\n", eval());

    tcc_delete(s);
    return 0;
}
```

```bash
./demo '2*3+4'    # 输出 10
```

---

## 【动手小实验】

1. 把上面的 demo 编译运行，试几个表达式。
2. 用 `tcc_add_symbol` 注入一个 `host_rand()`，让编译的代码调用它。
3. 用 `tcc_set_error_func` 把错误写到文件。
4. 用 `tcc_output_file` 把编译的代码写成 `.o`，再用 `nm` 看符号。

## 【通关暗号】

```bash
cat > /tmp/lt.c <<'EOF'
#include <tcc/libtcc.h>
#include <stdio.h>
int main(void){
  TCCState *s=tcc_new();
  tcc_set_output_type(s,TCC_OUTPUT_MEMORY);
  tcc_compile_string(s,"int ans(void){return 7*6;}");
  tcc_relocate(s,TCC_RELOCATE_AUTO);
  int(*ans)(void)=tcc_get_symbol(s,"ans");
  printf("%d\n",ans());
  tcc_delete(s);
  return 0;
}
EOF
cc /tmp/lt.c -ltcc -o /tmp/lt 2>/dev/null && /tmp/lt
# 期望：42（如果系统装了 libtcc）
```

## 【常见卡点】

- **必须先 `tcc_set_output_type` 再编译**（头文件里注明 MUST）。
- **`tcc_compile_string` 编译字符串；`tcc_add_file` 编译文件**。
- **`tcc_add_symbol` 注入宿主符号**。
- **`tcc_relocate` + `tcc_get_symbol` 才能拿函数指针**。
- **API 层很薄，核心逻辑在 `libtcc.c`/`tccelf.c`/`tccrun.c`**。

---

## 【第十部小结】

| 篇 | 主题 |
|---|---|
| 62 | `tcc -run` 与内存管理 |
| 63 | 崩溃回溯 |
| 64 | libtcc API |

**下一步（第十一部）**：其它后端（ARM/ARM64/IL/C67）与内置汇编器。

**下一篇**：`65-ARM与ARM64后端.md`。
