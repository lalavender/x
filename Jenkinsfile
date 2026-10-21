// yh 本地 Jenkins 流水线（macOS/arm64 宿主）。
//
// 两个 job 共用本文件：
//   yh-ci      ：分支 push（arm64/llvm/main）→ ANTLR + Linux/arm64 + Darwin/arm64
//   yh-release ：版本 tag push（x.y.z）→ 三端构建 + 打包 + 发布 Release
//
// 触发：本机 .git/hooks/pre-push → tools/jenkins/trigger.py；不经 GitHub webhook。
// 凭据：github-https（clone）、github-token（取种/发布），由 tools/jenkins/setup.py 创建。
// LLVM 闭包：优先复用 $YH_LLVM_CACHE（缺省 $HOME/Documents/x/tmp/llvm-migration）；
// 缓存不存在时由 make bootstrap 自行准备（首次很慢）。
//
// 注意：Linux 端在 Apple container 里跑（arm64 原生、x86_64 模拟）；容器内构建
// 产物经 virtiofs 映射回宿主用户，不需要 chown。

def tagName = (params.TAG ?: '').trim()
def branchName = (params.BRANCH ?: '').trim()
def isRelease = tagName != ''
def isVersionTag = isRelease && (tagName ==~ /^\d+\.\d+\.\d+$/)
def isTrackedBranch = branchName in ['arm64', 'llvm', 'main'] ||
    branchName ==~ /^\d+\.\d+\.\d+-(rc|release)$/
def shouldRun = isRelease ? isVersionTag : isTrackedBranch
def refName = isRelease ? "refs/tags/${tagName}" : "refs/heads/${branchName ?: 'llvm'}"

