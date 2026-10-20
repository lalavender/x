#!/usr/bin/env bash
# 在 GitHub Ubuntu runner 上准备 ANTLR 4.13.2 并跑参考语法门。
#
# 平台 job 不再运行 `make test`（它隐含本机 ANTLR 环境）；ANTLR 参考语法
# 与平台无关，统一在这个 job 里跑一次。Java/pip 由调用方先安装。
set -euo pipefail

python3 -m pip install --user --break-system-packages --quiet \
    antlr4-python3-runtime==4.13.2 antlr4-tools

# check.py 约定从 Maven 缓存读取 jar；预先放好可避免 antlr4-tools 联网探测。
jar_dir="$HOME/.m2/repository/org/antlr/antlr4/4.13.2"
jar="$jar_dir/antlr4-4.13.2-complete.jar"
mkdir -p "$jar_dir"
if [[ ! -f "$jar" ]]; then
    curl -fsSL https://www.antlr.org/download/antlr-4.13.2-complete.jar -o "$jar"
fi

# pip --user 的可执行目录不一定在 PATH；check.py 自身按绝对路径找 antlr4，
# 但 antlr4 子进程也可能需要 PATH。
export PATH="$HOME/.local/bin:$PATH"

python3 - <<'PY'
import antlr4
print(f"antlr4 runtime: {antlr4.__file__}")
PY
python3 tests/yh/check.py "$@"
