#!/usr/bin/env python3
"""LL2/LL9 模块缓存门：IRModule 序列化往返、确定性、坏输入拒绝与稳定身份。

在隔离项目里编译**真实** compiler/ir（含 ssa_module_30_serialize.yh），再用一个
scalar 风格的小模块（2 个来源 / 4 个类型 / 3 个符号 / 1 个带重定位的全局 /
1 个含 PARAM·CONST·ADD·CALL·COPY 与逐条来源的函数）验证：

  roundtrip  序列化→反序列化→完整 verifier 通过，主要字段与原件逐项一致，
             再次序列化逐字节相同（确定性），容量不足时不写任何字节，
             空模块（五张表全空）同样往返；
  reject     截断/错 magic/错格式版本/错内存版本/计数与长度越界/非法索引
             （重定位符号、全局符号）/目标键与 triple 不一致/描述符与头部总数
             不一致/名字含内部零，共 11 例，各返回 -1 且 out 保持零初始化；
  identity   同一模块两次构造摘要相同，改一个函数常量、改目标或让模块不合法
             都会改变/拒绝摘要；探针跑两次，两次输出必须逐字节相同（跨进程稳定）。

依赖与既有门相同的环境（x86_64 宿主经 qemu 跑 arm64 种子）：
    export PATH="$PWD/tmp/boot/crossbin:$PATH"
    export SEED=bin/yh-linux-arm64 YH_LINK=/nonexistent
    python3 tests/selfhost/llvm-module-cache.py --compiler-path ./yh

退出码：全部通过 0；失败非 0，并保留编译/运行日志到 tmp/llvm-migration/ir-module-cache/。
"""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/llvm-migration/ir-module-cache"

