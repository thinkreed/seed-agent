"""
文件同步器（增量索引）

基于 Claude Context FileSynchronizer 设计：
- 文件哈希生成（SHA-256）
- Merkle DAG 构建
- 快照持久化
- 变更检测（O(1) 无变更检测）

使用示例：
    synchronizer = FileSynchronizer(
        root_dir="/path/to/project",
        supported_extensions=[".py", ".md"],
    )
    await synchronizer.initialize()
    changes = await synchronizer.check_for_changes()
    # changes = {"added": [...], "removed": [...], "modified": [...]}
"""

import hashlib
import json
import logging
import os
from pathlib import Path

from ._merkle_dag import MerkleDAG

logger = logging.getLogger("seed_agent")


class FileSynchronizer:
    """文件同步器，管理增量索引"""

    def __init__(
        self,
        root_dir: str,
        supported_extensions: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
        snapshot_dir: str | None = None,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.supported_extensions = supported_extensions or [".py", ".md", ".txt"]
        self.ignore_patterns = ignore_patterns or [
            ".git",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "node_modules",
        ]

        # 快照路径
        if snapshot_dir:
            self.snapshot_dir = Path(snapshot_dir)
        else:
            self.snapshot_dir = Path.home() / ".seed" / "merkle"

        self._file_hashes: dict[str, str] = {}
        self._merkle_dag: MerkleDAG = MerkleDAG()
        self._initialized = False

    def _get_snapshot_path(self) -> Path:
        """获取快照文件路径"""
        # 使用 MD5 哈希项目路径作为文件名
        path_hash = hashlib.md5(str(self.root_dir).encode()).hexdigest()
        return self.snapshot_dir / f"{path_hash}.json"

    def _hash_file(self, file_path: Path) -> str:
        """计算文件 SHA-256 哈希"""
        try:
            content = file_path.read_text(encoding="utf-8")
            return hashlib.sha256(content.encode("utf-8")).hexdigest()
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to hash file {file_path}: {e}")
            return ""

    def _should_ignore(self, relative_path: str) -> bool:
        """检查路径是否应被忽略"""
        # 隐藏文件/目录
        parts = relative_path.split(os.sep)
        if any(part.startswith(".") for part in parts):
            return True

        # 模式匹配
        for pattern in self.ignore_patterns:
            if pattern in parts:
                return True

        return False

    def _generate_file_hashes(self) -> dict[str, str]:
        """递归扫描目录生成文件哈希"""
        file_hashes: dict[str, str] = {}

        for root, dirs, files in os.walk(self.root_dir):
            # 过滤目录
            dirs[:] = [d for d in dirs if not self._should_ignore(d)]

            for file_name in files:
                file_path = Path(root) / file_name
                relative_path = str(file_path.relative_to(self.root_dir))

                # 检查扩展名
                ext = file_path.suffix
                if ext not in self.supported_extensions:
                    continue

                # 检查忽略模式
                if self._should_ignore(relative_path):
                    continue

                # 计算哈希
                hash_value = self._hash_file(file_path)
                if hash_value:
                    file_hashes[relative_path] = hash_value

        return file_hashes

    def _build_merkle_dag(self, file_hashes: dict[str, str]) -> MerkleDAG:
        """构建 Merkle DAG"""
        dag = MerkleDAG()

        # 排序文件路径确保一致性
        sorted_paths = sorted(file_hashes.keys())

        # 创建根节点（所有哈希拼接）
        values_string = "".join(file_hashes[p] for p in sorted_paths)
        root_data = f"root:{values_string}"
        root_id = dag.add_node(root_data)

        # 添加文件节点作为子节点
        for file_path in sorted_paths:
            file_data = f"{file_path}:{file_hashes[file_path]}"
            dag.add_node(file_data, root_id)

        return dag

    def initialize(self) -> None:
        """初始化同步器（加载或生成快照）"""
        snapshot_path = self._get_snapshot_path()

        try:
            with open(snapshot_path, encoding="utf-8") as f:
                data = json.load(f)

            self._file_hashes = dict(data.get("file_hashes", []))
            self._merkle_dag = MerkleDAG.deserialize(data.get("merkle_dag", {}))
            logger.info(
                f"Loaded {len(self._file_hashes)} file hashes from snapshot"
            )
        except (OSError, json.JSONDecodeError):
            # 快照不存在，生成新快照
            self._file_hashes = self._generate_file_hashes()
            self._merkle_dag = self._build_merkle_dag(self._file_hashes)
            self._save_snapshot()
            logger.info(
                f"Generated new snapshot with {len(self._file_hashes)} files"
            )

        self._initialized = True

    def _save_snapshot(self) -> None:
        """保存快照"""
        snapshot_path = self._get_snapshot_path()
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)

        # 转换 dict 为列表（兼容 JSON）
        file_hashes_list = list(self._file_hashes.items())

        data = {
            "file_hashes": file_hashes_list,
            "merkle_dag": self._merkle_dag.serialize(),
        }

        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def check_for_changes(self) -> dict[str, list[str]]:
        """检测文件变更"""
        if not self._initialized:
            self.initialize()

        # 生成当前哈希
        new_hashes = self._generate_file_hashes()
        new_dag = self._build_merkle_dag(new_hashes)

        # Merkle DAG 快速比对
        dag_changes = MerkleDAG.compare(self._merkle_dag, new_dag)

        # 根哈希相同 → 无变更
        if not dag_changes["added"] and not dag_changes["removed"]:
            return {"added": [], "removed": [], "modified": []}

        # 文件级详细比对
        file_changes = self._compare_states(self._file_hashes, new_hashes)

        # 更新内部状态
        self._file_hashes = new_hashes
        self._merkle_dag = new_dag
        self._save_snapshot()

        return file_changes

    def _compare_states(
        self,
        old_hashes: dict[str, str],
        new_hashes: dict[str, str],
    ) -> dict[str, list[str]]:
        """比对文件状态"""
        added: list[str] = []
        removed: list[str] = []
        modified: list[str] = []

        # 检测新增和修改
        for file_path, hash_value in new_hashes.items():
            if file_path not in old_hashes:
                added.append(file_path)
            elif old_hashes[file_path] != hash_value:
                modified.append(file_path)

        # 检测删除
        for file_path in old_hashes:
            if file_path not in new_hashes:
                removed.append(file_path)

        return {"added": added, "removed": removed, "modified": modified}

    def get_file_hashes(self) -> dict[str, str]:
        """获取当前文件哈希"""
        return self._file_hashes.copy()

    def delete_snapshot(self) -> None:
        """删除快照"""
        snapshot_path = self._get_snapshot_path()
        try:
            snapshot_path.unlink()
            logger.info(f"Deleted snapshot: {snapshot_path}")
        except OSError as e:
            if e.errno != 2:  # ENOENT
                raise

    def __len__(self) -> int:
        return len(self._file_hashes)


__all__ = ["FileSynchronizer"]