# libc 标准库：C ABI 兼容的 yh 实现

日期：2026-10-23。状态：**L1 纯 yh 子集已实现**（memory/string/整数转换，
Linux/AArch64 与 Darwin/ARM64 同一份源码）。分配器、stdio、errno/TLS 与
动态链接分别属于 L1.4–L5，见
[分阶段候选方案](../../docs/02-plan/yh-libc分阶段候选方案.md)。

- 完整 API 清单与契约：[doc.yh](doc.yh)
- OS 原语：[os](../os/README.md)、[sys](../sys/README.md)

## 加载

```sh
# 与其它标准库模块一致：显式依赖、YH_STDLIB 或默认发现
# project.toml:
#   [dependencies]
#   yh_libs = { path = "../libs" }
# main.yh:
#   import yh_libs.libc as libc;
```

```yh
import libc;

pub fn main() int {
    if (libc.strcmp("abc", "abd") >= 0) {
        return 1;
    }
    let copy [8]u8;
    libc.strcpy((&copy[0]).to_type(*char), "ok");
    return libc.atoi(" 42");
}
```

## C ABI 与 C 调用方

每个导出函数都带 `@[extern]`，所以对象里就是标准 C 符号（Mach-O 为
`_strcmp` 等，ELF 为 `strcmp`），参数/返回值按 LP64 的 C 原型：

| C 原型 | yh 签名 |
| --- | --- |
| `void *memmove(void *, const void *, size_t)` | `*void, *void, u64 -> *void` |
| `int strcmp(const char *, const char *)` | `*char, *char -> int` |
| `size_t strnlen(const char *, size_t)` | `*char, u64 -> u64` |

实现只用循环和指针，不调用 yh 运行时，模块对象没有未定义符号。当前编译器
还没有静态归档导出（L0.2），要交给 C 调用方时直接使用构建产物里的模块对象：

```sh
YH_STDLIB=$PWD/libs ./yh build              # 在任意导入 libc 的项目里
# 产物：.build/targets/<triple>/llvm/<opt>/obj/yh_libs-libc.o
cc -o ctest ctest.c .build/targets/aarch64-apple-darwin/llvm/O0/obj/yh_libs-libc.o
```

本机验证就是这样做的：C 调用方覆盖重叠 memmove、零填充 strncpy、
NUL 匹配 strchr、空 needle strstr 与 atoi 饱和，全部通过。

## 自带验收

```sh
python3 libs/libc/test/run.py            # yh 侧断言 + C ABI 调用方
python3 libs/libc/test/run.py --quiet    # 只打印失败与汇总
```

runner 在工作目录构建 `libs/libc/test/main.yh`，再取模块对象链接
`libs/libc/test/ctest.c` 并运行；两段都通过才返回 0。

## 已实现

```text
libs/libc/
  memory.yh   memmove/memset/memcmp/memchr
  string.yh   strcmp/strncmp/strcpy/strncpy/strcat/strncat/
                 strchr/strrchr/strstr/strnlen/strspn/strcspn/strpbrk/
                 strcasecmp/strncasecmp/strlcpy/strlcat
  convert.yh  atoi/atol/atoll/strtol/strtoul/abs/labs/llabs
  sort.yh     qsort/bsearch（C ABI 比较回调）
  doc.yh      仅注释的完整 API 参考
```

## 未实现与硬边界

- `memcpy`、`strlen`、`malloc`、`free`、`printf`、`exit`、`open/read/
  write/close` 等：名字由编译器 prelude 登记（yh 运行时里有弱定义），
  模块内再声明会报“顶层符号重定义”；编译器目前也没有符号别名/重命名
  属性。要在 yh 里重写这些入口，需要先加 C 符号别名或把这些名字从
  prelude 解耦（编译器改动）。
- `errno`、`strerror`：errno 需要每线程存储（L3 的 TLS），L1 不伪造
  全局 errno，因此不提供（`strtol` 已提供，但溢出只饱和、不报 ERANGE）。
- `FILE*`/stdio、`setjmp`、pthread、动态链接：分别属于 L2–L5，且部分依赖
  编译器能力（裸变参调用、TLS、非局部跳转）。
- 语义取舍：`atoi`/`atol`/`strtol` 溢出饱和到 i32/i64 两端（C 标准此处
  未定义，且要求设 errno(ERANGE)），不设置 errno；`strncpy`/`strncat` 的
  NUL 行为按 C 标准实现并已在 doc.yh 注明。
- `qsort`/`bsearch` 的比较函数必须是 `@[extern]` 定义的 C ABI 函数：编译器
  拒绝把普通 yh 函数当作 C 回调实参；当前后端也不支持函数指针与 0 比较，
  所以库里不做空回调检查（C 标准同样要求合法回调）。
- 大整数字面量必须先落进带类型的变量再参与表达式：直接写
  `0 - 9223372036854775807 - 1` 会被当成 i32 静默截断成 0（本轮实现
  `strtol` 时踩过），这是语言层面的既有行为，不是 libc 契约。
