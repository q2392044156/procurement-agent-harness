"""
Harness 结构化状态模型（Planning → Executing → Review → Result）。

为什么放在 agent/review 而不是 core/contracts：
这些类型是「评审流水线内部的状态形状」，只有 review 包消费（phase / gate），
不属于对外契约；对外契约（ChatRequest、ProcurementContext、DisplayMessage 等）
留在 core/contracts.py，供 server 与工具层共用。

设计意图：阶段、计划、评审结果都是可校验的强类型数据，替代 prompt 软约束。
"""
from datetime import datetime
from enum import Enum
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field
from typing_extensions import NotRequired

from langchain.agents.middleware.types import AgentState, PrivateStateAttr


class Phase(str, Enum):
    """Harness 工作流阶段（图状态机，非文本猜测）"""
    thinking = "thinking"      # 思考中（初始态）
    planning = "planning"      # Planning：生成任务规划
    executing = "executing"    # Executing：调用工具/子Agent执行
    reviewing = "reviewing"    # Review：评审器校验结果
    result = "result"          # Result：结构化输出最终结果


class PlanStep(BaseModel):
    """规划中的单个步骤（对应 TodoListMiddleware 的 todo 项，但增加 result 回填）"""
    id: str = Field(..., description="步骤唯一标识")
    content: str = Field(..., description="步骤描述")
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending", description="步骤状态"
    )
    result: Optional[str] = Field(default=None, description="步骤执行结果摘要")


class Plan(BaseModel):
    """Harness Planning 阶段的产物：结构化任务规划"""
    steps: List[PlanStep] = Field(default_factory=list, description="规划步骤列表")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    current_step: Optional[str] = Field(default=None, description="当前执行中的步骤 id")


class ReviewResult(BaseModel):
    """Harness Review 阶段的产物：评审器对执行结果的判定

    由 RubricMiddleware 的 grader 子Agent 产出，结构化而非 LLM 自述文本。
    """
    verdict: Literal[
        "satisfied", "needs_revision", "failed",
        "max_iterations_reached", "grader_error",
    ] = Field(..., description="评审判定")
    explanation: str = Field(default="", description="评审结论说明")
    criteria: List[dict] = Field(default_factory=list, description="逐条评审标准判定")
    iteration: int = Field(default=0, description="评审迭代次数")


class HarnessPhaseState(AgentState):
    """Harness 扩展状态：在 DeepAgentState 基础上增加阶段/计划/评审字段。

    通过 HarnessPhaseMiddleware.state_schema 声明，由框架自动合并进 graph state，
    因此这些字段会出现在 checkpoint 和 values 流中（可观测、可恢复）。
    """

    phase: NotRequired[str]
    """当前阶段：planning / executing / reviewing / result（见 Phase）"""

    plan: NotRequired[dict]
    """结构化任务规划（Plan 序列化后的 dict）"""

    review_result: NotRequired[dict]
    """评审结果（ReviewResult 序列化后的 dict）"""

    _harness_rubric_source: NotRequired[Annotated[str, PrivateStateAttr]]
    """记录 rubric 是否由本中间件自动注入，用于跨 checkpoint 清理旧 rubric。"""

    review_decision: NotRequired[dict]
    _review_start: NotRequired[Annotated[int, PrivateStateAttr]]
    _review_write_attempted: NotRequired[Annotated[bool, PrivateStateAttr]]
    _review_signals: NotRequired[Annotated[list[str], PrivateStateAttr]]
