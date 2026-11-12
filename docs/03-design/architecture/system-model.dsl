// yh（玉衡）编译器工具链 —— 当前架构全景模型
// 快照：2026-11-10，llvm 分支 HEAD 13d3bd4 + 未提交的 errors 重构（工作区状态）
// 产出技能：system-modeler + c4model；证据索引见 system-model.evidence.md
// 视图：SystemContext（L1 边界）、Containers（L2 复合体组成）
// 模块级 drill-down 见 compiler-modules.dot / stdlib-modules.dot（Graphviz）
workspace "yh 编译器工具链" "当前状态架构模型（2026-11-10 工作区快照）" {

    model {
        developer = person "yh 开发者" "编写 yh 程序、运行 just 门禁与发布流程的开发者"
        github = softwareSystem "GitHub Releases / Actions" "种子与发布资产托管；四端原生 CI runner" "external"
        hostSdk = softwareSystem "宿主平台 SDK" "Darwin 真实 SDKROOT（libc++）、Linux glibc、Windows MSVC/SDK" "external"
        antlr = softwareSystem "ANTLR 参考语法" "Java + antlr jar；仅本机语法门，CI 显式关闭（YH_ANTLR=0）" "external"
        userProject = softwareSystem "用户 yh 项目" ".yh 源码 + project.toml 清单" "external"

        yh = softwareSystem "yh 编译器工具链" "语言 + 前端 + SSA IR + LLVM 后端 + 构建系统 + 标准库 + 自举/发布流水线的复合体" {
            compiler = container "yh 编译器" "单二进制：CLI 分派、受检前端、SSA IR、LLVM IR 发射、构建编排、链接驱动" "yh 语言 / 内嵌 LLVM 21 + lld"
            stdlib = container "标准库 yh_libs" "sys→os→io/net/cli/fmt/json/toml 分层模块；源码形态随编译器分发" "yh 源码"
            seed = container "上一代种子" "bin/yh-<平台>-<架构>；不入库，从最新带资产 Release 下载并核对 SHA-256" "二进制"
            closure = container "LLVM/lld 静态闭包" "compiler/llvm C/C++ 桥 + 固定版 LLVM/lld 静态归档；构建机准备，不烘焙进种子" "C/C++ / 静态归档"
            orchestrator = container "构建与门禁编排" "justfile 唯一真源 + tools/*.py：两代自举、三层回归、ci-gate、发布打包" "just / Python"
            tests = container "测试套件" "Python harness 驱动 .yh 语料：语法/运行/模块/自举固定点/性能/平台专项" "Python / yh"
            cacheStore = container "构建缓存" "项目 .build/（产物与索引）+ YH_CACHE 全局内容寻址 store（ActionID/OutputID）" "文件 / 内容寻址" "database"
        }

        developer -> compiler "运行 yh build/run/test/check/cache" "CLI"
        developer -> orchestrator "just dev/test/bootstrap/ci-gate" "just"
        compiler -> userProject "读取 .yh 与 project.toml，写入 .build 产物" "文件"
        compiler -> stdlib "三层来源解析：本项目 → 标准库 → 直接依赖" "源码 import"
        compiler -> closure "进程内 C ABI 调桥发射 .o；内嵌 lld 链接" "C ABI"
        compiler -> cacheStore "读写模块/函数 IR/链接缓存；发布 .s.i/.s.ct 接口" "文件"
        compiler -> hostSdk "Darwin 链接回退真实 SDK 解析 -lc++；Windows 导入库" "平台链接"
        orchestrator -> seed "tools/fetch-release-seed.py 取种到 bin/" "HTTPS"
        seed -> compiler "tools/seed-build.py 驱动种子冷编 compiler/ 源码" "yh build"
        orchestrator -> closure "just llvm-host 按平台准备/校验闭包" "Python 准备器"
        orchestrator -> tests "门禁配方调用 harness 脚本" "子进程"
        tests -> compiler "驱动执行语料与两代固定点自举" "子进程"
        tests -> antlr "参考语法层（仅本机，YH_ANTLR=1）" "Java"
        orchestrator -> github "取种子 / publish-release.py 上传资产" "HTTPS"
        github -> orchestrator "ci.yml / release.yml 调用 just ci-gate" "Actions runner"
    }

    views {
        systemContext yh "SystemContext" "L1：系统边界、使用者与外部系统" {
            include developer github hostSdk antlr userProject yh
            autoLayout tb
        }

        container yh "Containers" "L2：工具链复合体的六个组成单元与关键关系" {
            include *
            autoLayout tb
        }

        styles {
            element "Person" {
                shape Person
                background #08427b
                color #ffffff
            }
            element "Software System" {
                background #1168bd
                color #ffffff
            }
            element "Container" {
                background #438dd5
                color #ffffff
            }
            element "external" {
                background #8a8a8a
                color #ffffff
            }
            element "database" {
                shape Cylinder
                background #438dd5
                color #ffffff
            }
        }
    }
}