import os
from pathlib import Path

# 获取项目根目录（脚本所在目录的上一级）
project_root = Path(__file__).parent.parent

files = []
for root, dirs, filenames in os.walk(project_root / 'src'):
    dirs[:] = [d for d in dirs if not d.startswith('_') and d != '__pycache__']
    for f in filenames:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                lines = len(open(path, 'r', encoding='utf-8').readlines())
                if lines > 300:
                    files.append((path, lines))
            except:
                pass

files.sort(key=lambda x: -x[1])
for p, l in files:
    print(f'{p}: {l} lines')