# 12 · SValue 与值栈：TCC 的"中间表示"就是一张便利贴

> **一句话**：TCC 没有语法树，它的"中间表示"是一个**值栈**。
> 每读到一个值，就在栈顶贴一张便利贴 `SValue`：
> "我是什么类型、我现在住在哪、我的值是多少"。
>
> 对应源码：`src/core/tcc.h:424`（结构）、`src/core/tccgen.c:50`（值栈本体）、
> `src/core/tccgen.c:630`（`vsetc` 贴便利贴）、`src/core/tccgen.c:678`（`vpop` 撕便利贴）、
> `src/core/tccgen.c:663`（`vswap`）、`src/core/tccgen.c:758-797`（`vdup`/`vrotb`/`vrott`/`vrote`）。

---

## 第 0 站：便利贴长什么样（`tcc.h:424`）

```c
/* src/core/tcc.h:423-432 */
typedef struct SValue {
    CType type;           /* 类型（第 11 篇） */
    unsigned short r;     /* ★ 我现在住在哪 + 标志位 */
    unsigned short r2;    /* 64 位值住两个寄存器时的第二个；否则 VT_CONST */
    CValue c;             /* 常量值，或栈帧偏移 */
    struct Sym *sym;      /* 牵扯的符号（欠条） */
} SValue;
```

`r` 是灵魂。它低 6 位是"住址"，高位是标志。

---

## 第 1 站：`r` 的住址（`tcc.h:832-838`）

```c
/* src/core/tcc.h:832-838 */
#define VT_VALMASK   0x003f  /* 低 6 位：住址 */
#define VT_CONST     0x0030  /* 我是常量，值在 c 里 */
#define VT_LLOCAL    0x0031  /* 我是左值，地址在栈上 */
#define VT_LOCAL     0x0032  /* 我在栈帧的 c 偏移处 */
#define VT_CMP       0x0033  /* 我的值在 CPU 标志位里 */
#define VT_JMP       0x0034  /* 我是一段跳转链（真） */
#define VT_JMPI      0x0035  /* 我是一段跳转链（假） */
```

`0` 到 `0x2f` 是**寄存器号**（比如 `rax`、`rbx`）。所以：

| `r & VT_VALMASK` | 人话 |
|---|---|
| `0..0x2f` | "我住在某个寄存器里" |
| `VT_CONST (0x30)` | "我是个常量，值在 `c` 里" |
| `VT_LOCAL (0x32)` | "我在栈帧 `c` 偏移处"（局部变量） |
| `VT_CMP (0x33)` | "我刚比较完，结果在 CPU 标志位，还没落地" |
| `VT_JMP/VT_JMPI (0x34/0x35)` | "我是一串待回填的跳转"（`&&`/`\|\|` 用） |

### 标志位（`tcc.h:839-850`）

```c
#define VT_LVAL      0x0100  /* 这张便利贴代表"一个位置"：读它要取货，写它要放货 */
#define VT_SYM       0x0200  /* 贴了一张欠条 sym（地址还没定） */
#define VT_MUSTCAST  0x0400  /* 必须转换后才能用（char/short 塞在 32 位里） */
#define VT_MUSTBOUND 0x0800  /* 使用前必须做边界检查 */
#define VT_BOUNDED   0x8000  /* 已经检查过了 */
#define VT_LVAL_BYTE     0x1000
#define VT_LVAL_SHORT    0x2000
#define VT_LVAL_UNSIGNED 0x4000
```

其中 `VT_LVAL` 最重要：**它区分"值"和"位置"**。

- `x` 这个变量：`r = VT_LOCAL | VT_LVAL`，`c = -8` → "我在 `rbp-8`，我是个位置"。
- 常量 `3`：`r = VT_CONST`，`c.i = 3` → "我就是 3"。

---

## 第 2 站：值栈本体（`tccgen.c:50`）

```c
/* src/core/tccgen.c:50 */
ST_DATA SValue __vstack[1+VSTACK_SIZE], *vtop, *pvtop;
```

- `__vstack` 是一个固定大小数组（`VSTACK_SIZE = 256`，`tcc.h:371`）。
- `vtop` 是**栈顶指针**，指向"当前最上面那张便利贴"。
- 栈是**向上生长**的：`vtop[0]` 是栈顶，`vtop[-1]` 是它下面那张。

