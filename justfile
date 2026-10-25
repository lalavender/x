# --------------------------------------------------------------------------
# yh（玉衡）编译器 —— 自举构建（just 是唯一真源）
#
# 编译器就是 yh：由种子 bin/yh-<平台>-<架构>（上一版编译器二进制，不入库，
# 首次 just fetch-seed 下载）对 compiler/ 多模块项目 yh build 产出，形态随
# 宿主（Darwin → Mach-O，Linux → ELF）。每个版本直接用上一个版本的二进制
# 编译（无 C 编译步骤、无 stage0）：
#
#   just                 源文件比 yh 新时冷编（等价旧 make 默认目标）
#   just build           强制冷编
#   just dev             增量构建（保留 compiler/.build）
#   just seed            滚种子：写入当前宿主平台种子并记录 SHA-256
#   just test            三层回归（ANTLR + 编译器语法 + 运行语义）
#   just quick           日常迭代门（ANTLR + 编译器语法语料，约 20s）
#   just libs-test       libs 自有测试（test 块 + cli/os/libc 外部 runner）
#   just libs-test-o2    同一批 test 块在 O2 下重跑
#   just selfhost-native 本机全套门（候选两代固定点 + 全量语料，无需容器）
#   just full            滚种子前的全量门（= test + selfhost-native）
#   just install         安装到 PREFIX（默认 /usr/local；DESTDIR 用作打包根）
#   just uninstall       卸载
#   just explorer        启动 yh Compiler Explorer（本地浏览器图形界面）
#   just llvm-host       准备内嵌静态 LLVM 宿主（LL3；首次需要联网取固定 SDK）
#   just bootstrap       准备固定 LLVM 宿主后冷编（首次/换机的一条命令）
#   just clean           清理
#
# 命令行覆盖（just 的变量覆盖，等价旧 make 的 VAR=值）：
#   just build SEED=bin/yh-linux-arm64
#   just selfhost-native SKIP_CORPUS=1
#   just install DESTDIR=/tmp/root PREFIX=/usr
# 环境变量形式同样生效（SKIP_CORPUS=1 just selfhost-native）。
#
# 内嵌静态 LLVM（LL3，见 docs/02-plan/yh-LLVM后端替换实施方案.md）：
# 根目录 yh 由种子冷编，最终链接发生在编译器内部（compiler/cmd/link_cache.yh
# 的 mb_link），按目标平台使用 clang/gcc。因此这里让 tools/seed-build.py 调宿主
# 驱动生成链接包装器目录，并**只对种子构建子进程**前置 PATH/YH_CC：编译
# （clang/gcc -c）原样透传，最终链接改用固定工具链并追加桥归档与静态 LLVM
# 参数。链接哪个架构由种子文件名决定（x86_64 宿主上用 bin/yh-linux-arm64 时
# 产物仍是 aarch64 ELF）。
#
#   YH_LLVM_HOST=auto（默认）宿主已准备才链入；缺少固定闭包时打印明确诊断；
#   YH_LLVM_HOST=1 显式要求：必要时联网准备固定 SDK，准备不了则构建失败；
#   YH_LLVM_HOST=0 关闭（不准备固定闭包；种子无内置闭包时链接会明确报错）。
# 自举闭包由构建机提供：tools/llvm-darwin-host.py prepare 生成的
# selfhost-flags.txt 经 YH_LLVM_SELFHOST_FLAGS 传给种子（Zig 式：闭包路径
# 属于构建环境，不烘焙进种子）。
# --------------------------------------------------------------------------

set shell := ["bash", "-euo", "pipefail", "-c"]

# 仓库根：所有命令都以绝对路径引用，避免子过程 cwd 变化导致的相对路径漂移。
root := justfile_directory()
host_os := os()
cpu := arch()

# 种子文件名按「yh-<平台>-<架构>」：Darwin/arm64 → darwin-arm64，
# Linux/arm64 → linux-arm64，Linux/x64 → linux-x64。
seed_arch := if cpu == "aarch64" { "arm64" } else if cpu == "arm64" { "arm64" } else if cpu == "x86_64" { "x64" } else if cpu == "amd64" { "x64" } else { cpu }
host_tag := if host_os == "macos" { "darwin" } else if host_os == "linux" { "linux" } else { lowercase(host_os) }
bin_seed := root + "/bin/yh-" + host_tag + "-" + seed_arch

# 编译、验证和滚动使用同一个宿主平台种子；显式 SEED 可用于 CI 的临时种子。
SEED := env_var_or_default("SEED", bin_seed)
seed := if SEED == "" { bin_seed } else { SEED }
seed_abs := absolute_path(seed)
SEED_DEST := env_var_or_default("SEED_DEST", bin_seed)
seed_dest := if SEED_DEST == "" { bin_seed } else { SEED_DEST }
seed_dest_abs := absolute_path(seed_dest)

