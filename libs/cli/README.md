# yh cli 标准库

`libs/cli/` 提供接近 Python argparse 能力的命令行解析：声明参数、解析成带标签的
结果命名空间、用类型化查询取值。设计见
[cli 设计](../../docs/03-design/yh-cli标准库设计.md)，与 argparse 的差异见
[对照说明](../../docs/03-design/yh-cli与argparse差异.md)，
分期与门禁见[实施方案](../../docs/02-plan/yh-cli标准库实施方案.md)。

本文的使用说明全部按本目录的验收项目实跑过（语义断言在
`libs/cli/zz_tests_*.yh`，真实 argv/退出码在 `libs/cli/test/`），片段可直接编译。

## 目录

- [1. 快速开始](#1-快速开始)
- [2. 一次解析的五个步骤](#2-一次解析的五个步骤)
- [3. 选项](#3-选项)
- [4. 布尔与计数](#4-布尔与计数)
- [5. 多值与列表](#5-多值与列表)
- [6. 位置参数](#6-位置参数)
- [7. 子命令与继承](#7-子命令与继承)
- [8. 展示组与互斥组](#8-展示组与互斥组)
- [9. 解析模式与初始命名空间](#9-解析模式与初始命名空间)
- [10. 自定义类型与校验](#10-自定义类型与校验)
- [11. 自定义 action](#11-自定义-action)
- [12. 参数文件](#12-参数文件)
- [13. 帮助与输出](#13-帮助与输出)
- [14. 退出码与错误处理](#14-退出码与错误处理)
- [15. 生命周期与所有权](#15-生命周期与所有权)
- [16. 常见陷阱](#16-常见陷阱)
- [文件划分](#文件划分)
- [公开 API](#公开-api)
- [契约要点](#契约要点)
- [容量上限（本版本）](#容量上限本版本)
- [未实现与已知边界](#未实现与已知边界)
- [验收](#验收)

## 1. 快速开始

`libs/` 是普通项目，通过标准库根加载。构建与运行：

```sh
# 仓库内：把 libs 作为标准库根
YH_STDLIB=/path/to/yh/libs ./yh build     # 在项目目录里构建
YH_STDLIB=/path/to/yh/libs ./yh run       # 构建并运行 main
```

也可以在自己的 `project.toml` 里依赖 `libs`，这样不必每次设环境变量。

最小可运行程序（`src/main/main.yh`）：

```yh
module main;

import cli;

// main 解析 `pack input.bin -vv -o out.bin` 形式的命令行。
fn main(argc int, argv **char) int {
    let parser cli.Parser;                            // 零值句柄，可安全 destroy
    let config cli.ParserConfig = cli.parser_config("pack");
    config.description = "打包指定输入文件";
    if (cli.init(&parser, config) != 0) {
        return 1;
    }

    let output cli.Argument = cli.option("--output", "-o");
    output.help = "输出文件路径";
    output.metavar = "PATH";
    output.default_value = cli.default_of(cli.value_text("bundle.bin"));
    cli.add_argument(&parser, output);

    let verbose cli.Argument = cli.option("--verbose", "-v");
    verbose.action = cli.count;                       // 可重复，累加整数
    verbose.help = "增加详细等级，可重复";
    cli.add_argument(&parser, verbose);

    let source cli.Argument = cli.positional("source");
    source.help = "输入文件路径";
    cli.add_argument(&parser, source);

    // 失败与帮助路径会在这里输出并结束进程，成功才返回。
    let result cli.Result = cli.parse_main_or_exit(&parser, argc, argv);

    let path *char;
    let input *char;
    let level i64;
    if (cli.get_text(&result.values, "output", &path) != 0
        || cli.get_text(&result.values, "source", &input) != 0) {
        cli.release(&result);
        cli.destroy(&parser);
        return 1;
    }
    if (cli.get_i64(&result.values, "verbose", &level) != 0) {
        level = 0;                                    // count 缺席时缺省 none
    }
    printf("output=%s source=%s verbose=%d\n", path, input, level);

    cli.release(&result);
    cli.destroy(&parser);
    return 0;
}
```

实跑：

```text
$ pack input.bin -vv -o out.bin
output=out.bin source=input.bin verbose=2

$ pack --help                # 退出码 0，帮助写到 stdout
usage: pack [-h] [--output PATH] [--verbose] source
...

$ pack                       # 退出码 2，诊断与 usage 写到 stderr
pack: 错误: 缺少必需的位置参数
usage: pack [-h] [--output PATH] [--verbose] source
```

## 2. 一次解析的五个步骤

1. **初始化**：`cli.init(&parser, config)`。`parser_config(prog)` 给出推荐默认值；
   零值 `Parser` 才能 init，失败返回 -1，之后仍可 `destroy`。
2. **声明**：`cli.option(name, alias)` / `cli.positional(name)` 返回 `Argument`
   （值语义），按需改字段后用 `cli.add_argument(&parser, spec)` 注册；
   返回正数参数 ID，失败 -1。
3. **解析**：`parse`（严格、普通模式）、`parse_known`、`parse_intermixed`、
   `parse_known_intermixed`、`parse_with`、`parse_main`（跳过 `argv[0]`）、
   `parse_main_or_exit`（失败时输出并退出）。解析会自动 `freeze`。
4. **取值**：`result.values` 是 `Namespace`；用 `get_text/get_i64/get_u64/get_f64/
   get_bool/get_list/get_value` 取，或 `contains/provided/occurrences` 判断状态。
5. **释放**：`cli.release(&result)` 释放结果，`cli.destroy(&parser)` 释放声明树；
   两者都可对零值安全调用。

## 3. 选项

```yh
let output cli.Argument = cli.option("--output", "-o"); // 主名称 + 别名
output.dest = "out";                                    // 结果键名；默认从名称推导
output.required = true;                                 // 必须显式出现
output.help = "输出路径";
output.metavar = "PATH";
output.hidden = false;
output.deprecated = true;                               // 帮助里标注 (deprecated)
cli.add_argument(&parser, output);

// 更多别名（不改变 dest）
cli.add_alias(&parser, id, "--out");

// 默认值：显式值
output.default_value = cli.default_of(cli.value_text("a.bin"));
// 不创建该键
// output.default_value = cli.suppress_default();
// 保留组/parser 级策略（默认）
// output.default_value = cli.inherit_default();
```

- **dest 推导**：优先双前缀名称，去前缀并把 `-` 换成 `_`（`--dry-run` → `dry_run`）；
  显式 `dest` 优先。
- **必需性**：`required=true` 的选项缺席 → usage_error；默认值不满足 required。
  位置参数的必需性由 `arity` 决定，给它设 `required=true` 是 config_error（对齐 argparse）。
- **常量**：`store_const`/`append_const` 必须给 `const_value`，缺了是 config_error。
- **附着值**：`--output=a.bin` 与 `--output a.bin` 等价；`--output=` 得到显式空串。
- **零参数选项不接受值**：`--flag=yes` 是 usage_error。

## 4. 布尔与计数

```yh
let json cli.Argument = cli.option("--json", 0);       // 无别名时传 0
json.action = cli.store_true;                          // 出现即 true，缺席为 false
cli.add_argument(&parser, json);

let cache cli.Argument = cli.option("--cache", 0);
cache.action = cli.boolean_optional;                   // 自动补 --no-cache
cli.add_argument(&parser, cache);                      // --cache → true，--no-cache → false

let quiet cli.Argument = cli.option("--quiet", "-q");
quiet.action = cli.store_false;                        // 出现即 false，缺席为 true
cli.add_argument(&parser, quiet);

let verbose cli.Argument = cli.option("--verbose", "-v");
verbose.action = cli.count;                            // -vvv → 3
cli.add_argument(&parser, verbose);
```

- `boolean_optional` 只对双前缀长名称生成否定别名；同时给出时**最后出现者胜出**。
- `count` 缺席时键存在但值是 `none`（`get_i64` 返回 -2）；要当 0 用就按上面的写法兜底。
- 显式默认值或 initial 是 `count` 的累计基值：默认 3 时出现一次得 4，initial 5 时得 6。
- 短选项可组合：`-vvv`（零参数各触发一次）、`-abc`（逐个处理，遇到需要值的短选项，
  剩余后缀整体作为它的值，如 `-Ipath`）；`-I=path` 的 `=` 是分隔符。

## 5. 多值与列表

```yh
// 恰好两个值，结果始终是列表
let nums cli.Argument = cli.option("--nums", 0);
nums.arity = cli.exactly(2);
nums.value_kind = cli.integer;                         // text（默认）/integer/natural/real/boolean
cli.add_argument(&parser, nums);                        // --nums 1 2

// 可重复的标量 → 列表
let tag cli.Argument = cli.option("--tag", "-t");
tag.action = cli.append;
cli.add_argument(&parser, tag);                         // -t a -t b → ["a", "b"]

// 可重复的多值 → 批次列表（每个元素本身是列表）
let pair cli.Argument = cli.option("--pair", 0);
pair.action = cli.append;
pair.arity = cli.exactly(2);
cli.add_argument(&parser, pair);                        // --pair a b --pair c d → [["a","b"],["c","d"]]

// 每次出现展平到一层列表
let only cli.Argument = cli.option("--only", 0);
only.action = cli.extend;
only.arity = cli.one_or_more();
cli.add_argument(&parser, only);

// 固定常量，出现即追加
let stamp cli.Argument = cli.option("--stamp", 0);
stamp.action = cli.append_const;
stamp.const_value = cli.value_text("v1");
cli.add_argument(&parser, stamp);
```

读取列表：

```yh
let list []cli.Value;
if (cli.get_list(&result.values, "tag", &list) == 0) {
    printf("tags=%d first=%s\n", len(list), list[0].data.text);
}
```

- `append`/`extend` 有非空列表默认值时先深复制再追加。列表值没有公开构造函数：
  先解析一个列表，用 `get_value` 取出该值再交给 `default_of`，`add_argument` 会深复制。
- `get_list` 返回借用视图：0 成功、-1 缺键、-2 类型不符（例如 `single` 的标量）。
- `exactly(1)` 与 `single` 形状不同：前者是单元素列表，`get_text` 返回 -2。
- 逐项占位名用 `metavars`（**只**用于 `exactly(n)`，个数必须等于 n，且不能与 `metavar`
  同时设置）：`--nums 1 2` 显示为 `--nums LEFT RIGHT`。省略时按数量重复同一个占位名。
- `choices` 缺省把候选集合作为占位名（argparse 的 `{a,b}` 形式）：`--mode {fast,slow}`；
  显式 `metavar`/`metavars` 优先，候选约束照旧生效。
- 列表元素上限见文末容量表（本版本 256）。

## 6. 位置参数

```yh
let source cli.Argument = cli.positional("source");      // 默认 single：恰好一个
cli.add_argument(&parser, source);

let files cli.Argument = cli.positional("files");
files.arity = cli.zero_or_more();                        // 0 个或多个 → 列表（无输入得空列表）
cli.add_argument(&parser, files);

let rest cli.Argument = cli.positional("rest");
rest.arity = cli.remainder();                            // 其后全部 token（含选项样式）
cli.add_argument(&parser, rest);
```

分配规则（普通模式）：按声明顺序**贪心**，同时为后面的参数保留最低需求。

```text
files(zero_or_more) + tags(one_or_more)   输入 `a b c` → files=[a,b] tags=[c]
files(zero_or_more) + source(single)      输入 `a b`   → files=[a]   source=b
files + more_files（都是 zero_or_more）   输入 `a b`   → files=[a,b] more_files=[]
```

- 位置参数只在**段落内**匹配：遇到选项 token 就结束当前段；已完成的可变位置参数
  不会因为后面的新段重新打开（新段里多出来的值报 usage_error）。
- `remainder` 一旦轮到就吞掉其后全部 token（`--help`、`--`、选项样式都算数据）；
  选项形态的 remainder（`--rest a -x --`）同样全部收下。
- `optional()` 位置参数没有取到值时用**默认值**（不写 `const_value`，也不计为显式出现），
  与 argparse 的 `nargs='?'` 一致。
- `single`/`one_or_more`/`exactly(n)` 位置参数不能靠默认值满足数量要求。
- usage 里占位名按数量模型展开：`single` 一个、`exactly(n)` n 个、`zero_or_more` 写
  `[FILE [FILE ...]]`、`one_or_more` 写 `FILE [FILE ...]`、`remainder` 只写 `...`。
- 本层有子命令槽时，**整段 token 足够**（≥ 全部位置参数最低需求 + 1）会为槽预留一个
  token：`files(zero_or_more) + 槽` 下 `tool add` 得到 `files=[] cmd=add`。
  最低需求已占满整段时不预留（`files(one_or_more) + 槽` 下 `tool go` 仍是 `files=[go]`）。

## 7. 子命令与继承

```yh
let slot int = cli.add_subparsers(&parser, cli.subparsers());   // 每个 parser 一个槽

let add cli.Command = cli.command("add");
add.help = "新增笔记";
let aliases [1]*char;
aliases[0] = "a";                                               // 别名只影响匹配
add.aliases = aliases.to_type([]*char);
let add_cmd *cli.Parser = cli.add_parser(&parser, slot, add); // 归父所有，可继续声明
cli.add_argument(add_cmd, cli.positional("title"));

let list_cmd cli.Command = cli.command("list");
cli.add_parser(&parser, slot, list_cmd);
```

解析后：

```yh
printf("command=%s\n", result.command_path[0]);   // 规范名，别名输入也得到 "add"
```

- **槽配置**：`spec.dest` 非空时把选中的规范命令名写进命名空间；
  `spec.required = true` 时未选命令报 usage_error；`spec.title`/`spec.description`
  决定帮助段标题与说明（缺省标题 `commands`）；`spec.metavar` 覆盖 usage 占位名
  （缺省为 `{add,list}` 形式的规范命令名列表）。
- **usage 形态**：槽写成 `{add,list} ...`（argparse 的 PARSER 语义，不加方括号）。
- **作用范围**：根选项只在子命令之前有效；子命令之后只识别子 parser 的声明。
- **与前缀位置参数共存**：槽前的可变位置参数不会吞掉子命令名——整段 token 满足
  「位置参数最低需求 + 1」时为槽预留一个 token（`tool add` → `files=[] cmd=add`）。
- **未知子命令**：即使 `known` 模式也是错误（槽不接受任意值）。
- **默认值合成**：显式值优先；没有显式值时按「父 → 子」应用默认，子层默认覆盖父层默认。

公共 parent（`--color`、`--quiet` 之类前后都要支持的选项）用 `inherit` 复制，
而不是让根选项穿透：

```yh
let common cli.Parser;
let common_config cli.ParserConfig = cli.parser_config("common");
common_config.add_help = false;                 // 避免复制 -h/--help 造成冲突
cli.init(&common, common_config);
cli.add_argument(&common, cli.option("--color", 0));

cli.inherit(&root, &common);                    // 深复制参数、默认值、组、互斥组
cli.inherit(child, &common);                    // 之后修改 common 不影响它们
```

## 8. 展示组与互斥组

```yh
// 展示组：只影响帮助分段与组级默认值
let gspec cli.Group = cli.group("输出", "输出相关参数");
gspec.argument_default = cli.default_of(cli.value_text("plain"));  // 组内默认值
let group_id int = cli.add_group(&parser, gspec);

let fmt cli.Argument = cli.option("--fmt", 0);
fmt.group = group_id;
cli.add_argument(&parser, fmt);

// 互斥组：最多一个成员显式出现；required 时恰好一个
let mutex int = cli.add_mutex(&parser, false, 0);   // 第二参数 required，第三参数展示组
let json cli.Argument = cli.option("--json", 0);
json.action = cli.store_true;
json.mutex = mutex;
let yaml cli.Argument = cli.option("--yaml", 0);
yaml.action = cli.store_true;
yaml.mutex = mutex;
cli.add_argument(&parser, json);
cli.add_argument(&parser, yaml);
```

- `--json --yaml` → usage_error；默认值与 initial 不算「显式出现」。
- 组级 `conflict = cli.resolve` 可在名称冲突时移除旧声明的名称
  （名称全部移除的旧声明停用，旧 ID 不复用）。

## 9. 解析模式与初始命名空间

```yh
// known：把没被消费的 token 按输入顺序留在 result.unparsed
let r1 cli.Result = cli.parse_known(&parser, args);
for i, item in r1.unparsed {
    printf("unparsed[%d]=%s\n", i, item);
}
cli.release(&r1);

// intermixed：跨选项收集位置参数
let r2 cli.Result = cli.parse_intermixed(&parser, args);
cli.release(&r2);

// 显式配置：模式 + known + 初始值
let preset cli.Namespace;
cli.namespace_init(&preset);
cli.namespace_set(&preset, "source", cli.value_text("default.txt"));

let spec cli.ParseConfig = cli.parse_config();
spec.mode = cli.intermixed;
spec.known = true;
spec.initial = &preset;                 // 深复制进结果，调用者的 namespace 不被改
spec.file_max_depth = 16;
spec.file_max_bytes = 1048576;
spec.file_max_tokens = 4096;
let r3 cli.Result = cli.parse_with(&parser, args, spec);
cli.release(&r3);
cli.namespace_destroy(&preset);
```

- `known` 只放宽「未被当前声明消费的 token」：缺必需项、坏值、未知子命令、互斥冲突
  仍然是错误；未知短组合**整 token** 保留，不会先累计一半再保留后缀。
- `intermixed` 拒绝子命令、`remainder`，以及「同一 dest 同时由选项与位置提供」
  的声明组合（返回 config_error）。
- `initial` 里已有的键不会被默认值覆盖，但会被显式 action 更新。

## 10. 自定义类型与校验

```yh
// 转换回调：把 0x 前缀文本转成整数
fn hex_convert(ctx *cli.ConvertContext, out *cli.Value, error *cli.Diagnostic,
    user *void) int {
    let text *char = ctx.token;
    if (text[0] != '0' || (text[1] != 'x' && text[1] != 'X')) {
        error.message = "需要 0x 前缀的十六进制";
        return -1;
    }
    let value i64 = 0;
    let i int = 2;
    for text[i] != 0 {
        let ch int = text[i].to_type(int);
        let digit int = -1;
        if (ch >= '0' && ch <= '9') {
            digit = ch - '0';
        } else if (ch >= 'a' && ch <= 'f') {
            digit = ch - 'a' + 10;
        } else if (ch >= 'A' && ch <= 'F') {
            digit = ch - 'A' + 10;
        } else {
            error.message = "非法十六进制字符";
            return -1;
        }
        value = value * 16 + digit.to_type(i64);
        i += 1;
    }
    *out = cli.value_i64(value);
    return 0;
}

// 校验回调：值必须非负
fn positive(value cli.Value, error *cli.Diagnostic, user *void) int {
    if (value.kind == cli.integer && value.data.integer < 0) {
        error.message = "必须是正数";
        return -1;
    }
    return 0;
}

let mask cli.Argument = cli.option("--mask", 0);
mask.value_kind = cli.integer;      // 转换器输出必须与声明类型一致
mask.converter = hex_convert;
mask.validator = positive;          // 转换与 choices 之后逐值调用
cli.add_argument(&parser, mask);    // --mask 0x1f → 31
```

命名注册表（同一 parser 内复用）：

```yh
cli.register_type(&parser, "chars", count_chars, 0);        // 回调 + user 指针
let shape cli.ValueShape = cli.value_shape(cli.text, 0);
cli.register_action(&parser, "upper", cli.exactly(1), shape, upper_action, 0);

let length cli.Argument = cli.option("--length", 0);
length.value_kind = cli.integer;
length.type_name = "chars";                                 // 与 converter 互斥
cli.add_argument(&parser, length);

let shout cli.Argument = cli.option("--shout", 0);
shout.action = cli.custom;
shout.action_name = "upper";                                // 数量与形状来自注册项
cli.add_argument(&parser, shout);
```

- 回调返回 -1 时，`error.message` 会进入结果诊断；不设置则用库内默认消息。
- malloc 出来的文本用 `cli.context_text(context, text)` 复制进结果池再返回；
  回调返回的切片不能指向自己的栈数组。
- `validator` 也会在 `freeze` 时用于校验显式默认值与常量（失败是 config_error），
  所以不要依赖调用次数。
- `choices` 只约束命令行显式值；默认值与常量不参与 choices 校验（与 argparse 一致），
  需要严格约束时用 `validator`。
- converter 输出类型不符 → usage_error；custom action 输出形状不符 → usage_error。

## 11. 自定义 action

```yh
fn join_all(ctx *cli.ActionContext, out *cli.Value, error *cli.Diagnostic,
    user *void) int {
    let buffer [256]char;
    let at int = 0;
    if (ctx.previous.kind == cli.text && ctx.previous.data.text != 0) {
        let old *char = ctx.previous.data.text;      // 旧值的借用视图
        for old[at] != 0 && at < 200 {
            buffer[at] = old[at];
            at += 1;
        }
    }
    let i int = 0;
    for i < len(ctx.values) {                        // 本次转换出的值
        if (at > 0 && at < 200) {
            buffer[at] = ',';
            at += 1;
        }
        let item *char = ctx.values[i].data.text;
        let j int = 0;
        for item[j] != 0 && at < 200 {
            buffer[at] = item[j];
            at += 1;
            j += 1;
        }
        i += 1;
    }
    buffer[at] = 0;
    *out = cli.value_text(cli.context_text(ctx.context, &buffer[0]));
    return 0;
}

let add cli.Argument = cli.option("--add", 0);
add.action = cli.custom;
add.arity = cli.exactly(1);                          // 必须显式声明数量
let shape cli.ValueShape = cli.value_shape(cli.text, 0);  // depth：0 标量、1 列表、2 批次
add.output_shape = &shape;                           // 直接回调必须给形状
add.custom_action = join_all;
cli.add_argument(&parser, add);                      // --add a --add b → "a,b"
```

`ActionContext` 提供 `argument`（参数 ID）、`dest`、`matched_name`、`occurrences`
（此前的出现次数）、`values`（本次值）、`previous`（旧值，没有时为 none）、
`context`（结果池句柄）。

## 12. 参数文件

```yh
let config cli.ParserConfig = cli.parser_config("tool");
config.fromfile_prefix_chars = "@";                  // 开启 @file 展开
cli.init(&parser, config);
```

```text
# args.txt：默认一行一个完整参数
--output
out.bin
input.bin
```

```sh
tool @args.txt        # 等价于 tool --output out.bin input.bin
```

- **一行一个 token**：行内空白保留在 token 里（`--add one` 会变成名字含空格的
  单个 token）；需要按空格拆分时用 `line_converter`。
- **相对路径**：顶层按进程工作目录，嵌套包含按包含文件所在目录。
- **上限**：深度、累计字节、token 数三个上限，可从 `ParseConfig` 调整；
  循环、超限、打开/读取失败都返回带文件与行号的 `resource_error`，
  且不使用部分展开结果。
- **逐行回调**（`config.line_converter`）可以把一行拆成零个或多个 token；
  返回的 `LineTokens.items` 必须由回调自己持有（例如全局或池化存储）。
- 子命令 parser 不能设置展开前缀或逐行回调（`freeze` 报 config_error），
  展开始终用根 parser 的配置。

## 13. 帮助与输出

```yh
// 生成文本（不打印、不退出）
let help cli.TextResult = cli.format_help(&parser);
if (help.status == cli.ok) {
    cli.render_text(&help, 1);              // 写到 fd 1；-1 表示写失败
}
cli.release_text(&help);

let usage cli.TextResult = cli.format_usage(&parser);
cli.release_text(&usage);

// 直接打印
cli.print_help(&parser, 1);
cli.print_usage(&parser, 2);

// 结果级输出与退出码
let result cli.Result = cli.parse(&parser, args);
if (result.status != cli.ok) {
    cli.render(&result, 1, 2);              // 控制文本 → out，诊断与 usage → err
    let code int = cli.exit_code(&result);  // 0 / 2 / 1
    cli.release(&result);
    return code;
}
cli.release(&result);
```

自定义 usage 与文本模板：

```yh
config.usage = "%(prog)s [options] src";   // 空串表示不显示 usage 正文
config.description = "%(prog)s 做某件事";
config.epilog = "详见 %(prog)s --help";
output.help = "%(prog)s 输出到 %(default)s（类型 %(type)s）";

let version cli.Argument = cli.option("--version", 0);
version.action = cli.version;
version.version_text = "%(prog)s 1.0";      // 空指针时只输出 prog
```

- 占位符：`%(prog)s`、`%(dest)s`、`%(default)s`、`%(type)s` 与 `%%`；usage/
  description/epilog/version 只接受 `%(prog)s` 与 `%%`，help 支持全部。
- 未知占位符在 `freeze` 报 config_error，不会带着字面量进入输出。
- `usage` 为空串时不写 usage 正文；非空时整体替换自动生成的 usage 行。

配置与效果：

```yh
let config cli.ParserConfig = cli.parser_config("tool");
config.help_format.show_defaults = true;      // 追加 "(default: ...)"
config.help_format.width = 100;               // 折行宽度；0 不折行
config.help_format.metavar_from_type = true;  // 无 metavar 时用 INT/UINT/FLOAT/BOOL
config.help_format.preserve_description = true;
config.help_format.max_help_column = 30;      // 说明列起始列；0 用段落默认（位置 22、其余 26）
config.color = cli.always;                    // never / automatic / always
config.suggest_on_error = true;               // 未知选项/choices/子命令给「是否想用 X？」
```

- 帮助/usage 文本上限 `MAX_HELP`（16384 字节）：超限时 `format_help`/`format_usage`
  返回 `resource_error` 且 `text` 为空指针，不返回截断文本。
- `Color.automatic` 用 `os.is_terminal` 检测，非终端或检测失败时无色降级。
- `boolean_optional` 在 usage 里写成 `[--cache | --no-cache]`，帮助列写成
  `--cache, --no-cache`；子命令段按 argparse 的排法先给 `{add,list}` 再给各命令说明。
- 帮助段落顺序固定：usage → description → positional → options → 用户组 →
  commands → epilog；`hidden` 参数不出现在帮助但继续参与匹配。
- 帮助/诊断文本里的控制字节与非法 UTF-8 输出为 `\xHH`。
- `Result` 在解析失败时自带 `usage_text` 与 `prog_text`，所以 `render` 不需要 parser。

## 14. 退出码与错误处理

| `Result.status` | 含义 | `exit_code` |
| --- | --- | --- |
| `ok` | 解析成功 | 0 |
| `help_requested` / `version_requested` | 控制请求（`control_text` 是正文） | 0 |
| `usage_error` | 输入不满足声明（缺值、未知选项、坏值、互斥冲突等） | 2 |
| `config_error` | 声明无效或不支持（freeze 失败） | 1 |
| `resource_error` | 内存不足、参数文件读取失败、超限 | 1 |

`Diagnostic.code` 的稳定取值有对应常量，应用应比较常量而不是文案：
`cli.CODE_USAGE`、`cli.CODE_CONFIG`、`cli.CODE_RESOURCE`（分别等价于
`"usage_error"`、`"config_error"`、`"resource_error"`）。

```yh
let result cli.Result = cli.parse(&parser, args);
if (result.status != cli.ok) {
    let diag cli.Diagnostic = result.error;      // 借用视图
    if (diag.message != 0) {
        printf("错误: %s\n", diag.message);
    }
    if (diag.token_index >= 0) {
        printf("第 %d 个 token\n", diag.token_index);
    }
    if (diag.file != 0) {
        printf("来自 %s:%d\n", diag.file, diag.line);
    }
    cli.release(&result);
}
```

- 诊断文案带上下文（对齐 argparse）：choices 不匹配写「选项 --mode 的值不在候选集合中
  （可选：fast, slow）」，未知子命令写「未知子命令 ad（可选：add, list）」，
  多余的位置参数列出全部剩余 token（「多余的位置参数：b c」）。
  开启 `suggest_on_error` 后，choices 与子命令也会追加「是否想用 X？」（编辑距离 ≤ 2）。
- 类型化 getter 的错误码：`0` 成功、`-1` 缺键、`-2` 类型不符（不做隐式转换）。
- 声明阶段的错误是**粘滞**的：第一次失败后 `add_argument` 继续返回 -1，
  诊断用 `cli.last_error(&parser)` 读取，直到 `destroy` 才能重新 `init`。
- `parse_main_or_exit` 只接受根 parser；输出失败时最终退出码降级为 1。
- `Result.warnings` 保存运行期警告（目前是 deprecated 参数/命令的显式使用），
  每个声明每次 parse 最多一条；`render` 把它们以「警告: …」写到 error_fd。
  `parse_main_or_exit` 在成功路径先输出并清空，应用看到的 `warnings` 为空。

## 15. 生命周期与所有权

```yh
cli.release(&result);      // 先释放结果
cli.destroy(&parser);      // 再释放声明树（递归释放子命令 parser）
```

- `add_argument` / `register_*` / `set_default` 会**深复制**传入的文本、候选、
  默认值与常量；注册完成后原存储即可释放。
- `set_default` 也可以给**尚未声明**的 dest 设置值（`argparse` 的 `set_defaults` 语义）；
  该键在解析结果里存在、`provided` 为 false，并且不会覆盖 `initial`。
- 结果独立于 parser：`destroy` 之后再读 `result.values` 里的文本仍然有效
  （结果自带池）；`release` 释放结果全部存储。
- 重复解析是隔离的：同一个 parser 连续 `parse`，第二次不会继承第一次的显式值。
- 子 parser 归父所有：`add_parser` 返回的句柄不要单独 `destroy`，随根一起释放。
- `namespace_set` 深复制值，`get_*` 返回借用视图（命名空间存活期内有效）。

## 16. 常见陷阱

1. **`freeze` 之后不能再注册**：解析会自动 freeze；需要改声明就重新
   `destroy` + `init`。
2. **`count` 缺席不是 0**：键存在但为 `none`，`get_i64` 返回 -2；用默认值
   `cli.default_of(cli.value_i64(0))` 或代码兜底。
3. **`single` 与 `exactly(1)` 形状不同**：前者标量（`get_text` 可用），
   后者单元素列表（只能用 `get_list`）。
4. **未知选项不会成为已知选项的值**：`--output --verbose` 报缺值；
   需要以 `-` 开头的值就写 `--output=-draft`。
5. **参数文件一行一个 token**：整行内容是一个参数，空格不会被拆分。
6. **混合模式限制**：`intermixed` 下同一 dest 不能同时由选项和位置参数提供，
   也不支持子命令与 `remainder`。
7. **短组合只对「单前缀 + 单字节」声明生效**：`-abc` 逐字符匹配；
   单前缀多字节名称（如 `-vv`）如果精确注册过，优先精确匹配。
8. **负数特判**：注册了 `-1` 这类数字型短选项后，`-12` 不再被当作位置值。
9. **上限**：注册数量、列表长度、参数个数、参数文件 token 数都有上限，
   超出是明确的失败而不是截断。

## 文件划分

| 文件 | 职责 |
| --- | --- |
| `cli.yh` | 公开数据模型、容量常量、构造函数、模块私有分配池与状态 |
| `schema.yh` | `init`/`add_argument`/`add_alias`/`freeze`/`last_error`/`destroy`、声明校验 |
| `values.yh` | 命名空间、值深复制、`contains`/`provided`/`occurrences` 与类型化 getter |
| `parse.yh` | token 匹配、数量分配、默认值层级、必需项与互斥检查 |
| `convert.yh` | 内置类型转换（integer/natural/real/boolean/text） |
| `write.yh` | 结果写入（标量/列表/批次列表/计数/自定义 action 提交） |
| `commands.yh` | 子命令槽、`inherit`、展示组与互斥组 |
| `layer.yh` | 分层解析、known/intermixed 模式、initial、命令路径 |
| `extensions.yh` | converter/validator/custom action 与命名注册表 |
| `files.yh` | 参数文件 `@file` 展开 |
| `help.yh` | usage/help 生成、格式配置、颜色、建议与输出 API |
| `entry.yh` | `argc`/`argv` 适配与 0/1/2 退出契约 |

## 公开 API

- **声明**：`parser_config`、`option`、`positional`、`help_format`、`subparsers`、
  `command`、`group`、`parse_config`。
- **诊断码**：`CODE_USAGE`、`CODE_CONFIG`、`CODE_RESOURCE`。
- **值**：`value_none/text/i64/u64/f64/bool`、`default_of`、`suppress_default`、
  `inherit_default`、`value_shape`。
- **数量**：`infer_arity`、`single`、`exactly`、`optional`、`zero_or_more`、
  `one_or_more`、`remainder`、`no_values`。
- **注册**：`init`、`add_argument`、`add_alias`、`add_group`、`add_mutex`、
  `add_subparsers`、`add_parser`、`inherit`、`register_type`、`register_action`、
  `set_default`、`get_default`、`freeze`、`last_error`、`destroy`。
- **解析**：`parse`、`parse_known`、`parse_intermixed`、`parse_known_intermixed`、
  `parse_with`、`parse_main`、`parse_main_or_exit`、`release`。
- **查询**：`namespace_init`/`namespace_set`/`namespace_destroy`、`contains`、
  `provided`、`occurrences`、`get_value`、`get_text`、`get_i64`、`get_u64`、
  `get_f64`、`get_bool`、`get_list`。
- **扩展分配**：`context_text`（把回调产生的文本复制进结果池）。
- **帮助与输出**：`format_usage`、`format_help`、`release_text`、`render_text`、
  `print_usage`、`print_help`、`render`、`exit_code`。
- **结果字段**：`Result.values`、`Result.unparsed`、`Result.warnings`、
  `Result.command_path`；`Argument.version_text` 是 version action 的输出模板。
- **测试专用**：`test_alloc_count`、`test_fail_alloc_after`（分配失败注入，
  不作为产品配置项）。

## 契约要点

- 声明是值语义：`add_argument` 复制文本、候选、默认值与常量；结果独立持有文本与
  列表，`destroy` parser 之后仍可读结果，`release` 释放结果全部存储。
- 零值 `destroy`/`release`/`release_text` 安全；`init` 要求句柄为零值或已 destroy；
  首次配置错误粘滞保留，直到 destroy。
- 默认值层级：action 固有缺省 → 参数/组/parser 策略 → `set_default` 覆盖（含未声明
  dest）→ 子命令默认（父到子覆盖）→ `initial`（不被默认值覆盖）→ 显式 action。
- `provided`/`occurrences` 只统计显式出现；`contains` 区分「键不存在」与「显式 none」。
- 类型化 getter 不做隐式转换：缺键返回 -1，类型不符返回 -2。
- 退出契约：`parse_main_or_exit` 成功才返回；help/version 退出 0，
  usage_error 退出 2，config/resource 退出 1，输出失败降级为 1。

## 容量上限（本版本）

`MAX_ARGS=64`、`MAX_NAMES=4`、`MAX_ENTRIES=128`、`MAX_LIST=256`、`MAX_CHOICES=64`、
`MAX_CHILDREN=32`、`MAX_ALIASES=8`、`MAX_GROUPS=16`、`MAX_MUTEX=16`、`MAX_DEPTH=8`、
`MAX_TYPES=8`、`MAX_ACTIONS=8`、`MAX_ARGC=128`、`MAX_TEXT=1024`、`MAX_HELP=16384`、
`MAX_METAVARS=16`、`MAX_FILE_TOKENS=4096`、`MAX_FILE_LINE=4096`、
`MAX_FILE_DEPTH=16`、`MAX_FILE_BYTES=1048576`。
超出上限返回带诊断的失败，不静默截断。

## 未实现与已知边界

- 逐字段着色；`HelpFormat` 的保留模式只影响空白折叠与缩进。
- 折行按字节宽度近似，中文宽度不等于终端列宽。
- 位置参数与子命令槽的顺序固定为「位置在前、槽在后」；
  混合模式下同一 dest 不能同时由选项与位置提供（返回 config_error）。
- 参数文件诊断带文件与行号，列号为 -1；`line_converter` 返回的切片须由回调自持。
- 分配失败注入只覆盖 parser 池（注册期）；结果池独立，注入不影响解析结果。

## 验收

cli 的用例与 fixture 全部放在本目录，不与全局 `tests/` 耦合：

```sh
python3 libs/cli/test/run.py                     # 真实 argv/退出码：5 例
python3 libs/cli/test/diff.py                    # 与 Python argparse 的差分验收
just libs-test                                   # CI 独立阶段，含上面两个 runner
```

- **语义断言**在 `libs/cli/zz_tests_{basics,actions,commands,extensions,help}.yh`
  （51 个 `test`），由 `cd libs && yh test cli` / `just test` /
  `just selfhost-native` / `just libs-test` 执行；文件名必须 `zz_` 前缀
  （类型声明在 `cli.yh`）。
- fixture：`libs/cli/test/{climodel,clibasics,cliwarnings,clidiff}`；其余
  selftest 夹具已迁入内建测试并删除（记录见
  [YT4-P4](../../docs/01-finished/yh-YT4-P4-cli迁移-2026-10-25.md)）。
- runner 的 5 条用例：`cli0-model-abi`、`cli1-pack-run`、`cli1-pack-help`、
  `cli1-pack-missing`、`cli6-warning-entry`。
- `diff.py` 用 `clidiff` 探针把 94 条 argv 同时交给 yh 与 Python 3.14 argparse，
  比较 status、各 dest 值与未消费 token；设计保留的差异在脚本里显式列出，
  只在新差异出现时返回非 0。
- 仓库级门：`just libs-test`（含 cli runner + diff）、`just test`、
  `just selfhost-native`。