`pvtop` 是"进入某个函数时的栈顶"，用于检查栈是否泄漏：

```c
/* src/core/tccgen.c:131-135 */
ST_FUNC void check_vstack(void)
{
    if (pvtop != vtop)
        tcc_error("internal compiler error: vstack leak (%d)", vtop - pvtop);
}
```

**如果真的忘了 `vpop`，TCC 会自己报"栈泄漏"——这是编译器开发者的安全带。**

---

## 第 3 站：贴一张便利贴 —— `vsetc`（`tccgen.c:630`）

```c
/* src/core/tccgen.c:630-661 */
static void vsetc(CType *type, int r, CValue *vc)
{
    int v;

    if (vtop >= vstack + (VSTACK_SIZE - 1))
        tcc_error("memory full (vstack)");

    /* 栈顶如果是"CPU 标志位/跳转链"，先物化成寄存器 */
    if (vtop >= vstack && !nocode_wanted) {
        v = vtop->r & VT_VALMASK;
        if (v == VT_CMP || (v & ~1) == VT_JMP)
            gv(RC_INT);
    }

    vtop++;                  /* ★ 栈顶升高一格 */
    vtop->type = *type;      /* 写类型 */
    vtop->r = r;             /* 写住址 */
    vtop->r2 = VT_CONST;     /* 默认没有第二寄存器 */
    vtop->c = *vc;           /* 写值 */
    vtop->sym = NULL;        /* 默认没有欠条 */
}
```

**为什么开头要"物化"？** 因为 `VT_CMP`/`VT_JMP` 的值只存在于"处理器状态"里，
如果栈顶又压了新值，那条跳转链的位置就乱了。所以压栈前先把它们变成真寄存器。
（`gv(RC_INT)` 是第 21 篇的主角。）

贴便利贴的几种快捷方式：

```c
/* src/core/tccgen.c:695-756（节选）*/
ST_FUNC void vpush(CType *type)          /* 压一个"空值"占位 */
{ vset(type, VT_CONST, 0); }

ST_FUNC void vpushi(int v)               /* 压整数常量 */
{ CValue cval; cval.i = v; vsetc(&int_type, VT_CONST, &cval); }

ST_FUNC void vset(CType *type, int r, int v)
{ CValue cval; cval.i = v; vsetc(type, r, &cval); }

ST_FUNC void vpushv(SValue *v)           /* 复制一张现成的便利贴 */
{ ... vtop++; *vtop = *v; }

static void vdup(void) { vpushv(vtop); } /* 复制栈顶 */
```

---

## 第 4 站：撕一张 —— `vpop`（`tccgen.c:678`）

```c
/* src/core/tccgen.c:677-693 */
/* 弹出栈顶值 */
ST_FUNC void vpop(void)
{
    int v;
    v = vtop->r & VT_VALMASK;
#if defined(TCC_TARGET_I386) || defined(TCC_TARGET_X86_64)
    /* x86 需要弹掉浮点栈 */
    if (v == TREG_ST0) {
        o(0xd8dd); /* fstp %st(0) */
    } else
#endif
    if (v == VT_JMP || v == VT_JMPI) {
        /* && 或 || 没测试就弹出：把跳转补上 */
        gsym(vtop->c.i);
    }
    vtop--;                    /* ★ 栈顶降一格 */
}
```

两个副作用：

1. 浮点栈寄存器要发一条 `fstp`（x86 历史问题）；
2. `VT_JMP` 弹出时，说明 `&&`/`||` 的跳转链还没回填，调用 `gsym` 补上。

**`vpop` 不只是"指针减一"，它还负责收拾资源。** 这是值栈设计的隐含约定。

---

## 第 5 站：换位置 —— `vswap` / `vrotb` / `vrott`（`tccgen.c:663-797`）

有时候栈顶两张便利贴的顺序不对，要交换或旋转：

```c
/* src/core/tccgen.c:663-675 */
ST_FUNC void vswap(void)
{
    SValue tmp;
    if (vtop >= vstack && !nocode_wanted) {   /* 同样先物化 CMP/JMP */
        int v = vtop->r & VT_VALMASK;
        if (v == VT_CMP || (v & ~1) == VT_JMP)
            gv(RC_INT);
    }
    tmp = vtop[0];
    vtop[0] = vtop[-1];
    vtop[-1] = tmp;
}
```