# 从最新 GitHub Release 取本机平台种子时的平台名；Linux/x86_64 种子默认
# 不入库，开发机先执行 just fetch-seed 或显式设置 SEED。
seed_platform := if host_os == "macos" { "darwin-arm64" } else if seed_arch == "arm64" { "linux-arm64" } else { "linux-x86_64" }

yh := root + "/yh"
yh_abs := absolute_path("yh")

# 快速暂存目录（2026-10-15）：语料门每个用例都要 exec 一遍 70MB 量级的编译器，
# 仓库挂在 9p/网络盘上时每次读二进制要 0.2–0.4s。把编译器与语料产物放到系统
# 临时目录（Linux /tmp 为 ext4/tmpfs、macOS $TMPDIR 为 APFS）后实测单次调用
# 665ms→464ms、整用例 939ms→703ms（约 −25%）。FAST_STAGE=0 关闭暂存。
FAST_STAGE := env_var_or_default("FAST_STAGE", "1")
fast_stage := if FAST_STAGE == "" { "1" } else { FAST_STAGE }
tmpdir := if env_var_or_default("TMPDIR", "") == "" { "/tmp" } else { env_var_or_default("TMPDIR", "/tmp") }
run_id := env_var_or_default("GITHUB_RUN_ID", "")
# 每次 CI run 独占一个快速目录：同机并发跑多个 run 时共用 /tmp/yh-fast 会让
# stage-yh 互相覆盖（release 与分支门同时跑时出现过 selfhost 探针读错二进制）。
FAST_DIR := env_var_or_default("FAST_DIR", tmpdir + "/yh-fast" + (if run_id == "" { "" } else { "-" + run_id }))
fast_dir := if FAST_DIR == "" { tmpdir + "/yh-fast" } else { FAST_DIR }
# 一律用绝对路径：harness 里 subprocess 不带 cwd，相对路径不会走 PATH 查找。
yh_run := if fast_stage == "1" { absolute_path(fast_dir + "/yh") } else { yh_abs }
run_work_flag := if fast_stage == "1" { "--workdir " + absolute_path(fast_dir + "/yh-run-work") } else { "" }
modcheck_work_flag := if fast_stage == "1" { "--workdir " + absolute_path(fast_dir + "/modcheck") } else { "" }

# SELFHOST_WORKDIR/SELFHOST_KEEP 供 Release CI 保留 cc4 自举候选：
#   just selfhost-native SELFHOST_KEEP=1 SELFHOST_WORKDIR=dist/selfhost
# 默认不保留，保持日常门临时目录/清理行为。
SELFHOST_KEEP := env_var_or_default("SELFHOST_KEEP", "0")
selfhost_keep := if SELFHOST_KEEP == "" { "0" } else { SELFHOST_KEEP }
selfhost_keep_flag := if selfhost_keep == "1" { "--keep" } else { "" }
SELFHOST_WORKDIR := env_var_or_default("SELFHOST_WORKDIR", "")
selfhost_work_flag := if SELFHOST_WORKDIR == "" { if fast_stage == "1" { "--workdir " + absolute_path(fast_dir + "/selfhost") } else { "" } } else { "--workdir " + absolute_path(SELFHOST_WORKDIR) }

# SKIP_CORPUS=1：同一轮里 just test 已经跑过等价语料时，省掉自举门里重复的
# 那遍（约 1 分钟）。默认 0——门保持最严，重复跑一遍不省。
SKIP_CORPUS := env_var_or_default("SKIP_CORPUS", "0")
skip_corpus := if SKIP_CORPUS == "" { "0" } else { SKIP_CORPUS }
corpus_flag := if skip_corpus == "1" { "--skip-corpus" } else { "" }

# LL10：x86_64 LLVM 语料与原生连续自举门。只在 Linux/x86_64 启动；
# A 由 ARM64 种子经 qemu 交叉生成，B/C/D 均直接原生运行。
LLVM_TARGET := env_var_or_default("LLVM_TARGET", "x86_64-unknown-linux-gnu")
LLVM_SEED := env_var_or_default("LLVM_SEED", root + "/bin/yh-linux-arm64")
LLVM_JOBS := env_var_or_default("LLVM_JOBS", "2")
llvm_jobs := if LLVM_JOBS == "" { "2" } else { LLVM_JOBS }
llvm_run_flags := "--backend llvm --target " + LLVM_TARGET

