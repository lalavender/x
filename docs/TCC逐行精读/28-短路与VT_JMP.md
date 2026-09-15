# 28 · 短路 `&&` `||` 与 `VT_JMP`：跳转链也是一种值

> **一句话**：`&&`、`||` 的结果不是算出来的，而是"一段跳转"。
> TCC 把这段跳转链当成一张便利贴压到值栈上；
> 真正要用这个布尔值时（赋值、return），才把跳转链"物化"成 0/1。
>
> 对应源码：`src/core/tccgen.c:5382`（`expr_land`）、`:5423`（`expr_lor`）、
> `:1605`（`gvtst`）、`src/core/tccgen.c:649`（`vsetc` 里的物化）、
> `src/targets/x86_64-gen.c:1716`（`gtst` 的 `VT_JMP` 分支）。

---

## 第 0 站：先看"真值"怎么表示

C 里任何值都能当条件：非 0 为真。TCC 的办法是**统一转成"和 0 比较"**：

```c
/* src/core/tccgen.c:1605-1611 */
ST_FUNC int gvtst(int inv, int t)
{
    int v = vtop->r & VT_VALMASK;
    if (v != VT_CMP && v != VT_JMP && v != VT_JMPI) {
        vpushi(0);
        gen_op(TOK_NE);      /* 值 != 0 → 变成 VT_CMP（结果在标志位） */
    }
    ...
}
```

做完 `gen_op(TOK_NE)` 后，栈顶是一张 `VT_CMP` 便利贴：
"我的真假在 CPU 标志位里，还没落地成 0/1"。

---

## 第 1 站：`&&` 的生成（`tccgen.c:5382`）

```c
/* src/core/tccgen.c:5382-5420（重贴，逐行）*/
static void expr_land(void)
{
    expr_or();                    /* 先算左边 */
    if (tok == TOK_LAND) {        /* 看到 && */
        int t = 0;
        for(;;) {
            if (左边是常量) {
                gen_cast_s(VT_BOOL);
                if (vtop->c.i) {
                    vpop();       /* 常量真：&& 只看右边 */
                } else {
                    nocode_wanted++;                  /* 常量假：右边全不生成 */
                    while (tok == TOK_LAND) { next(); expr_or(); vpop(); }
                    nocode_wanted--;
                    if (t) gsym(t);
                    gen_cast_s(VT_INT);
                    break;
                }
            } else {
                if (!t) save_regs(1);                 /* 第一次：保存寄存器 */
                t = gvtst(1, t);  /* ★ 左边假 → 追加到跳转链 t */
            }
            if (tok != TOK_LAND) {
                if (t)
                    vseti(VT_JMPI, t);   /* ★ 把跳转链压成一张"值"便利贴 */
                else
                    vpushi(1);
                break;
            }
            next();
            expr_or();            /* 算右边 */
        }
    }
}
```

关键理解：

1. 逐项算 `a && b && c`；
2. 每算出一项，如果它非假就要继续算下一项，所以要生成"**这一项为假就跳到最终为假的地方**"：
   `t = gvtst(1, t)`，把新跳转追加到链 `t`。
3. 全算完后，**把链 `t` 压成一张便利贴**：
   ```c
   vseti(VT_JMPI, t);
   ```
   `VT_JMPI`（`tcc.h:838`）意思是"我是一段跳转链，链上每条都在'某个操作数为假'时跳走"。
   **链的地址存在 `vtop->c.i` 里。**

所以 `a && b` 的"值"就是一段跳转链。**跳转链 ≠ 0/1，它是一种"待物化的布尔值"。**

`||` 是对偶的（`tccgen.c:5423`）：`t = gvtst(0, t)`（某项为**真**就跳走），
最后压 `vseti(VT_JMP, t)`。

---

## 第 2 站：`VT_JMP` vs `VT_JMPI`

`tcc.h:837-838`：

```c
#define VT_JMP       0x0034  /* 真时跳（偶数） */
#define VT_JMPI      0x0035  /* 假时跳（奇数） */
```

注意它们是**相邻的**，只差最低位。所以后端可以：

```c
/* src/targets/x86_64-gen.c:1716-1730 */
    } else if (v == VT_JMP || v == VT_JMPI) {
        if ((v & 1) == inv) {
            /* 把 vtop 的跳转链插进已有链 t */
            uint32_t n1, n = vtop->c.i;
            if (n) {
                while ((n1 = read32le(cur_text_section->data + n)))
                    n = n1;
                write32le(cur_text_section->data + n, t);
                t = vtop->c.i;
            }
        } else {
            /* 方向相反：新生成一条跳转，回填已有的链 */
            t = gjmp(t);
            gsym(vtop->c.i);
        }
    }
```

