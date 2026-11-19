"""网页抓取工具：把任意 URL 转成可读文本。

技能安装（下载 + 沙箱验证）已独立到 `src.agent.skills.installer`。
"""
import re

import httpx
from langchain_core.tools import tool

from src.core.logging import agent_logger


def _strip_html(html: str) -> str:
    """简易 HTML → 纯文本（去标签、合并空白）"""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@tool
def web_fetch(url: str, max_chars: int = 8000) -> str:
    """获取指定 URL 的网页内容（转为纯文本）。

    可用于：
    - 查看技术文档、API 说明
    - 获取 Skill 文件内容
    - 阅读在线资源

    Args:
        url: 完整的 HTTP/HTTPS 地址
        max_chars: 返回内容最大字符数（默认8000）

    Returns:
        网页文本内容或错误信息
    """
    if not url.startswith(("http://", "https://")):
        return "错误: URL 必须以 http:// 或 https:// 开头"

    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=20,
            headers={"User-Agent": "ERP-Agent/1.0 (Skill Downloader)"},
        )

        if response.status_code != 200:
            return f"请求失败: HTTP {response.status_code}"

        content_type = response.headers.get("content-type", "")
        text = response.text

        # HTML → 纯文本
        if "text/html" in content_type:
            text = _strip_html(text)

        # 截断
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n... [内容已截断，共 {len(response.text)} 字符]"

        agent_logger.info(f"web_fetch: {url} ({len(text)} chars)")
        return text

    except httpx.TimeoutException:
        return f"请求超时: {url}"
    except Exception as e:
        agent_logger.error(f"web_fetch error: {e}")
        return f"获取失败: {str(e)}"