# 内嵌静态 LLVM：开关（auto/1/0）与宿主架构。宿主只按**种子文件名**判定，
# 因为 SEED_ARCH 随宿主架构而 SEED 可被显式覆盖（x86_64 宿主上默认种子里
# 没有 x64 后端，必须显式用 bin/yh-linux-arm64，此时产物是 aarch64 ELF）。
# replace() 判断等价旧 Makefile 的 $(findstring ...)：把命中串替换后与自身
# 比较，相同说明没命中。
seed_file := file_name(seed)
seed_has_arm := if replace(seed_file, "arm64", "") == seed_file { if replace(seed_file, "aarch64", "") == seed_file { "0" } else { "1" } } else { "1" }
seed_has_x64 := if replace(seed_file, "x64", "") == seed_file { "0" } else { "1" }
seed_has_darwin_arm := if replace(seed_file, "darwin-arm64", "") == seed_file { "0" } else { "1" }
llvm_host := if host_os == "linux" { if seed_has_arm == "1" { "linux-aarch64" } else if seed_has_x64 == "1" { "linux-x86_64" } else { "" } } else if host_os == "macos" { if seed_has_darwin_arm == "1" { "darwin-aarch64" } else { "" } } else { "" }
YH_LLVM_HOST := env_var_or_default("YH_LLVM_HOST", "auto")
llvm_mode := if YH_LLVM_HOST == "1" { "require" } else if YH_LLVM_HOST == "0" { "off" } else { "auto" }
llvm_host_flags := if llvm_host == "" { "" } else { "--llvm-host " + llvm_host + " --llvm-mode " + llvm_mode }

# LLVM 闭包缓存根：显式 YH_LLVM_CACHE 优先，否则仓库 tmp/llvm-migration，
# 再否则复用同一 Git 仓库主 worktree 的缓存（见 tools/llvm_cache.py）。
cache_env := env_var_or_default("YH_LLVM_CACHE", "")
cache_root := if cache_env == "" { `python3 tools/llvm_cache.py 2>/dev/null || echo tmp/llvm-migration` } else { cache_env }
export YH_LLVM_CACHE := cache_root

# Darwin 测试/自举统一使用随编译器分发的 SDK stub；显式 SDKROOT 仍优先。
# 固定 SDK 一旦准备好，就用它记录里的 SDKROOT：自举闭包末尾的 -lc++ 只能由
# 宿主真实 SDK 解析（bundled stub 不含 libc++）。SDKROOT 为空串时编译器按
# 「未设置」处理（compiler/build/darwin_link.yh 的 root_len == 0 分支）。
sdkroot := if host_os == "macos" { `python3 -c 'import json,os,subprocess,sys
cache = subprocess.check_output([sys.executable, "tools/llvm_cache.py"], text=True).strip()
record = os.path.join(cache, "darwin-sdk", "sdk-darwin-aarch64", "host.json")
print(json.load(open(record))["sdk_root"] if os.path.isfile(record) else "")' 2>/dev/null || true` } else { "" }
export SDKROOT := sdkroot
darwin_sdk := if host_os == "macos" { absolute_path("compiler/darwin-sdk") } else { "" }
export YH_DARWIN_SDK := darwin_sdk

# 安装位置；DESTDIR 用作打包根（just install DESTDIR=/tmp/root PREFIX=/usr）。
PREFIX := env_var_or_default("PREFIX", "/usr/local")
prefix := if PREFIX == "" { "/usr/local" } else { PREFIX }
DESTDIR := env_var_or_default("DESTDIR", "")
destdir := DESTDIR
INSTALL := env_var_or_default("INSTALL", "install")
install_prog := if INSTALL == "" { "install" } else { INSTALL }
prefix_root := destdir + prefix

# 每平台专项门的命令：变量替旧 Makefile 里的条件赋值。
runtime_test := if llvm_host == "darwin-aarch64" { "python3 " + root + "/tests/selfhost/llvm-darwin-runtime.py --compiler-path " + yh_run } else if llvm_host == "linux-x86_64" { "python3 " + root + "/tests/selfhost/runtime-memory.py --compiler-path " + yh_run + " --llvm-x64" } else if llvm_host == "linux-aarch64" { "python3 " + root + "/tests/selfhost/llvm-linux-arm64.py --compiler-path " + yh_run } else { "python3 " + root + "/tests/selfhost/runtime-memory.py --compiler-path " + yh_run }
cache_test := if llvm_host == "darwin-aarch64" { "python3 " + root + "/tests/selfhost/llvm-darwin-cache.py --compiler-path " + yh } else if llvm_host == "linux-x86_64" { "python3 " + root + "/tests/selfhost/llvm-cache.py --compiler-path " + yh } else if llvm_host == "linux-aarch64" { "python3 " + root + "/tests/selfhost/llvm-cache.py --compiler-path " + yh + " --target aarch64-unknown-linux-gnu" } else { "python3 " + root + "/tests/selfhost/link-cache.py --compiler-path " + yh }
modcheck_flags := if llvm_host == "" { "" } else { "--backend llvm" }
selfhost_flags_test := if llvm_host == "darwin-aarch64" { "python3 " + root + "/tests/selfhost/llvm-darwin-selfhost-flags.py --compiler-path " + yh_run } else { "true" }

