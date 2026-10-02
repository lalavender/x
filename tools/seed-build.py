#!/usr/bin/env python3
"""用上一代 yh 在默认配置下冷编项目。"""

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    compiler = Path(args.compiler).resolve()
    project = Path(args.project).resolve()
    output = Path(args.output).resolve()
    command = [str(compiler), "build", "-o", str(output)]
    result = subprocess.run(command, cwd=project, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
