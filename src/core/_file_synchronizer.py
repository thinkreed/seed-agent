"""
文件同步器（增量索引）

基于 Claude Context FileSynchronizer 设计，支持：
- 文件哈希生成、Merkle DAG 构建、快照持久化、变更检测
"""

import hashlib
import json
import logging
from pathlib import Path

from ._hash_utils import generate_file_hashes
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
        if snapshot_dir:
            self.snapshot_dir = Path(snapshot_dir)
        else:
            self.snapshot_dir = Path.home() / ".seed" / "merkle"
        self._file_hashes: dict[str, str] = {}
        self._merkle_dag: MerkleDAG = MerkleDAG()
        self._initialized = False

    def _get_snapshot_path(self) -> Path:
        """获取快照文件路径"""
        path_hash = hashlib.md5(str(self.root_dir).encode()).hexdigest()
        return self.snapshot_dir / f"{path_hash}.json"

    def _build_merkle_dag(self, file_hashes: dict[str, str]) -> MerkleDAG:
        """构建 Merkle DAG"""
        dag = MerkleDAG()
        sorted_paths = sorted(file_hashes.keys())
        values_string = "".join(file_hashes[p] for p in sorted_paths)
        root_data = f"root:{values_string}"
        root_id = dag.add_node(root_data)
        for file_path in sorted_paths:
            file_data = f"{file_path}:{file_hashes[file_path]}"
            dag.add_node(file_data, root_id)
        return dag

    def _save_snapshot(self) -> None:
        """保存快照"""
        snapshot_path = self._get_snapshot_path()
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        file_hashes_list = list(self._file_hashes.items())
        data = {
            "file_hashes": file_hashes_list,
            "merkle_dag": self._merkle_dag.serialize(),
        }
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _compare_states(
        self, old_hashes: dict[str, str], new_hashes: dict[str, str]
    ) -> dict[str, list[str]]:
        """比对文件状态"""
        added: list[str] = []
        removed: list[str] = []
        modified: list[str] = []
        for file_path, hash_value in new_hashes.items():
            if file_path not in old_hashes:
                added.append(file_path)
            elif old_hashes[file_path] != hash_value:
                modified.append(file_path)
        for file_path in old_hashes:
            if file_path not in new_hashes:
                removed.append(file_path)
        return {"added": added, "removed": removed, "modified": modified}

    def initialize(self) -> None:
        """初始化同步器（加载或生成快照）"""
        snapshot_path = self._get_snapshot_path()
        try:
            with open(snapshot_path, encoding="utf-8") as f:
                data = json.load(f)
            self._file_hashes = dict(data.get("file_hashes", []))
            self._merkle_dag = MerkleDAG.deserialize(data.get("merkle_dag", {}))
            logger.info(f"Loaded {len(self._file_hashes)} file hashes from snapshot")
        except (OSError, json.JSONDecodeError):
            self._file_hashes = generate_file_hashes(
                self.root_dir, self.supported_extensions, self.ignore_patterns
            )
            self._merkle_dag = self._build_merkle_dag(self._file_hashes)
            self._save_snapshot()
            logger.info(f"Generated new snapshot with {len(self._file_hashes)} files")
        self._initialized = True

    def check_for_changes(self) -> dict[str, list[str]]:
        """检测文件变更"""
        if not self._initialized:
            self.initialize()
        new_hashes = generate_file_hashes(
            self.root_dir, self.supported_extensions, self.ignore_patterns
        )
        new_dag = self._build_merkle_dag(new_hashes)
        dag_changes = MerkleDAG.compare(self._merkle_dag, new_dag)
        if not dag_changes["added"] and not dag_changes["removed"]:
            return {"added": [], "removed": [], "modified": []}
        file_changes = self._compare_states(self._file_hashes, new_hashes)
        self._file_hashes = new_hashes
        self._merkle_dag = new_dag
        self._save_snapshot()
        return file_changes

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