# 预处理：仓库内 tmp/llvm-migration 必须指向缓存根：compiler/project.toml 的
# 桥库路径按「仓库/compiler」相对书写，新 worktree 里由这里补上软链。
[private]
_prepare:
    @mkdir -p "{{ root }}/tmp"
    @if [ "{{ cache_root }}" != "{{ root }}/tmp/llvm-migration" ]; then ln -sfn "{{ cache_root }}" "{{ root }}/tmp/llvm-migration"; fi

# 默认目标：源比 yh 新时冷编，否则什么都不做（等价旧 make 默认目标）。
default: _ensure_built

# all：默认目标别名（等价 default）。
all: _ensure_built

# build：强制冷编（清除 compiler/.build，从种子完整重编）。
build: verify-seed _prepare
    rm -rf "{{ root }}/compiler/.build"
    python3 "{{ root }}/tools/seed-build.py" --compiler "{{ seed_abs }}" --project "{{ root }}/compiler" --output "{{ yh }}" {{ llvm_host_flags }}

# dev：开发迭代用增量构建。与 build 的差别是不删除 compiler/.build，
# 让编译器自己的对象/IR 缓存命中未变模块；只用于本地迭代，
# 不用于种子候选与固定点验收（那些必须冷编）。
dev: verify-seed _prepare
    python3 "{{ root }}/tools/seed-build.py" --compiler "{{ seed_abs }}" --project "{{ root }}/compiler" --output "{{ yh }}" {{ llvm_host_flags }}

# verify-seed：核对种子哈希（水合/复制损坏时尽早失败）。
verify-seed:
    python3 "{{ root }}/tools/selfhost_snapshot_gate.py" --verify-seed "{{ seed_abs }}"

# fetch-seed：从最新 GitHub Release 下载当前平台种子（写入 bin/...）。
# 私有仓库需要 GITHUB_REPOSITORY 与 GH_TOKEN/GITHUB_TOKEN；
# 种子不入库（2026-10-21 起不再使用 Git LFS），任何平台首次构建前执行。
fetch-seed:
    python3 "{{ root }}/tools/fetch-release-seed.py" --platform {{ seed_platform }}

# llvm-host：准备内嵌静态 LLVM 宿主（桥归档 + 宿主可执行文件 + 身份记录）。
# 首次需要联网取固定 SDK；之后只用缓存包，可离线重跑。
llvm-host:
    @test -n "{{ llvm_host }}" || { echo "错误: 当前种子 {{ seed }} 没有对应的固定 LLVM SDK"; exit 1; }
    @if [ "{{ llvm_host }}" = "darwin-aarch64" ]; then python3 "{{ root }}/tools/llvm-darwin-host.py" prepare --host "{{ llvm_host }}" --jobs {{ llvm_jobs }}; else python3 "{{ root }}/tools/llvm-host.py" prepare --host "{{ llvm_host }}"; fi

# bootstrap：准备固定 LLVM 宿主（幂等）后冷编，首次/换机的一条命令。
bootstrap: llvm-host _ensure_built

# seed：滚种子——把刚构建并验证过的 yh 覆盖入库种子。
# 只应在 just test 与 just selfhost-native 全绿后执行（不作为依赖，
# 防止未验证产物污染种子）。
seed:
    @cp -f "{{ yh }}" "{{ seed_dest_abs }}.tmp"
    @mv -f "{{ seed_dest_abs }}.tmp" "{{ seed_dest_abs }}"
    @if [ "{{ host_os }}" = "macos" ]; then codesign -s - -f "{{ seed_dest_abs }}" 2>/dev/null || true; fi
    @python3 "{{ root }}/tools/selfhost_snapshot_gate.py" --write-seed-hash "{{ seed_dest_abs }}"
    @echo "宿主平台种子已更新：{{ seed_dest }}"

# install：安装到 PREFIX（DESTDIR 用作打包根）。
install: _ensure_built
    #!/usr/bin/env bash
    set -euo pipefail
    {{ install_prog }} -d "{{ prefix_root }}/bin"
    {{ install_prog }} -m755 "{{ yh }}" "{{ prefix_root }}/bin"
    {{ install_prog }} -d "{{ prefix_root }}/share/yh/libs"
    (
      cd "{{ root }}/libs"
      find . -path './cli/test' -prune -o -type f \( -name '*.yh' -o -name 'project.toml' \) -print | while read -r f; do
        d="{{ prefix_root }}/share/yh/libs/$(dirname "$f")"
        {{ install_prog }} -d "$d"
        {{ install_prog }} -m644 "$f" "$d"
      done
    )
    if [[ "$(uname -s)" == Darwin ]]; then
      {{ install_prog }} -d "{{ prefix_root }}/share/yh/darwin-sdk/usr/lib"
      {{ install_prog }} -m644 compiler/darwin-sdk/usr/lib/libSystem.tbd "{{ prefix_root }}/share/yh/darwin-sdk/usr/lib/"
      {{ install_prog }} -m644 compiler/darwin-sdk/SDKSettings.json compiler/darwin-sdk/manifest.json compiler/darwin-sdk/README.md "{{ prefix_root }}/share/yh/darwin-sdk/"
    fi

