"""
向量记忆管理模块 - 基于 Milvus 向量数据库

功能特性:
- 使用 embedding 模型将对话内容转换为向量
- 存储到 Milvus 向量数据库
- 支持相似度检索
- 字段: id, vector, query, tool, content, time
"""

import uuid
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import numpy as np
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 尝试导入 transformers，如果失败则使用模拟模式
try:
    from transformers import AutoTokenizer, AutoModel
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("警告: transformers 未安装，将使用模拟模式")

# 尝试导入 pymilvus
try:
    from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility
    MILVUS_AVAILABLE = True
except ImportError:
    MILVUS_AVAILABLE = False
    print("警告: pymilvus 未安装，将使用模拟模式")


@dataclass
class VectorMemoryEntry:
    """向量记忆条目"""
    id: str
    vector: List[float]
    query: str
    tool: str
    content: str
    time: datetime

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "vector": self.vector,
            "query": self.query,
            "tool": self.tool,
            "content": self.content,
            "time": self.time.isoformat()
        }


class EmbeddingModel:
    """Embedding 模型封装"""

    def __init__(self, model_path: str = None):
        self.model_path = model_path or "milvus/embedding_model/iic/nlp_corom_sentence-embedding_chinese-base"
        self.tokenizer = None
        self.model = None
        self.device = None
        self._initialized = False

    def initialize(self):
        """初始化模型"""
        if self._initialized:
            return

        if not TRANSFORMERS_AVAILABLE:
            print("警告: transformers 不可用，使用随机向量")
            self._initialized = True
            return

        try:
            print(f"加载 embedding 模型: {self.model_path}")
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

            # 检查模型路径是否存在
            if not os.path.exists(self.model_path):
                print(f"警告: 模型路径不存在: {self.model_path}")
                print("将使用随机向量")
                self._initialized = True
                return

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModel.from_pretrained(self.model_path).to(self.device)
            self.model.eval()

            self._initialized = True
            print(f"模型加载完成，使用设备: {self.device}")

        except Exception as e:
            print(f"模型加载失败: {e}")
            print("将使用随机向量")
            self._initialized = True

    def encode(self, text: str) -> List[float]:
        """
        将文本编码为向量

        Args:
            text: 输入文本

        Returns:
            向量列表
        """
        if not self._initialized:
            self.initialize()

        # 如果模型不可用，返回随机向量（用于测试）
        if not TRANSFORMERS_AVAILABLE or self.model is None:
            # 返回固定维度的随机向量（768维）
            np.random.seed(hash(text) % 2**32)
            return np.random.randn(768).tolist()

        try:
            # 使用模型编码
            inputs = self.tokenizer(
                text,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt"
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)
                # 使用 [CLS] token 的嵌入作为句子表示
                embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()

            return embeddings[0].tolist()

        except Exception as e:
            print(f"编码失败: {e}")
            # 返回随机向量
            np.random.seed(hash(text) % 2**32)
            return np.random.randn(768).tolist()


