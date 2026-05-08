#!/usr/bin/env python3
"""扫描 src 目录下超过 300 行的 Python 文件"""
import os
from pathlib import Path

src_dir = Path(__file__).parent.parent / "src"
file_lines = []

for py_file in src_dir.rglob("*.py"):
    try:
        with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = len(f.readlines())
            if lines > 100:  # 降低阈值查看所有候选文件
                file_lines.append((lines, str(py_file.relative_to(src_dir))))
    except Exception as e:
        print(f"Error reading {py_file}: {e}")

file_lines.sort(reverse=True)
print(f"Total Python files: {len(list(src_dir.rglob('*.py')))}")
print(f"Files > 200 lines: {len(file_lines)}")
print()
for lines, path in file_lines:
    print(f"{lines:4d} | {path}")