# 探针源码：真实跨模块消费 ir 的 pub 序列化/身份接口；所有断言都在 yh 侧完成，
# 失败时打印具体阶段码，Python 侧只负责构建、运行与保留原始诊断。
FIXTURE = r'''
module main;
import ir;

// make_target：给出目标完整身份；key=2 用 x86_64 Linux，key=1 用 aarch64 Linux。
// 字符串手工抄自 ir/ssa_module_00_model.yh 的受检目标表，不由待测模块推导。
fn make_target(target *ir.IRModuleTarget, key int) void {
    if (key == 1) {
        target.triple = "aarch64-unknown-linux-gnu";
        target.data_layout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i8:8:32-i16:16:32-i64:64-i128:128-n32:64-S128-Fn32";
        target.abi = "aapcs64";
    } else {
        target.triple = "x86_64-unknown-linux-gnu";
        target.data_layout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128";
        target.abi = "sysv-amd64";
    }
    target.pointer_bits = 64;
    target.little_endian = 1;
    target.layout_version = 1;
}

// build_module：构造可往返的完整模块。内容覆盖多来源、聚合布局、指针重定位、
// 声明/定义两种符号、直接调用与逐条指令来源。返回 0 或阶段码。
fn build_module(unit *ir.IRModule, key int) int {
    let target ir.IRModuleTarget;
    make_target(&target, key);
    if (ir.ir_module_init(unit, &target) != 0) { return 1; }
    let text [8]u8;
    text[0] = 'm'; text[1] = 'o'; text[2] = 'd'; text[3] = 'u';
    text[4] = 'l'; text[5] = 'e'; text[6] = ';'; text[7] = '\n';
    if (ir.ir_module_add_source(unit, "scalar.yh", &text[0], 8) != 0) { return 2; }
    if (ir.ir_module_add_source(unit, "extra.yh", 0, 0) != 1) { return 3; }
    let scalar ir.IRModuleType;
    scalar.kind = ir.IR_TY_I32; scalar.bits = 32; scalar.size = 4; scalar.align = 4; scalar.elem = -1;
    if (ir.ir_module_add_type(unit, "i32", &scalar, 0, 0) != 0) { return 4; }
    scalar.kind = ir.IR_TY_VOID; scalar.bits = 0; scalar.size = 0; scalar.align = 1;
    if (ir.ir_module_add_type(unit, "void", &scalar, 0, 0) != 1) { return 5; }
    scalar.kind = ir.IR_TY_PTR; scalar.bits = 64; scalar.size = 8; scalar.align = 8; scalar.elem = 0;
    if (ir.ir_module_add_type(unit, "i32ptr", &scalar, 0, 0) != 2) { return 6; }
    let fields [2]ir.IRModuleField;
    fields[0].type_id = 0; fields[0].offset = 0;
    fields[1].type_id = 2; fields[1].offset = 8;
    scalar.kind = ir.IR_MODULE_TY_STRUCT; scalar.bits = 0; scalar.size = 16;
    scalar.align = 8; scalar.elem = -1; scalar.count = 0;
    if (ir.ir_module_add_type(unit, "Pair", &scalar, &fields[0], 2) != 3) { return 7; }
    let global_symbol ir.IRModuleSymbol;
    global_symbol.kind = ir.IR_MODULE_SYMBOL_GLOBAL; global_symbol.type_id = 3;
    global_symbol.linkage = ir.IR_MODULE_LINK_PRIVATE; global_symbol.defined = 1;
    global_symbol.mutable = 1; global_symbol.source = 0; global_symbol.offset = 0;
    if (ir.ir_module_add_symbol(unit, "fixture.data", &global_symbol, 0, 0) != 0) { return 8; }
    let params [1]int;
    params[0] = 0;
    let function_symbol ir.IRModuleSymbol;
    function_symbol.kind = ir.IR_MODULE_SYMBOL_FUNCTION; function_symbol.type_id = 0;
    function_symbol.linkage = ir.IR_MODULE_LINK_EXTERNAL;
    function_symbol.source = 0; function_symbol.offset = 0;
    if (ir.ir_module_add_symbol(unit, "fixture.answer", &function_symbol, &params[0], 1) != 1) { return 9; }
    function_symbol.defined = 1;
    if (ir.ir_module_add_symbol(unit, "fixture.answer", &function_symbol, &params[0], 1) != 1) { return 10; }
    function_symbol.defined = 0; function_symbol.source = 1; function_symbol.offset = 0;
    if (ir.ir_module_add_symbol(unit, "fixture.callee", &function_symbol, &params[0], 1) != 2) { return 11; }
    let data [16]u8;
    data[0] = 7;
    let relocs [1]ir.IRModuleReloc;
    relocs[0].offset = 8; relocs[0].width = 8; relocs[0].symbol = 2; relocs[0].addend = 0;
    if (ir.ir_module_add_global(unit, 0, &data[0], 16, 8, &relocs[0], 1) != 0) { return 12; }
    let types [1]ir.IRType;
    types[0].kind = ir.IR_TY_I32; types[0].bits = 32; types[0].elem = -1;
    let insts [5]ir.IRInst;
    insts[0].op = ir.IR_OP_PARAM; insts[0].result_id = 0; insts[0].result_type = 0;
    insts[0].a = -1; insts[0].b = -1; insts[0].aux = -1; insts[0].imm = 0;
    insts[1].op = ir.IR_OP_CONST; insts[1].result_id = 1; insts[1].result_type = 0;
    insts[1].a = -1; insts[1].b = -1; insts[1].aux = -1; insts[1].imm = 42;
    insts[2].op = ir.IR_OP_ADD; insts[2].result_id = 2; insts[2].result_type = 0;
    insts[2].a = 0; insts[2].b = 1; insts[2].aux = -1;
    insts[3].op = ir.IR_OP_CALL; insts[3].result_id = 3; insts[3].result_type = 0;
    insts[3].a = -1; insts[3].b = -1; insts[3].aux = 0;
    insts[4].op = ir.IR_OP_COPY; insts[4].result_id = 4; insts[4].result_type = 0;
    insts[4].a = 2; insts[4].b = -1; insts[4].aux = -1;
    let calls [1]ir.IRCall;
    calls[0].abi = 0; calls[0].callee_value = -1; calls[0].signature_type = -1;
    calls[0].symbol_first = 0; calls[0].symbol_len = 14;
    calls[0].arg_first = 0; calls[0].arg_count = 1;
    let args [1]ir.IRCallArg;
    args[0].value = 2; args[0].type_id = 0;
    let call_name *char = "fixture.callee";
    let blocks [1]ir.IRBlock;
    blocks[0].id = 0; blocks[0].first_inst = 0; blocks[0].inst_count = 5;
    blocks[0].term = ir.IR_TERM_RET; blocks[0].term_value = 3;
    blocks[0].succ0 = -1; blocks[0].succ1 = -1;
    let f ir.IRFunction;
    f.abi = 0; f.target_id = key; f.ret_type = 0; f.type_count = 1; f.types = &types[0];
    f.inst_count = 5; f.insts = &insts[0]; f.value_count = 5;
    f.call_count = 1; f.calls = &calls[0]; f.call_arg_count = 1; f.call_args = &args[0];
    f.call_symbols = call_name.to_type(*u8); f.call_symbol_size = 14;
    f.block_count = 1; f.blocks = &blocks[0];
    let mapping [1]int;
    mapping[0] = 0;
    let locs [5]ir.IRModuleLoc;
    locs[0].source = 0; locs[0].offset = 0;
    locs[1].source = 0; locs[1].offset = 6;
    locs[2].source = 1; locs[2].offset = 0;
    locs[3].source = 0; locs[3].offset = 2;
    locs[4].source = 1; locs[4].offset = 0;
    if (ir.ir_module_add_function(unit, 1, &f, &mapping[0], &locs[0]) != 0) { return 13; }
    if (ir.ir_module_verify(unit) != 0) { return 14; }
    return 0;
}

// text_size：C 字符串长度 + 1，用于独立重算 blob 偏移。
fn text_size(text *char) int {
    let n int = 0;
    for n < 1024 { if (text[n] == 0) { return n + 1; } n += 1; }
    return -1;
}

// same_text：有界比较两个 C 字符串。
fn same_text(a *char, b *char) int {
    let n int = 0;
    for n < 1024 {
        if (a[n] != b[n]) { return 0; }
        if (a[n] == 0) { return 1; }
        n += 1;
    }
    return 0;
}

// section_offset：按格式文档独立算出定长区各段起点（10 = 变长区起点）。
fn section_offset(unit *ir.IRModule, section int) int {
    let field_total int = 0;
    let i int = 0;
    for i < unit.type_count { field_total += unit.types[i].field_count; i += 1; }
    let param_total int = 0;
    i = 0;
    for i < unit.symbol_count { param_total += unit.symbols[i].param_count; i += 1; }
    let reloc_total int = 0;
    i = 0;
    for i < unit.global_count { reloc_total += unit.globals[i].reloc_count; i += 1; }
    let map_total int = 0;
    let loc_total int = 0;
    i = 0;
    for i < unit.function_count {
        map_total += unit.functions[i].type_map_count;
        loc_total += unit.functions[i].loc_count;
        i += 1;
    }
    let offset int = 208;
    if (section == 0) { return offset; }
    offset += unit.source_count * 16;
    if (section == 1) { return offset; }
    offset += unit.type_count * 80;
    if (section == 2) { return offset; }
    offset += field_total * 16;
    if (section == 3) { return offset; }
    offset += unit.symbol_count * 96;
    if (section == 4) { return offset; }
    offset += param_total * 8;
    if (section == 5) { return offset; }
    offset += unit.global_count * 32;
    if (section == 6) { return offset; }
    offset += reloc_total * 32;
    if (section == 7) { return offset; }
    offset += unit.function_count * 32;
    if (section == 8) { return offset; }
    offset += map_total * 8;
    if (section == 9) { return offset; }
    return offset + loc_total * 16;
}

// get_word / put_word：小端读写一个 64 位字，供坏输入用例精确改字节。
fn get_word(buf *u8, offset int) int {
    let value int = 0;
    let i int = 0;
    for i < 8 { value = value | (buf[offset + i].to_type(int) << (i * 8)); i += 1; }
    return value;
}

fn put_word(buf *u8, offset int, value int) void {
    let i int = 0;
    for i < 8 { buf[offset + i] = ((value >> (i * 8)) & 255).to_type(u8); i += 1; }
}

// same_bytes：比较两段字节。
fn same_bytes(a *u8, b *u8, size int) int {
    let i int = 0;
    for i < size { if (a[i] != b[i]) { return 0; } i += 1; }
    return 1;
}

// same_inst：逐字段比较两条指令。
fn same_inst(a *ir.IRInst, b *ir.IRInst) int {
    return a.op == b.op && a.result_id == b.result_id && a.result_type == b.result_type
        && a.a == b.a && a.b == b.b && a.imm == b.imm && a.aux == b.aux ? 1 : 0;
}

// same_body：比较函数体全部 SSA 表，包括调用符号字节与基本块终结。
fn same_body(a *ir.IRFunction, b *ir.IRFunction) int {
    if (a.abi != b.abi || a.target_id != b.target_id || a.ret_type != b.ret_type
        || a.type_count != b.type_count || a.inst_count != b.inst_count
        || a.phi_count != b.phi_count || a.phi_input_count != b.phi_input_count
        || a.call_count != b.call_count || a.call_arg_count != b.call_arg_count
        || a.call_symbol_size != b.call_symbol_size || a.block_count != b.block_count
        || a.value_count != b.value_count) { return 0; }
    let i int = 0;
    for i < a.type_count {
        if (a.types[i].kind != b.types[i].kind || a.types[i].elem != b.types[i].elem
            || a.types[i].bits != b.types[i].bits) { return 0; }
        i += 1;
    }
    i = 0;
    for i < a.inst_count { if (same_inst(&a.insts[i], &b.insts[i]) == 0) { return 0; } i += 1; }
    i = 0;
    for i < a.phi_count {
        if (a.phis[i].first != b.phis[i].first || a.phis[i].count != b.phis[i].count) { return 0; }
        i += 1;
    }
    i = 0;
    for i < a.phi_input_count {
        if (a.phi_inputs[i].pred != b.phi_inputs[i].pred || a.phi_inputs[i].value != b.phi_inputs[i].value) { return 0; }
        i += 1;
    }
    i = 0;
    for i < a.call_count {
        if (a.calls[i].abi != b.calls[i].abi || a.calls[i].callee_value != b.calls[i].callee_value
            || a.calls[i].signature_type != b.calls[i].signature_type
            || a.calls[i].symbol_first != b.calls[i].symbol_first
            || a.calls[i].symbol_len != b.calls[i].symbol_len || a.calls[i].arg_first != b.calls[i].arg_first
            || a.calls[i].arg_count != b.calls[i].arg_count) { return 0; }
        i += 1;
    }
    i = 0;
    for i < a.call_arg_count {
        if (a.call_args[i].value != b.call_args[i].value || a.call_args[i].type_id != b.call_args[i].type_id) { return 0; }
        i += 1;
    }
    i = 0;
    for i < a.call_symbol_size { if (a.call_symbols[i] != b.call_symbols[i]) { return 0; } i += 1; }
    i = 0;
    for i < a.block_count {
        if (a.blocks[i].id != b.blocks[i].id || a.blocks[i].first_inst != b.blocks[i].first_inst
            || a.blocks[i].inst_count != b.blocks[i].inst_count || a.blocks[i].term != b.blocks[i].term
            || a.blocks[i].term_value != b.blocks[i].term_value || a.blocks[i].succ0 != b.blocks[i].succ0
            || a.blocks[i].succ1 != b.blocks[i].succ1) { return 0; }
        i += 1;
    }
    return 1;
}

// same_module：比较原模块与反序列化副本的全部主要字段；返回 0 或首个不一致的段号。
fn same_module(a *ir.IRModule, b *ir.IRModule) int {
    if (a.version != b.version || a.target.key != b.target.key
        || a.target.pointer_bits != b.target.pointer_bits
        || a.target.little_endian != b.target.little_endian
        || a.target.layout_version != b.target.layout_version
        || same_text(a.target.triple, b.target.triple) == 0
        || same_text(a.target.data_layout, b.target.data_layout) == 0
        || same_text(a.target.abi, b.target.abi) == 0) { return 1; }
    if (a.source_count != b.source_count || a.type_count != b.type_count
        || a.symbol_count != b.symbol_count || a.global_count != b.global_count
        || a.function_count != b.function_count) { return 2; }
    let i int = 0;
    for i < a.source_count {
        if (a.sources[i].length != b.sources[i].length
            || same_text(a.sources[i].path, b.sources[i].path) == 0) { return 3; }
        let j int = 0;
        for j < a.sources[i].length {
            if (a.sources[i].text[j] != b.sources[i].text[j]) { return 3; }
            j += 1;
        }
        i += 1;
    }
    i = 0;
    for i < a.type_count {
        if (a.types[i].kind != b.types[i].kind || a.types[i].bits != b.types[i].bits
            || a.types[i].size != b.types[i].size || a.types[i].align != b.types[i].align
            || a.types[i].elem != b.types[i].elem || a.types[i].count != b.types[i].count
            || a.types[i].abi != b.types[i].abi || a.types[i].variadic != b.types[i].variadic
            || a.types[i].field_count != b.types[i].field_count
            || same_text(a.types[i].name, b.types[i].name) == 0) { return 4; }
        let j int = 0;
        for j < a.types[i].field_count {
            if (a.types[i].fields[j].type_id != b.types[i].fields[j].type_id
                || a.types[i].fields[j].offset != b.types[i].fields[j].offset) { return 4; }
            j += 1;
        }
        i += 1;
    }
    i = 0;
    for i < a.symbol_count {
        if (a.symbols[i].kind != b.symbols[i].kind || a.symbols[i].type_id != b.symbols[i].type_id
            || a.symbols[i].param_count != b.symbols[i].param_count
            || a.symbols[i].abi != b.symbols[i].abi || a.symbols[i].variadic != b.symbols[i].variadic
            || a.symbols[i].no_return != b.symbols[i].no_return
            || a.symbols[i].linkage != b.symbols[i].linkage || a.symbols[i].defined != b.symbols[i].defined
            || a.symbols[i].mutable != b.symbols[i].mutable || a.symbols[i].source != b.symbols[i].source
            || a.symbols[i].offset != b.symbols[i].offset
            || same_text(a.symbols[i].name, b.symbols[i].name) == 0) { return 5; }
        let j int = 0;
        for j < a.symbols[i].param_count {
            if (a.symbols[i].params[j] != b.symbols[i].params[j]) { return 5; }
            j += 1;
        }
        i += 1;
    }
    i = 0;
    for i < a.global_count {
        if (a.globals[i].symbol != b.globals[i].symbol || a.globals[i].size != b.globals[i].size
            || a.globals[i].align != b.globals[i].align
            || a.globals[i].reloc_count != b.globals[i].reloc_count) { return 6; }
        let j int = 0;
        for j < a.globals[i].size {
            if (a.globals[i].data[j] != b.globals[i].data[j]) { return 6; }
            j += 1;
        }
        j = 0;
        for j < a.globals[i].reloc_count {
            if (a.globals[i].relocs[j].offset != b.globals[i].relocs[j].offset
                || a.globals[i].relocs[j].width != b.globals[i].relocs[j].width
                || a.globals[i].relocs[j].symbol != b.globals[i].relocs[j].symbol
                || a.globals[i].relocs[j].addend != b.globals[i].relocs[j].addend) { return 6; }
            j += 1;
        }
        i += 1;
    }
    i = 0;
    for i < a.function_count {
        if (a.functions[i].symbol != b.functions[i].symbol
            || a.functions[i].type_map_count != b.functions[i].type_map_count
            || a.functions[i].loc_count != b.functions[i].loc_count
            || same_body(&a.functions[i].body, &b.functions[i].body) == 0) { return 7; }
        let j int = 0;
        for j < a.functions[i].type_map_count {
            if (a.functions[i].type_map[j] != b.functions[i].type_map[j]) { return 8; }
            j += 1;
        }
        j = 0;
        for j < a.functions[i].loc_count {
            if (a.functions[i].locs[j].source != b.functions[i].locs[j].source
                || a.functions[i].locs[j].offset != b.functions[i].locs[j].offset) { return 8; }
            j += 1;
        }
        i += 1;
    }
    return 0;
}

// module_zeroed：确认反序列化失败后 out 保持零初始化。
fn module_zeroed(unit *ir.IRModule) int {
    return unit.version == 0 && unit.functions == 0 && unit.sources == 0 && unit.types == 0
        && unit.symbols == 0 && unit.globals == 0 && unit.function_count == 0
        && unit.source_count == 0 && unit.type_count == 0 && unit.symbol_count == 0
        && unit.global_count == 0 && unit.target.triple == 0
        && unit.target.data_layout == 0 && unit.target.abi == 0 ? 1 : 0;
}

// check_roundtrip：往返一致 + 确定性 + 容量不足不写。
fn check_roundtrip() int {
    let unit ir.IRModule;
    if (build_module(&unit, 2) != 0) { return 1; }
    let size int = ir.ir_module_serialized_size(&unit);
    if (size <= 208) { return 2; }
    let first [4096]u8;
    let second [4096]u8;
    let i int = 0;
    for i < 4096 { first[i] = 0xAA; second[i] = 0xAA; i += 1; }
    if (ir.ir_module_serialize(&unit, &first[0], size - 1) != -1) { return 3; }
    i = 0;
    for i < 4096 { if (first[i] != 0xAA) { return 4; } i += 1; }
    if (ir.ir_module_serialize(&unit, &first[0], size) != size) { return 5; }
    let copy ir.IRModule;
    if (ir.ir_module_deserialize(&copy, &first[0], size) != 0) { return 6; }
    if (ir.ir_module_verify(&copy) != 0) { return 7; }
    let diff int = same_module(&unit, &copy);
    if (diff != 0) { return 8 + diff; }
    if (ir.ir_module_serialize(&copy, &second[0], size) != size) { return 20; }
    if (same_bytes(&first[0], &second[0], size) == 0) { return 21; }
    // 再独立构造一次同样的模块：字节必须逐字节相同（确定性）。
    let again ir.IRModule;
    if (build_module(&again, 2) != 0) { return 22; }
    if (ir.ir_module_serialize(&again, &second[0], size) != size) { return 23; }
    if (same_bytes(&first[0], &second[0], size) == 0) { return 24; }
    // 已有内容的 out 必须拒绝，且不破坏原模块。
    if (ir.ir_module_deserialize(&copy, &first[0], size) != -1) { return 25; }
    if (same_module(&unit, &copy) != 0) { return 26; }
    // 不合法模块不可序列化。
    unit.target.key = 1;
    if (ir.ir_module_serialized_size(&unit) != -1) { return 27; }
    if (ir.ir_module_serialize(&unit, &second[0], size) != -1) { return 28; }
    unit.target.key = 2;
    if (ir.ir_module_serialized_size(&unit) != size) { return 29; }
    // 空模块（五张表全空）也必须往返：覆盖全部零计数与空 blob 路径。
    let empty ir.IRModule;
    let empty_target ir.IRModuleTarget;
    make_target(&empty_target, 2);
    if (ir.ir_module_init(&empty, &empty_target) != 0) { return 30; }
    let empty_size int = ir.ir_module_serialized_size(&empty);
    if (empty_size <= 208 || ir.ir_module_serialize(&empty, &second[0], empty_size) != empty_size) { return 31; }
    let empty_copy ir.IRModule;
    if (ir.ir_module_deserialize(&empty_copy, &second[0], empty_size) != 0) { return 32; }
    if (ir.ir_module_verify(&empty_copy) != 0 || same_module(&empty, &empty_copy) != 0) { return 33; }
    if (ir.ir_module_serialize(&empty_copy, &first[0], empty_size) != empty_size) { return 34; }
    if (same_bytes(&second[0], &first[0], empty_size) == 0) { return 35; }
    ir.ir_module_release(&empty_copy);
    ir.ir_module_release(&empty);
    ir.ir_module_release(&copy);
    ir.ir_module_release(&again);
    ir.ir_module_release(&unit);
    printf("roundtrip=ok\n");
    printf("size=%d\n", size);
    return 0;
}

// check_rejects：十一类坏输入必须各自返回 -1 且 out 保持零初始化。
// 每个用例都从完整合法字节串出发，只改一处，因此失败原因唯一。
fn check_rejects() int {
    let unit ir.IRModule;
    if (build_module(&unit, 2) != 0) { return 1; }
    let size int = ir.ir_module_serialized_size(&unit);
    let buf [4096]u8;
    let original [4096]u8;
    if (size <= 208 || size > 4096) { return 2; }
    if (ir.ir_module_serialize(&unit, &buf[0], size) != size) { return 3; }
    let original_i int = 0;
    for original_i < size { original[original_i] = buf[original_i]; original_i += 1; }
    let out ir.IRModule;
    let reloc_section int = section_offset(&unit, 6);
    let global_section int = section_offset(&unit, 5);
    let source_section int = section_offset(&unit, 0);
    let blob_base int = section_offset(&unit, 10);
    let path_start int = blob_base + text_size(unit.target.triple)
        + text_size(unit.target.data_layout) + text_size(unit.target.abi);
    let cases int = 0;
    // 0：截断（长度少一字节）
    if (ir.ir_module_deserialize(&out, &buf[0], size - 1) != -1 || module_zeroed(&out) == 0) { return 10; }
    cases += 1;
    // 1：错误 magic
    buf[0] = buf[0] ^ 1;
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 11; }
    buf[0] = buf[0] ^ 1;
    cases += 1;
    // 2：未知序列化格式版本
    put_word(&buf[0], 8, ir.IR_MODULE_SERIAL_VERSION + 1);
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 12; }
    put_word(&buf[0], 8, ir.IR_MODULE_SERIAL_VERSION);
    cases += 1;
    // 3：未知内存模块版本（与 verify 的版本硬门不一致）
    put_word(&buf[0], 16, 2);
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 13; }
    put_word(&buf[0], 16, get_word(&original[0], 16));
    cases += 1;
    // 4：头部长度越界（字 20 = 来源路径总长 +8，总长与 size 不再相等）
    put_word(&buf[0], 160, get_word(&buf[0], 160) + 8);
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 14; }
    put_word(&buf[0], 160, get_word(&buf[0], 160) - 8);
    cases += 1;
    // 5：计数越界（字 10 = 来源数远超单表上限）
    put_word(&buf[0], 80, 1099511627776);
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 15; }
    put_word(&buf[0], 80, 2);
    cases += 1;
    // 6：非法索引——重定位指向不存在的符号
    put_word(&buf[0], reloc_section + 16, 99);
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 16; }
    put_word(&buf[0], reloc_section + 16, 2);
    cases += 1;
    // 7：非法索引——全局实体指向不存在的符号
    put_word(&buf[0], global_section, 99);
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 17; }
    put_word(&buf[0], global_section, 0);
    cases += 1;
    // 8：目标键与 triple 不一致（字 3 = 目标键改成 aarch64）
    put_word(&buf[0], 24, 1);
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 18; }
    put_word(&buf[0], 24, 2);
    cases += 1;
    // 9：描述符长度和与头部总数不一致（来源路径长度 +8）
    put_word(&buf[0], source_section, get_word(&buf[0], source_section) + 8);
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 19; }
    put_word(&buf[0], source_section, get_word(&buf[0], source_section) - 8);
    cases += 1;
    // 10：名字含内部零字节（第一个零不在末字节）
    buf[path_start + 1] = 0;
    if (ir.ir_module_deserialize(&out, &buf[0], size) != -1 || module_zeroed(&out) == 0) { return 30; }
    buf[path_start + 1] = 'c';
    cases += 1;
    // 恢复后必须仍然成功，证明以上失败都来自被改动的那一处。
    if (same_bytes(&buf[0], &original[0], size) == 0) { return 31; }
    if (ir.ir_module_deserialize(&out, &buf[0], size) != 0) { return 31; }
    if (ir.ir_module_verify(&out) != 0 || same_module(&unit, &out) != 0) { return 32; }
    ir.ir_module_release(&out);
    ir.ir_module_release(&unit);
    printf("rejects=ok\n");
    printf("cases=%d\n", cases);
    return 0;
}

// check_identity：同一内容两次构造摘要相同；改函数常量或改目标后摘要必须变化。
fn check_identity() int {
    let a ir.IRModule;
    let b ir.IRModule;
    let c ir.IRModule;
    if (build_module(&a, 2) != 0 || build_module(&b, 2) != 0) { return 1; }
    let ida [33]u8;
    let idb [33]u8;
    let idc [33]u8;
    if (ir.ir_module_identity(&a, &ida[0], 33) != ir.IR_MODULE_IDENTITY_HEX) { return 2; }
    if (ir.ir_module_identity(&b, &idb[0], 33) != ir.IR_MODULE_IDENTITY_HEX) { return 3; }
    if (same_text((&ida[0]).to_type(*char), (&idb[0]).to_type(*char)) == 0) { return 4; }
    // 容量不足必须拒绝，且不写半个摘要。
    idb[0] = 'z'; idb[32] = 'z';
    if (ir.ir_module_identity(&b, &idb[0], 32) != -1) { return 5; }
    if (idb[0] != 'z' || idb[32] != 'z') { return 6; }
    // 改一个函数的常量：摘要必须变化。
    a.functions[0].body.insts[1].imm = 43;
    if (ir.ir_module_identity(&a, &idc[0], 33) != ir.IR_MODULE_IDENTITY_HEX) { return 7; }
    if (same_text((&ida[0]).to_type(*char), (&idc[0]).to_type(*char)) != 0) { return 8; }
    a.functions[0].body.insts[1].imm = 42;
    if (ir.ir_module_identity(&a, &idc[0], 33) != ir.IR_MODULE_IDENTITY_HEX) { return 9; }
    if (same_text((&ida[0]).to_type(*char), (&idc[0]).to_type(*char)) == 0) { return 10; }
    // 改目标（aarch64 Linux）：摘要必须变化。
    if (build_module(&c, 1) != 0) { return 11; }
    if (ir.ir_module_identity(&c, &idc[0], 33) != ir.IR_MODULE_IDENTITY_HEX) { return 12; }
    if (same_text((&ida[0]).to_type(*char), (&idc[0]).to_type(*char)) != 0) { return 13; }
    // 不合法模块（目标键与 triple 不一致）不产生身份摘要；恢复后摘要回到原值。
    a.target.key = 1;
    if (ir.ir_module_identity(&a, &idc[0], 33) != -1) { return 14; }
    a.target.key = 2;
    if (ir.ir_module_identity(&a, &ida[0], 33) != ir.IR_MODULE_IDENTITY_HEX) { return 15; }
    printf("identity-a=%s\n", &ida[0]);
    printf("identity-arm64=%s\n", &idc[0]);
    ir.ir_module_release(&c);
    ir.ir_module_release(&b);
    ir.ir_module_release(&a);
    return 0;
}

// main：三个阶段各自带独立阶段码，失败时打印出来便于定位。
fn main() int {
    let status int = check_roundtrip();
    if (status != 0) { printf("roundtrip-fail=%d\n", status); return 50 + status; }
    status = check_rejects();
    if (status != 0) { printf("reject-fail=%d\n", status); return 100 + status; }
    status = check_identity();
    if (status != 0) { printf("identity-fail=%d\n", status); return 150 + status; }
    printf("module-cache=ok\n");
    return 0;
}
'''


