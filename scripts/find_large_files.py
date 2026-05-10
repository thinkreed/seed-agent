from pathlib import Path

# 获取项目根目录（脚本所在目录的上一级）
project_root = Path(__file__).resolve().parent.parent
src_dir = project_root / 'src'

files = []
# 使用 pathlib 的 rglob 替代 os.walk
for py_file in src_dir.rglob('*.py'):
    # 跳过 __pycache__ 和以 _ 开头的目录
    if '__pycache__' in py_file.parts or any(p.startswith('_') for p in py_file.parts):
        continue
    try:
        content = py_file.read_text(encoding='utf-8')
        lines = len(content.splitlines())
        if lines > 300:
            files.append((str(py_file), lines))
    except Exception:
        pass

files.sort(key=lambda x: -x[1])
for p, l in files:
    print(f'{p}: {l} lines')