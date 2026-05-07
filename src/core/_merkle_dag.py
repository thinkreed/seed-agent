"""
Merkle DAG 增量索引实现

基于 Claude Context 设计：使用 SHA-256 哈希检测文件变更，
实现 O(1) 无变更检测 + O(k) 增量更新。

核心设计：
- MerkleDAGNode: 节点结构（id, hash, data, parents, children）
- MerkleDAG: DAG 管理（添加节点、比对、序列化）
- 根哈希比对：O(1) 快速检测无变更
- DAG 比对：O(n) 检测新增/删除节点
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MerkleDAGNode:
    """Merkle DAG 节点"""

    id: str  # SHA-256(data)
    hash: str  # 哈希值（同 id）
    data: str  # 数据内容（"path:hash" 或 "root:hashes"）
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)


class MerkleDAG:
    """Merkle DAG 管理"""

    def __init__(self) -> None:
        self._nodes: dict[str, MerkleDAGNode] = {}
        self._root_ids: list[str] = []

    def _hash(self, data: str) -> str:
        """计算 SHA-256 哈希"""
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def add_node(self, data: str, parent_id: str | None = None) -> str:
        """添加节点到 DAG"""
        node_id = self._hash(data)
        node = MerkleDAGNode(
            id=node_id,
            hash=node_id,
            data=data,
            parents=[],
            children=[],
        )

        if parent_id:
            parent = self._nodes.get(parent_id)
            if parent:
                node.parents.append(parent_id)
                parent.children.append(node_id)
                self._nodes[parent_id] = parent
        else:
            self._root_ids.append(node_id)

        self._nodes[node_id] = node
        return node_id

    def get_node(self, node_id: str) -> MerkleDAGNode | None:
        """获取节点"""
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[MerkleDAGNode]:
        """获取所有节点"""
        return list(self._nodes.values())

    def get_root_ids(self) -> list[str]:
        """获取根节点 ID"""
        return self._root_ids

    def serialize(self) -> dict[str, Any]:
        """序列化 DAG"""
        nodes_data = []
        for node in self._nodes.values():
            nodes_data.append({
                "id": node.id,
                "hash": node.hash,
                "data": node.data,
                "parents": node.parents,
                "children": node.children,
            })
        return {"nodes": nodes_data, "root_ids": self._root_ids}

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "MerkleDAG":
        """反序列化 DAG"""
        dag = cls()
        for node_data in data.get("nodes", []):
            node = MerkleDAGNode(
                id=node_data["id"],
                hash=node_data["hash"],
                data=node_data["data"],
                parents=node_data.get("parents", []),
                children=node_data.get("children", []),
            )
            dag._nodes[node.id] = node
        dag._root_ids = data.get("root_ids", [])
        return dag

    @classmethod
    def compare(
        cls, dag1: MerkleDAG, dag2: MerkleDAG
    ) -> dict[str, list[str]]:
        """比对两个 DAG，返回差异"""
        nodes1 = {n.id for n in dag1.get_all_nodes()}
        nodes2 = {n.id for n in dag2.get_all_nodes()}

        added = [id for id in nodes2 if id not in nodes1]
        removed = [id for id in nodes1 if id not in nodes2]

        return {"added": added, "removed": removed}

    def __len__(self) -> int:
        return len(self._nodes)


__all__ = ["MerkleDAG", "MerkleDAGNode"]