def run(command, cwd, timeout=300):
    """运行编译器或产物，保留原始 stdout/stderr 供门禁诊断。"""
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def main():
    """构建隔离项目（真实 compiler/ir）并运行模块缓存探针。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler-path", default=str(ROOT / "yh"))
    args = parser.parse_args()
    compiler = Path(args.compiler_path).resolve()
    project = WORK / "cache"
    WORK.mkdir(parents=True, exist_ok=True)
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(ROOT / "tests/modules/projects/llvmmodule", project)
    shutil.copytree(ROOT / "compiler/ir", project / "ir")
    (project / "ir/project.toml").write_text('[project]\nname = "ir"\nsource = "."\n')
    (project / "main/main.yh").write_text(FIXTURE.lstrip("\n"))
    result = run([str(compiler), "build"], project)
    (WORK / "build.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    result = run([str(project / ".build/llvmmodule")], project)
    (WORK / "run.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    # 第二次在新进程里重跑：身份/长度/用例计数必须逐字节一致（跨进程稳定）。
    again = run([str(project / ".build/llvmmodule")], project)
    (WORK / "run-again.log").write_text(again.stdout + again.stderr)
    assert again.returncode == 0 and again.stdout == result.stdout, (again.returncode, again.stdout)
    lines = result.stdout.splitlines()
    assert lines and lines[-1] == "module-cache=ok", (result.returncode, result.stdout, result.stderr)
    fields = dict(line.split("=", 1) for line in lines[:-1] if "=" in line)
    identity = re.fullmatch(r"[0-9a-f]{32}", fields.get("identity-a", ""))
    assert identity, result.stdout
    assert fields.get("cases") == "11", result.stdout
    assert fields.get("rejects") == "ok", result.stdout
    assert fields.get("roundtrip") == "ok", result.stdout
    assert int(fields.get("size", "0")) > 208, result.stdout
    assert fields.get("identity-arm64") != fields.get("identity-a"), result.stdout
    (WORK / "report.json").write_text(json.dumps({
        "roundtrip": "ok", "deterministic_bytes": True, "reject_cases": 11,
        "identity_x86_64": fields["identity-a"], "identity_aarch64": fields["identity-arm64"],
        "cross_process_stable": True, "serialized_size": int(fields["size"]),
        "compiler": str(compiler),
        "scope": "模块级序列化/反序列化/身份；函数体复用 ir_serialize 稳定编码",
    }, ensure_ascii=False, indent=2) + "\n")
    print("LL2 模块缓存门通过：往返一致/逐字节确定/11 类坏输入拒绝/身份稳定 "
          f"(size={fields['size']} identity={fields['identity-a']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
