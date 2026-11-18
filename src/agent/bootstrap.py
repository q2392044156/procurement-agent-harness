"""沙箱冷启动填充：把项目与基础技能拷进新容器。

只使用稳定 Proxy 暴露的公开能力，因此健康检查重建后的同一个 Agent、
CompositeBackend 和工具对象都能继续复用。
"""
import fnmatch
import io
import tarfile
from pathlib import Path

from src.core.logging import agent_logger
from src.core.paths import PROJECT_ROOT


def _upload_project_to_sandbox(sandbox) -> bool:
    """
    将项目文件上传到沙箱 /workspace/src/ 目录，搭建 1:1 开发环境。
    跳过 node_modules / .git / __pycache__ / .next 等无关目录。
    """
    skip_patterns = [
        ".git", "__pycache__", "node_modules", ".next", ".venv",
        ".env", ".env.*", "*.pem", "*.key",
        ".eggs", "*.pyc", "*.pyo", ".DS_Store", ".docker",
        "*.png", "*.jpg", "*.jpeg", "*.gif",  # 生成物不传
    ]

    def _should_skip(rel_path: str) -> bool:
        for pattern in skip_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            parts = rel_path.replace("\\", "/").split("/")
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
        return False

    remote_dir = "/workspace/src"
    try:
        sandbox.execute(f"mkdir -p '{remote_dir}'")

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w:gz") as tar:
            for file_path in sorted(PROJECT_ROOT.rglob("*")):
                if not file_path.is_file():
                    continue
                rel = str(file_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
                if _should_skip(rel):
                    continue
                tar.add(str(file_path), arcname=rel)

        tar_stream.seek(0)
        data = tar_stream.read()

        # 仅使用 BaseSandbox 的公开协议上传；这样 SandboxBackendProxy 热替换
        # 底层容器后，项目上传仍能工作，且不会依赖 Docker 私有 _container。
        archive_path = "/tmp/erp-agent-project.tar.gz"
        responses = sandbox.upload_files([(archive_path, data)])
        errors = [getattr(item, "error", None) for item in responses]
        if not responses or any(errors):
            raise RuntimeError(f"archive upload failed: {errors or 'no response'}")

        unpack = sandbox.execute(
            f"tar -xzf '{archive_path}' -C '{remote_dir}' && rm -f '{archive_path}'"
        )
        if unpack.exit_code != 0:
            raise RuntimeError(f"archive extraction failed: {unpack.output}")

        # 获取文件数量和总大小
        count_result = sandbox.execute(
            f"find {remote_dir} -type f 2>/dev/null | wc -l"
        )
        size_result = sandbox.execute(
            f"du -sh {remote_dir} 2>/dev/null | cut -f1"
        )
        file_count = count_result.output.strip() if count_result.exit_code == 0 else "?"
        total_size = size_result.output.strip() if size_result.exit_code == 0 else "?"

        agent_logger.info(
            f"Project uploaded to sandbox: {remote_dir} "
            f"({file_count} files, {total_size})"
        )
        return True
    except Exception as e:
        agent_logger.warning(f"Project upload to sandbox failed (non-fatal): {e}")
        return False


def bootstrap_sandbox(sandbox) -> None:
    """填充一个新领取或重建后的沙箱，使其可立即继续 Agent 工作。

    这个函数只使用稳定 Proxy 暴露的公开能力，因此健康检查重建后的同一个
    Agent、CompositeBackend 和工具对象都能继续复用。
    """
    setup = sandbox.execute(
        "mkdir -p /workspace/charts /workspace/output /workspace/data "
        "/workspace/python-packages /skills"
    )
    if setup.exit_code != 0:
        raise RuntimeError(f"sandbox directory setup failed: {setup.output}")

    if not _upload_project_to_sandbox(sandbox):
        raise RuntimeError("project bootstrap upload failed")

    skills_copy = sandbox.execute(
        "mkdir -p /skills && "
        "cp -r /workspace/src/skills/. /skills/ 2>/dev/null || true"
    )
    if skills_copy.exit_code != 0:
        raise RuntimeError(f"core Skills bootstrap failed: {skills_copy.output}")

    agent_logger.info("Sandbox bootstrap complete: project + core Skills restored")


def _load_skills_prompt(skills_dir: Path) -> str:
    """
    兼容入口：仅返回基础技能元数据，不读取正文注入提示词。

    保留在 bootstrap 之外无意义 —— 它描述的是"技能目录如何渲染"；
    但历史基准脚本需按此路径取函数，故随 bootstrap 一起安放。
    """
    from src.agent.skills.catalog import SkillCatalog
    return SkillCatalog(skills_dir).index()
