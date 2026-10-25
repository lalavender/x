#!/usr/bin/env python3
"""yh-explorer 本地服务器 —— 给 tools/yh-explorer.html 提供编译/运行后端。

浏览器页面无法直接执行本地二进制，本服务器只做三件事：

    GET  /               返回同目录下的 yh-explorer.html
    GET  /api/defaults   探测仓库根的 yh，返回缺省编译器路径
    POST /api/compile    调 `yh --emit-asm <file.yh>`，汇编写到 stdout
    POST /api/run        `yh -o <exe> <file.yh>` 编译链接后运行，比对输出

仅监听 127.0.0.1（本机开发工具，无鉴权，切勿暴露到公网）。
仅依赖 Python 标准库；临时产物一律放在仓库 tmp/yh-explorer-work/ 下。

用法：
    python3 tools/yh-explorer.py                # 缺省端口 8765，自动开浏览器
    python3 tools/yh-explorer.py --port 9000
    python3 tools/yh-explorer.py --no-browser
"""

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 仓库根 = 本脚本目录的上一级（tools/ 的父目录）
ROOT = Path(__file__).resolve().parent.parent
HTML = Path(__file__).resolve().parent / "yh-explorer.html"
WORK = ROOT / "tmp" / "yh-explorer-work"   # 临时产物目录（tmp/ 已被 gitignore）

COMPILE_TIMEOUT = 60   # 编译超时（秒），与 tests/yh-run 一致
RUN_TIMEOUT = 15       # 运行超时（秒）


def default_compiler():
    """缺省编译器：仓库根的 yh（自举编译器，主要开发编译器）。"""
    for name in ("yh",):
        p = ROOT / name
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    return str(ROOT / "yh")  # 都不存在时仍返回预期路径，由前端报“未找到”


def ensure_work():
    """确保临时产物目录存在并返回。"""
    WORK.mkdir(parents=True, exist_ok=True)
    return WORK


def probe_candidates():
    """探测两个候选编译器是否存在，供前端下拉框显示。"""
    out = {}
    for name in ("yh",):
        p = ROOT / name
        out[name] = str(p) if p.exists() else None
    return out


def run_cmd(cmd, timeout, stdin_data=None, cwd=None):
    """统一执行子进程：返回 (returncode, stdout, stderr, timed_out)。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            input=stdin_data if stdin_data is not None else "", cwd=cwd,
        )
        return proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = (e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return None, out, err, True
    except FileNotFoundError as e:
        return None, "", f"无法启动进程: {e}", False


def api_compile(body):
    """--emit-asm：汇编输出到 stdout。body: {compiler, source, options}"""
    compiler = body.get("compiler") or default_compiler()
    source = body.get("source") or ""
    options = body.get("options") or ""
    work = ensure_work()
    src = work / "play.yh"
    src.write_text(source, encoding="utf-8")
    cmd = [compiler, "--emit-asm", str(src)] + shlex.split(options)
    rc, out, err, timed = run_cmd(cmd, COMPILE_TIMEOUT)
    if not os.path.exists(compiler):
        return {"ok": False, "asm": "", "stderr": f"编译器不存在: {compiler}\n（先用 just 构建，或改用右侧路径输入框指定）", "exit": None}
    if timed:
        return {"ok": False, "asm": "", "stderr": "编译超时（60 秒）", "exit": None}
    return {"ok": rc == 0, "asm": out, "stderr": err, "exit": rc}


def api_run(body):
    """编译链接并运行。body: {compiler, source, options, stdin}"""
    compiler = body.get("compiler") or default_compiler()
    source = body.get("source") or ""
    options = body.get("options") or ""
    stdin_data = body.get("stdin") or ""
    if not os.path.exists(compiler):
        return {"ok": False, "stdout": "", "stderr": f"编译器不存在: {compiler}\n（先用 just 构建，或改用右侧路径输入框指定）",
                "compileStderr": "", "exit": None}
    work = ensure_work()
    src = work / "play.yh"
    exe = work / "play.out"
    src.write_text(source, encoding="utf-8")
    if exe.exists():
        exe.unlink()
    cmd = [compiler, "-o", str(exe), str(src)] + shlex.split(options)
    rc, _, cerr, timed = run_cmd(cmd, COMPILE_TIMEOUT)
    if timed:
        return {"ok": False, "stdout": "", "stderr": "", "compileStderr": "编译超时（60 秒）", "exit": None}
    if rc != 0:
        return {"ok": False, "stdout": "", "stderr": "", "compileStderr": cerr or "编译失败", "exit": rc}
    rc, out, err, timed = run_cmd([str(exe)], RUN_TIMEOUT, stdin_data=stdin_data, cwd=str(work))
    if timed:
        return {"ok": False, "stdout": out, "stderr": (err + "\n运行超时（15 秒）").strip(),
                "compileStderr": "", "exit": None}
    # ok 只代表「跑完了且没有崩溃」：故意 return 42 是正常完成，
    # 退出码原样交给前端展示；负数返回码 = 信号崩溃才算失败。
    return {"ok": rc is not None and rc >= 0, "stdout": out, "stderr": err,
            "compileStderr": cerr, "exit": rc}


class Handler(BaseHTTPRequestHandler):
    """只处理 GET /（页面）与两个 POST API 的极简处理器。"""

    def _send(self, code, content_type, payload):
        data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                body = HTML.read_bytes()
            except FileNotFoundError:
                self._send(500, "text/plain; charset=utf-8",
                           "缺少 tools/yh-explorer.html")
                return
            self._send(200, "text/html; charset=utf-8", body)
        elif self.path == "/api/defaults":
            self._json(200, {
                "default": default_compiler(),
                "candidates": probe_candidates(),
                "root": str(ROOT),
            })
        else:
            self._send(404, "text/plain; charset=utf-8", "not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 2 * 1024 * 1024:
            self._json(413, {"ok": False, "stderr": "请求体过大"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"ok": False, "stderr": "请求不是合法 JSON"})
            return
        if self.path == "/api/compile":
            self._json(200, api_compile(body))
        elif self.path == "/api/run":
            self._json(200, api_run(body))
        else:
            self._json(404, {"ok": False, "stderr": "not found"})

    def log_message(self, fmt, *args):
        # 静默默认访问日志，避免刷屏；出错信息仍走 stderr。
        pass


def main():
    parser = argparse.ArgumentParser(description="yh-explorer 本地服务器")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true",
                        help="启动后不自动打开浏览器")
    args = parser.parse_args()

    # Python 3.14 的默认 SIGINT 处理器是延迟抛出机制：主线程阻塞在
    # serve_forever/sleep 时 Ctrl+C 只重试 syscall、不抛 KeyboardInterrupt，
    # 进程退不出去。必须显式安装「会抛异常」的 handler（实测有效）。
    def _on_sigint(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, _on_sigint)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    # serve_forever 放 daemon 线程；主线程做可被 SIGINT 打断的短等待循环，
    # 双保险确保 Ctrl+C 一定能走到清理逻辑。
    worker = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
    worker.start()

    url = f"http://127.0.0.1:{args.port}"
    print(f"yh-explorer 已启动: {url}  （仓库根: {ROOT}）", flush=True)
    print(f"缺省编译器: {default_compiler()}", flush=True)
    print("Ctrl+C 退出", flush=True)
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except KeyboardInterrupt:
            pass    # 启动早期按 Ctrl+C 也能干净退出
    try:
        while worker.is_alive():
            worker.join(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
    print("\n已退出", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