```c
/* src/core/tccgen.c:763-797 */
/* 把最上面 n 张转到底部： I1...In -> I2...In I1 [栈顶在右] */
ST_FUNC void vrotb(int n)
{
    int i;
    SValue tmp;
    tmp = vtop[-n + 1];
    for(i=-n+1;i!=0;i++)
        vtop[i] = vtop[i+1];
    vtop[0] = tmp;
}

/* 把 e 前面的 n 张往栈顶方向转： I1...In... -> In I1...I(n-1)... */
ST_FUNC void vrote(SValue *e, int n)
{
    int i;
    SValue tmp;
    tmp = *e;
    for(i = 0;i < n - 1; i++)
        e[-i] = e[-i - 1];
    e[-n + 1] = tmp;
}

/* 把最上面 n 张转到顶部： I1...In -> In I1...I(n-1) */
ST_FUNC void vrott(int n) { vrote(vtop, n); }
```

这些旋转用在**赋值、条件、函数调用参数**等"顺序要调整"的地方。
比如 C 的赋值 `a = b`：先算 `a`（左值）再算 `b`，但生成代码时希望
"值在寄存器、地址在栈上"按某种顺序——旋转就够了。

> 注意：旋转**不产生机器码**，只是把便利贴挪位置。
> **真正生成代码的是后面的 `gv`/`gen_op`/`load`。** 值栈操作是纯数据搬运。

---

## 第 6 站：为什么值栈能替代语法树

教科书编译器：

```
表达式 → 语法树（节点 = 运算，子节点 = 操作数）→ 遍历树 → 机器码
```

TCC：

```
表达式 → 边读边把值压栈 → 遇到运算符就"归约栈顶两项" → 机器码
```

**"归约栈顶两项"就是树的后序遍历！** 只是 TCC 不显式建树，
而用值栈的顺序天然表达了树的结构：

- `a + b * c` 读进栈：先 `a`；读 `b*c` 时 `b`、`c` 相继入栈，
  遇 `*` 归约成一项；最后遇 `+` 归约 `a` 和 `b*c`。
- 每个"归约"就是"弹两张、发一条指令、压一张结果"。

这就是第 3 部要展开的心脏。**记住：值栈 = 不用建树的中间表示。**

---

## 【把 `2 + 3 * 4` 的便利贴走一遍】

| 动作 | 值栈（栈顶在右） | 说明 |
|---|---|---|
| 读 `2` | `[2]` | `vpushi(2)` |
| 读 `3` | `[2, 3]` | `vpushi(3)` |
| 读 `4` | `[2, 3, 4]` | `vpushi(4)` |
| 遇 `*` | `[2, 12]` | 弹 3、4，常量折叠成 12 |
| 遇 `+` | `[14]` | 弹 2、12，折叠成 14 |
| 结束 | `[]` | 结果在栈顶被取走 |

**全程没有任何机器码**（都是常量折叠），值栈只是记录了"算到哪了"。

---

## 【动手小实验】

1. 在 `vsetc` 和 `vpop` 里各加一行 `printf("vstack depth=%d\n", (int)(vtop-vstack));`，
   编译一个表达式稍复杂的程序，观察深度变化。
2. 搜 `vrotb`/`vrott`/`vswap`，看它们分别在哪些语法场景被调用。
3. 看 `check_vstack` 被谁调用（一般在函数结束时），理解为什么需要它。

## 【通关暗号】

```bash
printf 'int main(void){return 2+3*4;}\n' > /tmp/v.c
./tcc -run /tmp/v.c; echo $?
# 期望：14（值栈按优先级正确归约）
```

## 【常见卡点】

- **`vtop[0]` 是栈顶，`vtop[-1]` 是下面一张**，不是反过来。
- **`r` 低 6 位住址、高位标志**：判断"住哪"先 `& VT_VALMASK`。
- **`VT_LVAL` 区分值/位置**：写它要 `store`，读它要 `load`（第 21、24 篇）。
- **值栈操作不发机器码**：它只是挪便利贴。

**下一篇**：`13-Sym的三条链.md` —— 一个 `Sym` 用三条链织出作用域和结构体。