# uninstall：卸载（与 install 对称）。
uninstall:
    rm -f "{{ prefix_root }}/bin/yh"
    rm -rf "{{ prefix_root }}/share/yh/libs"
    @if [ "{{ host_os }}" = "macos" ]; then rm -rf "{{ prefix_root }}/share/yh/darwin-sdk"; fi

# stage-yh：把 yh 复制到快速暂存目录（FAST_STAGE=0 时退化为空操作）。
# 先写 .tmp 再 mv，避免并发读到半个 70MB 二进制。
stage-yh: _ensure_built
    @if [ "{{ fast_stage }}" = "1" ]; then mkdir -p "{{ fast_dir }}"; cp -f "{{ yh }}" "{{ yh_run }}.tmp" && mv -f "{{ yh_run }}.tmp" "{{ yh_run }}"; fi
    @if [ "{{ host_os }}" = "macos" ] && [ "{{ fast_stage }}" = "1" ]; then ln -sfn "{{ root }}/compiler/darwin-sdk" "{{ fast_dir }}/darwin-sdk"; fi

# test：三层回归——ANTLR 参考语法 + 编译器语法模式 + 运行语义语料。
# 语料门的编译器一律用暂存副本 yh_run；ANTLR 层在单进程内解析，不需要编译器。
test: stage-yh
    python3 "{{ root }}/tests/yh/check.py"
    python3 "{{ root }}/tests/yh/check.py" --compiler --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/yh-run/check.py" --compiler "{{ yh_run }}" {{ run_work_flag }}
    python3 "{{ root }}/tests/modules/test-check.py" --compiler-path "{{ yh_run }}"
    @cd "{{ root }}/libs" && "{{ yh_run }}" test --timeout 60
    python3 "{{ root }}/tools/compiler-tests.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/fmt/interp.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/fmt-interp"
    python3 "{{ root }}/tests/tools/yh-code-stats/check.py"
    python3 "{{ root }}/tests/tools/arch-check/check.py"
    python3 "{{ root }}/tools/arch-check.py"

# quick：日常迭代门。只跑不依赖后端的语法语料（ANTLR + 编译器 --syntax-check），
# 秒级到十几秒；运行语义与自举门留给 test/full。
quick: stage-yh
    python3 "{{ root }}/tests/yh/check.py"
    python3 "{{ root }}/tests/yh/check.py" --compiler --compiler-path "{{ yh_run }}"

# test-all：旧入口别名，等价 test。
test-all: test

# test-toml：TOML 测试（API/所有权/资源/文件断言已迁入 libs/toml/99_tests.yh）。
test-toml: stage-yh
    @cd "{{ root }}/libs" && "{{ yh_run }}" test toml --timeout 60

# test-toml-conformance：固定 toml-test v2.2.0（TOML 1.1）decoder 一致性门。
test-toml-conformance: stage-yh
    python3 "{{ root }}/tests/toml/conformance.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/toml-conformance"

# test-toml-injection：在临时标准库副本注入池分配失败点，逐点验证失败原子性。
test-toml-injection: stage-yh
    python3 "{{ root }}/tests/toml/injection.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/toml-inject"

# test-toml-install：install 后从仓库外、无 YH_STDLIB 导入 toml。
test-toml-install:
    python3 "{{ root }}/tests/toml/install.py" --workdir "{{ root }}/tmp/toml-install"

# test-num：num 标准库的 Python 参考差分（D16：参考实现差分留在外部门）。
test-num: stage-yh
    python3 "{{ root }}/tests/num/reference.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/num-reference"

# test-string：string 标准库专项门（ST1–ST6，O0；含分配失败注入与参考差分）。
test-string: stage-yh
    python3 "{{ root }}/tests/string/run.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/string-test" --opt-level 0
    python3 "{{ root }}/tests/string/reference.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/string-reference" --opt-level 0

# test-string-o2：同一专项门在 O2 下重跑（较慢，单独入口）。
test-string-o2: stage-yh
    python3 "{{ root }}/tests/string/run.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/string-test-o2" --opt-level 2
    python3 "{{ root }}/tests/string/reference.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/string-reference-o2" --opt-level 2

# test-string-install：install 后从仓库外、无 YH_STDLIB 导入 string。
test-string-install:
    python3 "{{ root }}/tests/string/install.py" --workdir "{{ root }}/tmp/string-install"

# test-string-complexity：直接匹配的耗时探针（只记录，不设固定耗时门）。
test-string-complexity: stage-yh
    python3 "{{ root }}/tests/string/complexity.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/string-complexity"

