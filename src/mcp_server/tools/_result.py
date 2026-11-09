"""写工具的共享辅助：幂等头、写后校验标记、批量上限。"""
from typing import Optional

MAX_BATCH_ITEMS = 20


def idempotency_headers(key: Optional[str]) -> Optional[dict]:
    return {"Idempotency-Key": key.strip()} if key and key.strip() else None


def mark_verified(result: dict) -> dict:
    """对 code=0 的写操作结果标记 verified，便于模型判断写入已回读。"""
    if isinstance(result, dict) and result.get("code") == 0:
        data = result.get("data")
        if isinstance(data, dict):
            data["verified"] = True
        else:
            result["verified"] = True
    return result


def check_batch(items, limit: int = MAX_BATCH_ITEMS) -> None:
    if not isinstance(items, list) or not items:
        raise ValueError("明细不能为空")
    if len(items) > limit:
        raise ValueError(f"单次最多 {limit} 条明细，请拆分为多张单据")
