"""测试替身：跨测试文件共享的假 Store 与假消息。

刻意不依赖 MongoDB / Docker / langchain —— 任何 Python 3.10+ 都能直接跑，
这样记忆层的测试不需要起任何外部服务。
"""
from __future__ import annotations

from typing import Optional


class FakeItem:
    def __init__(self, namespace, key, value):
        self.namespace = tuple(namespace)
        self.key = key
        self.value = value


class FakeStore:
    """最小 BaseStore 替身：只实现 get/put/search/delete。"""

    def __init__(self, fail: bool = False):
        self.data = {}
        self.fail = fail
        self.calls = {"get": 0, "put": 0, "search": 0, "delete": 0}

    def _key(self, namespace, key):
        return (tuple(namespace), key)

    def get(self, namespace, key):
        self.calls["get"] += 1
        if self.fail:
            raise RuntimeError("store down")
        return FakeItem(namespace, key, self.data.get(self._key(namespace, key)))

    def put(self, namespace, key, value):
        self.calls["put"] += 1
        if self.fail:
            raise RuntimeError("store down")
        self.data[self._key(namespace, key)] = value
        return FakeItem(namespace, key, value)

    def search(self, namespace, limit: int = 100, **kwargs):
        self.calls["search"] += 1
        if self.fail:
            raise RuntimeError("store down")
        target = tuple(namespace)
        items = [
            FakeItem(n, k, v)
            for (n, k), v in self.data.items()
            if n == target
        ]
        return items[:limit]

    def delete(self, namespace, key):
        self.calls["delete"] += 1
        if self.fail:
            raise RuntimeError("store down")
        self.data.pop(self._key(namespace, key), None)


class Msg:
    """最简消息替身，模拟 LangChain 消息的接口面。"""

    def __init__(self, type_: str, content: str = "", tool_calls=None, name: Optional[str] = None):
        self.type = type_
        self.content = content
        self.tool_calls = tool_calls or []
        self.name = name