**`(v & 1) == inv` 用最低位判断方向**，一次比较搞定，不用两个分支写两遍。
`VT_JMP`（偶，0x34）和 `VT_JMPI`（奇，0x35）就差这一位。

---

## 第 3 站：什么时候要"物化"成 0/1

跳转链是"半成品"。一旦你要把它当普通值用（`int x = a && b;`、`return a||b;`、
`(a&&b) + 1`），就必须变成真寄存器里的 0/1。

第 21 篇的 `gv` 和 `vsetc` 会处理：**只要栈顶是 `VT_JMP` 且下面还要压新值，
就先物化**：

```c
/* src/core/tccgen.c:649-653（vsetc 里）*/
    if (vtop >= vstack && !nocode_wanted) {
        v = vtop->r & VT_VALMASK;
        if (v == VT_CMP || (v & ~1) == VT_JMP)
            gv(RC_INT);      /* ★ 把 CMP/JMP 变成寄存器里的 0/1 */
    }
```

`gv(RC_INT)` 遇到 `VT_JMP` 时，最终会调后端的 `gtst`/`load`：
把"跳转链"变成"跳到某处取 0，否则取 1"。这套逻辑在 `gvtst`/`gtst` +
`load` 里完成。

> **`(v & ~1) == VT_JMP`**：清掉最低位后等于 `VT_JMP`，也就是
> `VT_JMP(0x34)` 和 `VT_JMPI(0x35)` 都命中。又一处巧用相邻编号。

---

## 第 4 站：`&&`/`||` 套 `&&`/`||` 时链会合并

`a && b || c` 的解析：

- 先 `expr_lor` → `expr_land` 处理 `a && b`，得到一条 `VT_JMPI` 便利贴（链 `t1`）；
- 回到 `expr_lor`，看到 `||`，调 `gvtst(0, t1)`：
  它发现栈顶已经是 `VT_JMP`，于是**直接操作这条链**（`gtst` 的 `VT_JMP` 分支）；
- 结果链把"`a&&b` 为假"和"`c` 为真"合并。

**链在栈上传递、在后端合并**——不需要重新遍历。

---

## 第 5 站：`nocode_wanted` —— 常量短路

```c
/* src/core/tccgen.c:5393-5403（&& 的常量假分支）*/
                    nocode_wanted++;
                    while (tok == TOK_LAND) {
                        next();
                        expr_or();     /* 照常解析 */
                        vpop();        /* 但生成代码被禁止（nocode_wanted>0） */
                    }
                    nocode_wanted--;
```

`0 && f()` 里 `f()` 的**解析照做**（要检查语法），但**不生成机器码**。
`nocode_wanted` 就是这个开关。`vstore`、`gv` 等很多函数开头都会检查它。

---

## 【把 `if (a && b) x=1;` 走一遍】

| 步骤 | 动作 | 代码 |
|---|---|---|
| 1 | `gexpr` 求 `a&&b` | |
| 2 | `a` 入栈，`gvtst(1,0)` | `test a; je L_false`（链 `t`） |
| 3 | `b` 入栈，`gvtst(1,t)` | `test b; je L_false`（并入链） |
| 4 | `vseti(VT_JMPI, t)` | 栈顶是"链 t"便利贴 |
| 5 | `if` 的 `gvtst(1,0)` | 发现栈顶是 JMP → 直接用这条链 → `je L_else` |
| 6 | then 分支 | `x=1` |
| 7 | `gsym` | 回填 `L_else`/结尾 |

**注意第 4、5 步**：`if` 不需要"先把 `a&&b` 变成 0/1 再比较"，
它直接复用已有的跳转链。**这就是 `VT_JMP` 存在的意义：省掉一次往返。**

---

## 【动手小实验】

1. 写 `int x = a && b;`，反汇编看是否真的把结果物化成 0/1（有 `setne` 之类）。
2. 写 `if (a && b) {...}`，反汇编看是否没有 0/1 中间值（直接条件跳转）。
3. 写 `if (0 && f()) {...}`，看 `f` 是否完全没生成。
4. 在 `vseti(VT_JMPI, t)` 那行加 `printf("chain head=%d\n", t);` 观察链头变化。

## 【通关暗号】

```bash
printf 'int main(void){int a=1,b=0; return (a&&b) || a;}\n' > /tmp/l.c
./tcc -run /tmp/l.c; echo $?
# 期望：1（(1&&0)||1 = 1）
```

## 【常见卡点】

- **`&&`/`||` 的结果是"跳转链"，不是 0/1**。
- **`VT_JMP`/`VT_JMPI` 只差最低位**，后端用 `(v&1)` 判断方向。
- **压新值/赋值时 `VT_JMP` 会被 `gv` 物化**成寄存器里的 0/1。
- **`nocode_wanted` 让常量短路分支不生成代码**（但仍解析）。

**下一篇**：`29-switch与gcase.md`。