# test-compiler-tests：compiler/ 内嵌 yh test 测试（需要种子支持 test 语法）。
test-compiler-tests: stage-yh
    python3 "{{ root }}/tools/compiler-tests.py" --compiler-path "{{ yh_run }}"

# test-fmt-interp：字符串插值负例门（缺 import/空表达式/未终结/spec/类型）。
test-fmt-interp: stage-yh
    python3 "{{ root }}/tests/fmt/interp.py" --compiler "{{ yh_run }}" --stdlib "{{ root }}/libs" --workdir "{{ root }}/tmp/fmt-interp"

# test-fmt-install：fmt 安装后仓库外导入与公开 API surface。
test-fmt-install:
    python3 "{{ root }}/tests/fmt/install.py" --workdir "{{ root }}/tmp/fmt-install"

# libs-test：libs/ 自有测试（test 块 + 库级外部 runner），CI 独立阶段。
# 平台差异全部由编译器按 *.linux.yh/*.darwin.yh 选择，target 不带平台参数；
# 缺 99_tests*.yh 的库只提示、不阻断（2026-10-25 决策 D9）。
libs-test: stage-yh
    @cd "{{ root }}/libs" && for d in */; do case "$d" in tmp/) continue;; esac; ls "$d"*tests*.yh >/dev/null 2>&1 || echo "提示：libs/${d%/} 还没有测试文件（99_tests*.yh 或 zz_tests*.yh）"; done
    @cd "{{ root }}/libs" && "{{ yh_run }}" test --timeout 60
    python3 "{{ root }}/libs/cli/test/run.py" --compiler "{{ yh_run }}" --workdir "{{ root }}/tmp/libs-cli"
    python3 "{{ root }}/libs/cli/test/diff.py" --compiler "{{ yh_run }}" --workdir "{{ root }}/tmp/libs-cli-diff"
    python3 "{{ root }}/libs/os/test/run.py" --compiler "{{ yh_run }}" --workdir "{{ root }}/tmp/libs-os"
    python3 "{{ root }}/libs/libc/test/run.py" --compiler "{{ yh_run }}" --workdir "{{ root }}/tmp/libs-libc"

# libs-test-o2：同一批 test 块在 O2 下重跑（外部 runner 不重复）。
# 测试构建目录不按优化级细分，为了不把 O0 的增量缓存冲掉，这里把 libs
# 复制到 tmp/libs-o2 后运行（独立项目根 = 独立 tmp/yh-test 缓存与锁）。
libs-test-o2: stage-yh
    @rm -rf "{{ root }}/tmp/libs-o2"
    @cp -R "{{ root }}/libs" "{{ root }}/tmp/libs-o2"
    @rm -rf "{{ root }}/tmp/libs-o2/tmp" "{{ root }}/tmp/libs-o2/.build"
    @cd "{{ root }}/tmp/libs-o2" && "{{ yh_run }}" -O2 test --timeout 60

# test-lib-tests：历史入口，等价于 libs-test（保留以兼容文档/脚本）。
test-lib-tests: libs-test

# selfhost-native：本机全套门（无需容器、无 stage0）。
# 旧种子迁移代 + 候选两代固定点 + 自解析/语法/运行语料 + 项目验收。
# link-cache 探针需要观测编译器调用的外部汇编/链接工具，因此它继续用
# 仓库根 yh，不能用暂存副本。
selfhost-native: stage-yh
    python3 "{{ root }}/tools/selfhost_snapshot_gate.py" --verify-seed "{{ seed_abs }}"
    python3 "{{ root }}/tests/selfhost/native-selfhost.py" --seed "{{ seed_abs }}" {{ selfhost_work_flag }} {{ corpus_flag }} {{ selfhost_keep_flag }}
    python3 "{{ root }}/tests/selfhost/scratch-isolation.py" --compiler-path "{{ yh_run }}" --jobs 4
    python3 "{{ root }}/tests/selfhost/lex-stats.py" --compiler-path "{{ yh_run }}"
    {{ runtime_test }}
    {{ selfhost_flags_test }}
    python3 "{{ root }}/tests/selfhost/check-command.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/llvm-architecture.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/llvm-function-cache.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/foreign-fs-build.py" --compiler-path "{{ yh_run }}"
    {{ cache_test }}
    python3 "{{ root }}/tests/modules/check.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/modules/test-check.py" --compiler-path "{{ yh_run }}"
    @cd "{{ root }}/libs" && "{{ yh_run }}" test --timeout 60
    python3 "{{ root }}/tools/compiler-tests.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/modules/build-check.py" --compiler-path "{{ yh_run }}" {{ modcheck_flags }} {{ modcheck_work_flag }}

