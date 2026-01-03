# tests/conftest.py
from __future__ import annotations

import sys
from pathlib import Path

# 项目根目录 = tests 上一层目录
ROOT = Path(__file__).resolve().parents[1]

# 确保项目根在 sys.path 中，方便 `import core` 等绝对导入
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)