pipeline {
  agent { label 'built-in' }
  options {
    timestamps()
    disableConcurrentBuilds()
    timeout(time: 6, unit: 'HOURS')
    buildDiscarder(logRotator(numToKeepStr: '30'))
  }
  environment {
    PATH = "/opt/homebrew/bin:/usr/local/bin:${env.PATH}"
    GITHUB_REPOSITORY = 'lalavender/x'
    YH_LLVM_HOST = '1'
    LLVM_JOBS = '4'
    YH_LLVM_CACHE = "${env.HOME}/Documents/x/tmp/llvm-migration"
  }
  stages {
    stage('判定') {
      steps {
        script {
          env.TAG = tagName
          env.BRANCH = branchName
          env.SHOULD_RUN = shouldRun ? '1' : '0'
          env.IS_RELEASE = isRelease ? '1' : '0'
          echo "ref=${refName} release=${isRelease}"
          if (!shouldRun) {
            echo '跳过：分支只构建 arm64/llvm/main；tag 只构建 x.y.z（rc tag 按 CircleCI 现状忽略）'
          }
        }
      }
    }

    stage('准备容器服务') {
      when { expression { env.SHOULD_RUN == '1' } }
      steps {
        sh '''
          set -euo pipefail
          container ls >/dev/null 2>&1 || container system start
        '''
      }
    }

    stage('检出') {
      when { expression { env.SHOULD_RUN == '1' } }
      steps {
        deleteDir()
        checkout([
          $class: 'GitSCM',
          branches: [[name: refName]],
          userRemoteConfigs: [[
            url: 'https://github.com/lalavender/x.git',
            credentialsId: 'github-https'
          ]],
          extensions: [[$class: 'CloneOption', noTags: false, shallow: false, timeout: 30]]
        ])
        // 检出后恢复共享 LLVM 闭包缓存；删 workspace 不会删缓存本体。
        sh '''
          set -euo pipefail
          if [ -n "${YH_LLVM_CACHE:-}" ] && [ -d "$YH_LLVM_CACHE" ] && [ ! -e tmp/llvm-migration ]; then
            mkdir -p tmp
            ln -s "$YH_LLVM_CACHE" tmp/llvm-migration
          fi
        '''
      }
    }

    // CircleCI 只在分支流水线跑参考语法门；tag 发布不跑。
    stage('ANTLR 语法门') {
      when { expression { env.SHOULD_RUN == '1' && env.IS_RELEASE == '0' } }
      steps {
        sh '''
          set -euo pipefail
          container run --rm -v "$WORKSPACE":/work -w /work ubuntu:24.04 bash -lc '
            set -euo pipefail
            apt-get update -qq
            DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
              python3 python3-pip default-jre-headless curl ca-certificates
            bash tools/run-antlr-ci.sh --quiet
          '
        '''
      }
    }

    // 分支和 tag 都要跑 Linux/arm64（容器原生）。
    stage('Linux/arm64') {
      when { expression { env.SHOULD_RUN == '1' } }
      steps {
        withCredentials([string(credentialsId: 'github-token', variable: 'GITHUB_TOKEN')]) {
          sh '''
            set -euo pipefail
            python3 tools/fetch-release-seed.py --platform linux-arm64 --exclude-tag "${TAG:-}"
            mount=""
            if [ -n "${YH_LLVM_CACHE:-}" ] && [ -d "$YH_LLVM_CACHE" ]; then
              mount="-v $YH_LLVM_CACHE:$YH_LLVM_CACHE"
            fi
            container run --rm -v "$WORKSPACE":/work -w /work $mount \
              -e GITHUB_TOKEN -e GITHUB_REPOSITORY -e TAG -e BRANCH \
              ubuntu:24.04 bash -lc '
                set -euo pipefail
                apt-get update -qq
                DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
                  build-essential python3 binutils xz-utils libxml2-dev zlib1g-dev libzstd-dev
                make bootstrap
                make test-llvm-linux-arm64
                python3 tests/yh/check.py --compiler --compiler-path "$PWD/yh" --quiet
                python3 tests/yh-run/check.py --compiler "$PWD/yh" --quiet --jobs "$(nproc)"
                if [ -n "${TAG:-}" ]; then
                  make selfhost-native SKIP_CORPUS=1 SELFHOST_KEEP=1 SELFHOST_WORKDIR=dist/selfhost
                  cp dist/selfhost/cc4 yh
                  rm -rf dist/selfhost
                  name="yh-${TAG}-linux-arm64"
                  stage="dist/.stage-linux-arm64"
                  mkdir -p "$stage"
                  cp yh "$stage/yh"
                  tar -czf "dist/$name.tar.gz" -C "$stage" yh
                  rm -rf "$stage"
                  (cd dist && sha256sum "$name.tar.gz" > "$name.sha256")
                else
                  make selfhost-native SKIP_CORPUS=1
                fi
              '
          '''
        }
      }
    }

    // 只在 tag 发布时跑 Linux/x86_64（Apple container 模拟）。
    stage('Linux/x86_64') {
      when { expression { env.SHOULD_RUN == '1' && env.IS_RELEASE == '1' } }
      steps {
        withCredentials([string(credentialsId: 'github-token', variable: 'GITHUB_TOKEN')]) {
          sh '''
            set -euo pipefail
            python3 tools/fetch-release-seed.py --platform linux-x86_64 --exclude-tag "${TAG:-}"
            mount=""
            if [ -n "${YH_LLVM_CACHE:-}" ] && [ -d "$YH_LLVM_CACHE" ]; then
              mount="-v $YH_LLVM_CACHE:$YH_LLVM_CACHE"
            fi
            container run --rm -a amd64 -v "$WORKSPACE":/work -w /work $mount \
              -e GITHUB_TOKEN -e GITHUB_REPOSITORY -e TAG -e BRANCH \
              ubuntu:24.04 bash -lc '
                set -euo pipefail
                apt-get update -qq
                DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
                  build-essential python3 binutils xz-utils libxml2-dev zlib1g-dev libzstd-dev clang
                make bootstrap
                make test-llvm
                python3 tests/yh/check.py --compiler --compiler-path "$PWD/yh" --quiet
                python3 tests/yh-run/check.py --compiler "$PWD/yh" --quiet --jobs "$(nproc)"
                make selfhost-native SKIP_CORPUS=1 SELFHOST_KEEP=1 SELFHOST_WORKDIR=dist/selfhost
                cp dist/selfhost/cc4 yh
                rm -rf dist/selfhost
                name="yh-${TAG}-linux-x86_64"
                stage="dist/.stage-linux-x86_64"
                mkdir -p "$stage"
                cp yh "$stage/yh"
                tar -czf "dist/$name.tar.gz" -C "$stage" yh
                rm -rf "$stage"
                (cd dist && sha256sum "$name.tar.gz" > "$name.sha256")
              '
          '''
        }
      }
    }

    // 分支和 tag 都要跑 Darwin/arm64（宿主原生）。
    stage('Darwin/arm64') {
      when { expression { env.SHOULD_RUN == '1' } }
      steps {
        withCredentials([string(credentialsId: 'github-token', variable: 'GITHUB_TOKEN')]) {
          sh '''
            set -euo pipefail
            python3 tools/fetch-release-seed.py --platform darwin-arm64 --exclude-tag "${TAG:-}"
            make bootstrap
            make test-llvm-darwin
            python3 tests/yh/check.py --compiler --compiler-path "$PWD/yh" --quiet
            python3 tests/yh-run/check.py --compiler "$PWD/yh" --quiet --jobs "$(sysctl -n hw.ncpu)"
            if [ -n "${TAG:-}" ]; then
              make selfhost-native SKIP_CORPUS=1 SELFHOST_KEEP=1 SELFHOST_WORKDIR=dist/selfhost
              cp dist/selfhost/cc4 yh
              rm -rf dist/selfhost
              name="yh-${TAG}-darwin-arm64"
              stage="dist/.stage-darwin-arm64"
              mkdir -p "$stage"
              cp yh "$stage/yh"
              tar -czf "dist/$name.tar.gz" -C "$stage" yh
              rm -rf "$stage"
              (cd dist && shasum -a 256 "$name.tar.gz" > "$name.sha256")
            else
              make selfhost-native SKIP_CORPUS=1
            fi
          '''
        }
      }
    }

    stage('发布 Release') {
      when { expression { env.SHOULD_RUN == '1' && env.IS_RELEASE == '1' } }
      steps {
        withCredentials([string(credentialsId: 'github-token', variable: 'GITHUB_TOKEN')]) {
          sh '''
            set -euo pipefail
            python3 tools/jenkins/publish.py \
              --repo "$GITHUB_REPOSITORY" \
              --tag "$TAG" \
              --dist dist \
              --notes "docs/01-finished/release-$TAG.md"
          '''
        }
      }
    }
  }
  post {
    always {
      // Release 资产已经上传到 GitHub；这里只留很小的 .sha256，避免占满磁盘。
      archiveArtifacts artifacts: 'dist/*.sha256', allowEmptyArchive: true
      // 每轮构建后清 workspace；LLVM 闭包在 $YH_LLVM_CACHE，不受影响。
      deleteDir()
    }
  }
}