# full：滚种子前的全量门（test + selfhost-native）。test 已用等价编译器跑过
# 一遍语料，selfhost-native 里重复的那遍用 SKIP_CORPUS=1 省掉（约 1 分钟）。
full: test
    @SKIP_CORPUS=1 SEED="{{ seed_abs }}" SEED_DEST="{{ seed_dest_abs }}" just selfhost-native

# llvm-isolation：bwrap + 空 PATH 验证最终 yh 不依赖系统 LLVM/lld、无外部旁车。
llvm-isolation: _ensure_built
    python3 "{{ root }}/tests/selfhost/llvm-isolation.py" --compiler "{{ root }}/bin/yh-linux-x64"

# test-llvm：LLVM x64 O0/O2 全量语法/运行/模块/项目语料、统计覆盖与专项门。
# 只认 Linux/x86_64；其他宿主明确拒绝而不是降级运行。
test-llvm: stage-yh
    @test "{{ host_os }}" = "linux" || { echo "错误: test-llvm 首期要求 Linux/x86_64"; exit 1; }
    @test "{{ cpu }}" = "x86_64" -o "{{ cpu }}" = "amd64" || { echo "错误: test-llvm 首期要求 Linux/x86_64"; exit 1; }
    python3 "{{ root }}/tests/selfhost/llvm-selfhost.py" --self-test
    python3 "{{ root }}/tests/yh/check.py" --compiler --compiler-path "{{ yh_run }}" --quiet
    python3 "{{ root }}/tests/yh-run/check.py" --compiler "{{ yh_run }}" {{ llvm_run_flags }} --opt-level 0 --quiet --jobs {{ llvm_jobs }} --workdir "{{ root }}/tmp/llvm-test/yh-run-O0"
    python3 "{{ root }}/tests/yh-run/check.py" --compiler "{{ yh_run }}" {{ llvm_run_flags }} --opt-level 2 --quiet --jobs {{ llvm_jobs }} --workdir "{{ root }}/tmp/llvm-test/yh-run-O2"
    python3 "{{ root }}/tests/modules/check.py" --compiler-path "{{ yh_run }}" {{ llvm_run_flags }} --opt-level 0 --quiet --jobs {{ llvm_jobs }}
    python3 "{{ root }}/tests/modules/check.py" --compiler-path "{{ yh_run }}" {{ llvm_run_flags }} --opt-level 2 --quiet --jobs {{ llvm_jobs }}
    python3 "{{ root }}/tests/modules/build-check.py" --compiler-path "{{ yh_run }}" {{ llvm_run_flags }} --opt-level 0 --jobs {{ llvm_jobs }} --workdir "{{ root }}/tmp/llvm-test/modcheck-O0"
    python3 "{{ root }}/tests/modules/build-check.py" --compiler-path "{{ yh_run }}" {{ llvm_run_flags }} --opt-level 2 --jobs {{ llvm_jobs }} --workdir "{{ root }}/tmp/llvm-test/modcheck-O2"
    python3 "{{ root }}/tests/selfhost/llvm-driver.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/runtime-memory.py" --compiler-path "{{ yh_run }}" --llvm-x64
    python3 "{{ root }}/tests/selfhost/llvm-lld.py"

# selfhost-llvm：执行 A→B/C/D 的 O0/O2 原生固定点；脚本在最终 D 候选上运行
# 完整语料与专项门。不依赖 stage-yh：x64 交叉种子是 arm64，root yh 会误按
# 宿主种子构建；脚本自行用 seed-build 产 x64 A。
selfhost-llvm:
    python3 "{{ root }}/tests/selfhost/llvm-selfhost.py" --seed "{{ absolute_path(LLVM_SEED) }}" --jobs {{ llvm_jobs }}

# test-llvm-linux-arm64：F1 Linux/AArch64 LLVM 运行时、C ABI、对象架构与 O0/O2。
# 只在 arm64 Linux 容器内原生运行；x64 宿主不预跑本门。
test-llvm-linux-arm64: stage-yh
    @test "{{ host_os }}" = "linux" || { echo "错误: test-llvm-linux-arm64 要求 Linux/aarch64"; exit 1; }
    @test "{{ cpu }}" = "aarch64" -o "{{ cpu }}" = "arm64" || { echo "错误: test-llvm-linux-arm64 要求 Linux/aarch64"; exit 1; }
    python3 "{{ root }}/tests/selfhost/llvm-linux-arm64.py" --compiler-path "{{ yh_run }}"

# selfhost-llvm-darwin：F2-8 原生连续自举（种子 → B/C/D LLVM，
# O0/O2 固定点 + 自解析 + 全量语料 + Darwin 专项门 + 隔离 PATH）。
# LL12 后种子即 LLVM 编出的过渡代 A，不再有 legacy 起点。
selfhost-llvm-darwin:
    @test "{{ host_os }}" = "macos" -a "{{ cpu }}" = "arm64" || { echo "错误: selfhost-llvm-darwin 要求 Darwin/ARM64"; exit 1; }
    python3 "{{ root }}/tests/selfhost/llvm-darwin-selfhost.py" --seed "{{ seed_abs }}" --jobs {{ llvm_jobs }}

