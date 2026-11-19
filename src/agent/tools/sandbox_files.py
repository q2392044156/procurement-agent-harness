"""沙箱文件下载工具（Harness — 真实 Docker 文件提取）。

把沙箱容器里的文件（图表 PNG、报告 MD/HTML、CSV/JSON 等）读到宿主机
``data/download/`` 目录，返回相对 harness 的 HTTP 链接（``/api/download/<文件名>``），
浏览器侧由平台代理转成 ``/api/v1/ai/files/<文件名>`` 再取二进制。

取容器的方式很关键：必须用 **当前请求绑定的用户沙箱**（``src.sandbox.holder``
里的 ContextVar / 注册表）。早期实现直接在 Docker 里扫「第一个名字以
``erp-sandbox-`` 开头的运行中容器」，在有多用户或少预热池时会把 A 用户生成的
文件当成「不存在」（扫到的是别人的容器），于是模型只能用 ``execute`` 手工
base64 绕路，还撞上工具调用上限。
"""
from pathlib import Path
from urllib.parse import quote

from langchain_core.tools import tool

from src.agent.runtime import get_current_user_id
from src.core.logging import agent_logger
from src.sandbox.holder import get_sandbox

DOWNLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "download"


def _get_bound_sandbox():
    """取当前请求绑定的沙箱；未绑定（脚本、单测）返回 None。"""
    try:
        return get_sandbox(get_current_user_id())
    except Exception as e:  # noqa: BLE001 - 取不到就走本地回退
        agent_logger.warning(f"Cannot resolve bound sandbox: {e}")
        return None


def _download_url(filename: str) -> str:
    """返回相对 harness 的下载地址。

    不能写死 ``http://localhost:8000``：浏览器走的是平台 nginx，平台会把
    ``/api/v1/ai/files/<name>`` 代理到 harness 的 ``/api/download/<name>``，
    前端识别出文件名后再换成带鉴权的平台地址。相对路径对直连 harness 的脚本
    同样可用。
    """
    return f"/api/download/{quote(filename)}"


@tool
def download_sandbox_file(remote_path: str, filename: str = "") -> str:
    """从沙箱容器中下载文件到宿主机，生成 HTTP 下载链接。

    Args:
        remote_path: 沙箱内的文件路径（如 /workspace/charts/chart.png）
        filename: 下载后的文件名（默认使用原文件名）

    Returns:
        下载链接和本地路径，或错误信息
    """
    filename = filename or Path(remote_path).name
    target = DOWNLOAD_DIR / filename

    sandbox = _get_bound_sandbox()
    if sandbox is not None:
        try:
            content = sandbox.read_file_bytes(remote_path)
        except FileNotFoundError:
            return f"文件不存在于沙箱中: {remote_path}"
        except Exception as e:  # noqa: BLE001 - 读失败时把原因返回给模型
            agent_logger.error(f"Sandbox download error: {e}")
            return f"无法读取沙箱文件: {remote_path} — {e}"

        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        agent_logger.info(
            f"File downloaded from sandbox: {remote_path} -> {target} ({len(content)} bytes)"
        )
        return (
            f"✅ 文件已从沙箱下载!\n"
            f"沙箱路径: {remote_path}\n"
            f"文件大小: {len(content) / 1024:.1f} KB\n"
            f"下载链接: {_download_url(filename)}\n"
            f"本地路径: {target}"
        )

    # 回退：开发模式（LocalShell / 本地文件）
    source = Path(remote_path)
    if source.exists():
        if source.is_dir():
            return f"路径是目录而非文件: {remote_path}"

        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        agent_logger.info(f"File downloaded (local fallback): {source} -> {target}")
        return (
            f"✅ 文件已下载!\n"
            f"路径: {remote_path}\n"
            f"文件大小: {source.stat().st_size / 1024:.1f} KB\n"
            f"下载链接: {_download_url(filename)}\n"
            f"本地路径: {target}\n"
            f"(注: 沙箱不可用，使用本地文件)"
        )

    return (
        f"文件下载失败:\n"
        f"- 沙箱路径: {remote_path}\n"
        f"- 沙箱状态: 不可用（当前请求没有绑定沙箱）\n"
        f"请确认文件已在沙箱中生成。"
    )


@tool
def list_sandbox_files(path: str = "/workspace") -> str:
    """列出沙箱内指定目录的文件。

    Args:
        path: 沙箱内的目录路径（默认 /workspace）

    Returns:
        文件列表
    """
    sandbox = _get_bound_sandbox()
    if sandbox is None:
        return "沙箱不可用"

    try:
        result = sandbox.execute(f"ls -lah '{path}'")
    except Exception as e:  # noqa: BLE001
        return f"列出目录失败: {e}"

    output = (getattr(result, "output", "") or "").strip()
    if getattr(result, "exit_code", 1) != 0:
        return f"列出目录失败: {path} — {output[:200]}"
    return f"沙箱目录 {path}:\n{output}" if output else f"目录为空: {path}"