class VectorMemoryManager:
    """
    向量记忆管理器

    使用 Milvus 存储对话记录，支持向量检索
    """

    # 从环境变量读取配置
    COLLECTION_NAME = os.getenv("MILVUS_COLLECTION_NAME", "join_agent")
    VECTOR_DIM = 768  # embedding 维度

    def __init__(
        self,
        host: str = None,
        port: str = None,
        model_path: str = None,
        enable_vector_memory: bool = None
    ):
        # 从环境变量读取配置，参数可覆盖
        self.host = host or os.getenv("MILVUS_HOST", "localhost")
        self.port = port or os.getenv("MILVUS_PORT", "19530")

        # 是否启用向量记忆
        if enable_vector_memory is None:
            enable_env = os.getenv("ENABLE_VECTOR_MEMORY", "true").lower()
            enable_vector_memory = enable_env in ("true", "1", "yes")
        self.enable_vector_memory = enable_vector_memory and MILVUS_AVAILABLE

        # Embedding 模型路径
        if model_path is None:
            model_path = os.getenv("EMBEDDING_MODEL_PATH", "milvus/embedding_model/iic/nlp_corom_sentence-embedding_chinese-base")

        # Embedding 模型
        self.embedding_model = EmbeddingModel(model_path) if self.enable_vector_memory else None

        # Milvus 集合
        self.collection = None
        self._connected = False

        # 本地缓存（当 Milvus 不可用时使用）
        self._local_cache: List[VectorMemoryEntry] = []

    def connect(self) -> bool:
        """连接到 Milvus 服务器"""
        if not self.enable_vector_memory:
            print("向量记忆功能已禁用")
            return False

        if self._connected:
            return True

        try:
            print(f"连接到 Milvus: {self.host}:{self.port}")
            connections.connect(alias="default", host=self.host, port=self.port)
            self._connected = True
            print("Milvus 连接成功")

            # 初始化集合
            self._init_collection()

            # 初始化 embedding 模型
            if self.embedding_model:
                self.embedding_model.initialize()

            return True

        except Exception as e:
            print(f"Milvus 连接失败: {e}")
            print("将使用本地缓存模式")
            self._connected = False
            return False

    def _init_collection(self):
        """初始化 Milvus 集合"""
        if not self._connected:
            return

        try:
            # 检查集合是否存在
            if utility.has_collection(self.COLLECTION_NAME):
                print(f"集合 {self.COLLECTION_NAME} 已存在")
                self.collection = Collection(self.COLLECTION_NAME)
            else:
                print(f"创建集合 {self.COLLECTION_NAME}")

                # 定义字段
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=36, is_primary=True),
                    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=self.VECTOR_DIM),
                    FieldSchema(name="query", dtype=DataType.VARCHAR, max_length=4096),
                    FieldSchema(name="tool", dtype=DataType.VARCHAR, max_length=4096),
                    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                    FieldSchema(name="time", dtype=DataType.VARCHAR, max_length=30)
                ]

                # 创建 schema
                schema = CollectionSchema(fields, description="Join Agent 对话记忆")

                # 创建集合
                self.collection = Collection(self.COLLECTION_NAME, schema)

                # 创建索引
                index_params = {
                    "metric_type": "L2",
                    "index_type": "IVF_FLAT",
                    "params": {"nlist": 128}
                }
                self.collection.create_index(field_name="vector", index_params=index_params)
                print("集合创建完成")

            # 加载集合
            self.collection.load()

        except Exception as e:
            print(f"集合初始化失败: {e}")
            self.collection = None

    def add_memory(
        self,
        query: str,
        tool: str,
        content: str
    ) -> Optional[str]:
        """
        添加记忆

        Args:
            query: 用户输入问题
            tool: 调用的工具及返回结果
            content: 大模型最终生成的答案

        Returns:
            记忆ID
        """
        # 生成 UUID
        memory_id = str(uuid.uuid4())

        # 生成向量: query + tool + content 的拼接
        vector_text = f"{query} {tool} {content}"

        if self.embedding_model:
            vector = self.embedding_model.encode(vector_text)
        else:
            # 使用随机向量
            np.random.seed(hash(vector_text) % 2**32)
            vector = np.random.randn(self.VECTOR_DIM).tolist()

        # 创建记忆条目
        entry = VectorMemoryEntry(
            id=memory_id,
            vector=vector,
            query=query,
            tool=tool,
            content=content,
            time=datetime.now()
        )

        # 存储到 Milvus
        if self._connected and self.collection is not None:
            try:
                entities = [
                    [entry.id],
                    [entry.vector],
                    [entry.query],
                    [entry.tool],
                    [entry.content],
                    [entry.time.isoformat()]
                ]
                self.collection.insert(entities)
                self.collection.flush()
                print(f"记忆已存入 Milvus: {memory_id}")
            except Exception as e:
                print(f"Milvus 插入失败: {e}")
                # 存入本地缓存
                self._local_cache.append(entry)
        else:
            # 存入本地缓存
            self._local_cache.append(entry)
            print(f"记忆已存入本地缓存: {memory_id}")

        return memory_id

    def search_similar(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索相似记忆

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            相似记忆列表
        """
        if self.embedding_model:
            query_vector = self.embedding_model.encode(query)
        else:
            np.random.seed(hash(query) % 2**32)
            query_vector = np.random.randn(self.VECTOR_DIM).tolist()

        results = []

        # 如果未连接，尝试自动连接
        if not self._connected:
            self.connect()

        # 从 Milvus 搜索
        if self._connected and self.collection is not None:
            try:
                search_params = {"metric_type": "L2", "params": {"nprobe": 10}}

                milvus_results = self.collection.search(
                    data=[query_vector],
                    anns_field="vector",
                    param=search_params,
                    limit=top_k,
                    output_fields=["id", "query", "tool", "content", "time"]
                )

                for hits in milvus_results:
                    for hit in hits:
                        results.append({
                            "id": hit.entity.get("id"),
                            "query": hit.entity.get("query"),
                            "tool": hit.entity.get("tool"),
                            "content": hit.entity.get("content"),
                            "time": hit.entity.get("time"),
                            "distance": hit.distance
                        })

            except Exception as e:
                print(f"Milvus 搜索失败: {e}")

        # 如果 Milvus 没有结果或失败，从本地缓存搜索
        if not results and self._local_cache:
            # 简单的线性搜索
            from scipy.spatial.distance import cosine

            scored_cache = []
            for entry in self._local_cache:
                similarity = 1 - cosine(query_vector, entry.vector)
                scored_cache.append((similarity, entry))

            # 按相似度排序
            scored_cache.sort(key=lambda x: x[0], reverse=True)

            for similarity, entry in scored_cache[:top_k]:
                results.append({
                    "id": entry.id,
                    "query": entry.query,
                    "tool": entry.tool,
                    "content": entry.content,
                    "time": entry.time.isoformat(),
                    "distance": 1 - similarity
                })

        return results

    def get_recent_memories(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的记忆"""
        if self._connected and self.collection is not None:
            try:
                # 查询所有记录，按时间排序
                results = self.collection.query(
                    expr="id != ''",
                    output_fields=["id", "query", "tool", "content", "time"],
                    limit=limit
                )

                # 按时间排序
                results.sort(key=lambda x: x["time"], reverse=True)
                return results[:limit]

            except Exception as e:
                print(f"Milvus 查询失败: {e}")

        # 从本地缓存获取
        sorted_cache = sorted(
            self._local_cache,
            key=lambda x: x.time,
            reverse=True
        )

        return [
            {
                "id": entry.id,
                "query": entry.query,
                "tool": entry.tool,
                "content": entry.content,
                "time": entry.time.isoformat()
            }
            for entry in sorted_cache[:limit]
        ]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "connected": self._connected,
            "local_cache_count": len(self._local_cache)
        }

        if self._connected and self.collection is not None:
            try:
                stats["total_count"] = self.collection.num_entities
            except Exception as e:
                stats["total_count"] = len(self._local_cache)
        else:
            stats["total_count"] = len(self._local_cache)

        return stats

    def clear(self) -> None:
        """清空所有记忆"""
        # 清空本地缓存
        self._local_cache = []

        # 清空 Milvus 集合
        if self._connected and self.collection is not None:
            try:
                self.collection.drop()
                print("Milvus 集合已清空")
            except Exception as e:
                print(f"清空 Milvus 集合失败: {e}")

        self._connected = False
        self.collection = None