# test-llvm-darwin：Darwin/ARM64 静态 SDK、弱桩兼容、LLVM 对象与 Apple ABI 探针。
test-llvm-darwin: stage-yh
    @test "{{ host_os }}" = "macos" -a "{{ cpu }}" = "arm64" || { echo "错误: test-llvm-darwin 要求 Darwin/ARM64"; exit 1; }
    python3 "{{ root }}/tests/selfhost/llvm-darwin-sdk.py"
    python3 "{{ root }}/tests/selfhost/llvm-darwin-host.py"
    python3 "{{ root }}/tools/link-closure.py" check --host darwin-aarch64
    python3 "{{ root }}/tests/selfhost/llvm-darwin-bridge.py" --compiler-path "{{ yh_run }}" --require-embedded
    python3 "{{ root }}/tests/selfhost/llvm-darwin-object.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/llvm-darwin-abi.py" --suite full --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/llvm-darwin-cache.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/llvm-darwin-default.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/llvm-darwin-bundled-sdk.py" --compiler-path "{{ yh }}"
    python3 "{{ root }}/tests/selfhost/llvm-darwin-selfhost.py" --self-test
    python3 "{{ root }}/tests/selfhost/llvm-darwin-runtime.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/llvm-darwin-selfhost-flags.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tests/selfhost/llvm-darwin-link.py" --compiler-path "{{ yh_run }}"
    python3 "{{ root }}/tools/llvm-darwin-host.py" status --host darwin-aarch64

# explorer：启动 yh Compiler Explorer（本地浏览器图形界面）。
explorer:
    python3 "{{ root }}/tools/yh-explorer.py"

# code-stats：统计 compiler/ 下 yh 源码规模；独立运行，不依赖编译器构建。
code-stats:
    python3 "{{ root }}/tools/yh-code-stats.py"

# test-code-stats：验证统计工具边界与 JSON 输出。
test-code-stats:
    python3 "{{ root }}/tests/tools/yh-code-stats/check.py"

# arch-check：依赖矩阵 + 预算守护；test-arch-check 验证守护本身能抓到违规。
arch-check:
    python3 "{{ root }}/tools/arch-check.py"

# test-arch-check：arch-check 守护的自测。
test-arch-check:
    python3 "{{ root }}/tests/tools/arch-check/check.py"

# clean：删除 yh 与编译器缓存（保留 tmp 下的 LLVM 闭包缓存）。
clean:
    rm -f "{{ yh }}"
    rm -rf "{{ root }}/compiler/.build" "{{ root }}/tmp/selfbuild-gate" "{{ root }}/tmp/selfhost" "{{ root }}/tmp/modcheck"

# help：列出全部可运行目标（等价 just --list）。
help:
    @just --list

# _ensure_built：源文件比 yh 新（或 yh 不存在）时冷编一次。
# 依赖清单等价旧 Makefile 的 $(YH) 前提：种子、compiler/ 下源码与清单、
# 固定 LLVM 锁与四个构建工具脚本。子 just 显式传变量，确保命令行覆盖
# （just test SEED=...）也作用到构建。
[private]
_ensure_built:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{ root }}"
    target="{{ yh }}"
    need=0
    if [ ! -x "$target" ]; then
      need=1
    else
      # 依赖清单等价旧 Makefile 的 $(YH) 前提；只看源，且不递归进
      # compiler/tmp（测试生成物）与 compiler/.build（构建产物），否则每次
      # 都会被自己刚写出的文件判成过期、反复冷编。
      for p in "{{ seed_abs }}" compiler/project.toml compiler/llvm vendor/llvm/sdk.lock.json \
               tools/seed-build.py tools/llvm-host.py tools/llvm-darwin-host.py tools/llvm-darwin-sdk.py; do
        [ -e "$p" ] || continue
        if [ "$p" -nt "$target" ]; then need=1; break; fi
        if [ -d "$p" ] && [ -n "$(find "$p" -type f -newer "$target" -print -quit)" ]; then need=1; break; fi
      done
      # compiler/*.yh 与 compiler/*/*.yh（旧 Makefile 的两个 wildcard 层级）。
      if [ "$need" = 0 ] && [ -n "$(find compiler -maxdepth 2 -name '*.yh' -newer "$target" -print -quit)" ]; then need=1; fi
    fi
    if [ "$need" = 1 ]; then
      exec just SEED="{{ seed }}" SEED_DEST="{{ seed_dest }}" YH_LLVM_HOST="{{ YH_LLVM_HOST }}" YH_LLVM_CACHE="{{ cache_root }}" build
    fi
