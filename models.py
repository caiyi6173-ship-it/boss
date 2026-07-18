"""
Pydantic 数据模型 - 老板语音→结构化工作指令系统
定义所有核心数据结构，确保 LLM 输出严格符合 schema。
"""

from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime, date
from enum import Enum


# ────────────────────────── 枚举定义 ──────────────────────────

class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "待开始"
    IN_PROGRESS = "进行中"
    COMPLETED = "已完成"
    DELAYED = "已延期"
    BLOCKED = "被阻塞"


class TaskPriority(str, Enum):
    """任务优先级"""
    P0 = "P0-紧急"
    P1 = "P1-重要"
    P2 = "P2-一般"


class TaskCategory(str, Enum):
    """任务分类"""
    PLANNING = "策划"
    EXECUTION = "执行"
    CONTENT = "内容制作"
    REVIEW = "审核"
    REPORTING = "汇报"
    OTHER = "其他"


class EvidenceField(str, Enum):
    """证据支持的结构化字段。"""
    PROJECT_OBJECTIVE = "project.objective"
    PROJECT_DEADLINE = "project.deadline"
    TASK = "task"
    ASSIGNEE = "assignee"
    DEADLINE = "deadline"
    DELIVERABLE = "deliverable"
    DEPENDENCY = "dependency"
    PRIORITY = "priority"


class SourceSegment(BaseModel):
    """输入文件中的一条可追溯信息。"""
    id: str = Field(..., pattern=r"^S\d{4,}$", description="分段编号，如 S0001")
    source_type: str = Field(..., description="audio 或 excel")
    source_file: str = Field(..., description="来源文件名")
    speaker_role: str = Field(..., min_length=1, description="发言人职位")
    start_seconds: Optional[float] = Field(default=None, ge=0)
    end_seconds: Optional[float] = Field(default=None, ge=0)
    text: str = Field(..., min_length=1, description="原始转写文本")

    @model_validator(mode="after")
    def validate_time_range(self):
        if (
            self.start_seconds is not None
            and self.end_seconds is not None
            and self.end_seconds < self.start_seconds
        ):
            raise ValueError("来源分段结束时间不能早于开始时间")
        return self


class EvidenceItem(BaseModel):
    """AI 字段与来源分段之间的证据引用。"""
    field: EvidenceField
    source_segment_id: str = Field(..., pattern=r"^S\d{4,}$")
    source_quote: str = Field(..., min_length=1, description="必须逐字来自对应分段")
    confidence: float = Field(..., ge=0, le=1)


# ────────────────────────── 核心任务模型 ──────────────────────────

class Deliverable(BaseModel):
    """交付物"""
    name: str = Field(..., description="交付物名称")
    format: str = Field(default="", description="格式要求，如 PDF/视频/文档")
    description: str = Field(default="", description="详细描述")


class Task(BaseModel):
    """单个结构化任务"""
    id: str = Field(..., description="任务编号，如 T001")
    title: str = Field(..., description="任务标题")
    description: str = Field(..., description="任务详细描述")
    category: TaskCategory = Field(default=TaskCategory.OTHER, description="任务分类")
    priority: TaskPriority = Field(default=TaskPriority.P1, description="优先级")
    assignee: str = Field(default="待分配", description="负责人")
    deadline: Optional[str] = Field(default=None, description="截止日期，格式 YYYY-MM-DD")
    deliverables: list[Deliverable] = Field(default_factory=list, description="交付物清单")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")
    dependencies: list[str] = Field(default_factory=list, description="前置依赖任务ID列表")
    notes: str = Field(default="", description="备注")
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"), description="创建时间")
    updated_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"), description="更新时间")
    progress: int = Field(default=0, ge=0, le=100, description="完成百分比 0-100")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="字段级证据链")


# ────────────────────────── 项目总览 ──────────────────────────

class ProjectOverview(BaseModel):
    """项目总览 - LLM 从语音中提取"""
    project_name: str = Field(..., description="项目名称")
    background: str = Field(default="", description="项目背景")
    objective: str = Field(..., description="项目目标")
    scope: str = Field(default="", description="项目范围")
    overall_deadline: Optional[str] = Field(default=None, description="总体截止日期 YYYY-MM-DD")
    key_stakeholders: list[str] = Field(default_factory=list, description="关键干系人")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="项目级证据链")


class StructuredInstruction(BaseModel):
    """完整的结构化工作指令 - LLM 输出的最终结构"""
    overview: ProjectOverview = Field(..., description="项目总览")
    tasks: list[Task] = Field(..., description="任务清单")
    raw_input: str = Field(default="", description="原始语音输入文本")
    parsed_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"), description="解析时间")
    source_segments: list[SourceSegment] = Field(default_factory=list, description="规范化来源分段")

    @model_validator(mode="after")
    def validate_evidence_chain(self):
        """新输入必须具备可解析、可引用且字段覆盖完整的证据链。"""
        if not self.source_segments:
            # 兼容升级前的历史项目。
            return self

        segment_map = {segment.id: segment for segment in self.source_segments}
        if len(segment_map) != len(self.source_segments):
            raise ValueError("source_segments 中存在重复分段 ID")

        project_fields = {
            EvidenceField.PROJECT_OBJECTIVE,
            EvidenceField.PROJECT_DEADLINE,
        }
        task_fields = {
            EvidenceField.TASK,
            EvidenceField.ASSIGNEE,
            EvidenceField.DEADLINE,
            EvidenceField.DELIVERABLE,
            EvidenceField.DEPENDENCY,
            EvidenceField.PRIORITY,
        }

        def validate_items(items: list[EvidenceItem], allowed: set[EvidenceField], owner: str):
            for item in items:
                if item.field not in allowed:
                    raise ValueError(f"{owner} 使用了不适用的证据字段 {item.field.value}")
                segment = segment_map.get(item.source_segment_id)
                if not segment:
                    raise ValueError(
                        f"{owner} 引用了不存在的分段 {item.source_segment_id}"
                    )
                quote = item.source_quote.strip()
                if not quote:
                    raise ValueError(f"{owner} 的证据引文不能为空")
                if quote not in segment.text:
                    raise ValueError(
                        f"{owner} 的引文不在 {item.source_segment_id} 原话中：{quote}"
                    )

        validate_items(self.overview.evidence, project_fields, "项目概览")
        overview_fields = {item.field for item in self.overview.evidence}
        if EvidenceField.PROJECT_OBJECTIVE not in overview_fields:
            raise ValueError("项目目标缺少 project.objective 证据")
        if self.overview.overall_deadline and EvidenceField.PROJECT_DEADLINE not in overview_fields:
            raise ValueError("项目截止日期缺少 project.deadline 证据")

        for task in self.tasks:
            validate_items(task.evidence, task_fields, f"任务 {task.id}")
            fields = {item.field for item in task.evidence}
            required = {EvidenceField.TASK, EvidenceField.DELIVERABLE}
            if task.assignee not in {"", "待分配", "执行团队"}:
                required.add(EvidenceField.ASSIGNEE)
            if task.deadline:
                required.add(EvidenceField.DEADLINE)
            if task.dependencies:
                required.add(EvidenceField.DEPENDENCY)
            missing = required - fields
            if missing:
                names = ", ".join(sorted(field.value for field in missing))
                raise ValueError(f"任务 {task.id} 缺少证据字段：{names}")
        return self


# ────────────────────────── SOP 模板 ──────────────────────────

class SOPStep(BaseModel):
    """SOP 步骤"""
    step_number: int = Field(..., description="步骤编号")
    action: str = Field(..., description="动作描述")
    responsible: str = Field(default="执行者", description="负责角色")
    inputs: list[str] = Field(default_factory=list, description="输入物")
    outputs: list[str] = Field(default_factory=list, description="输出物")
    tools: list[str] = Field(default_factory=list, description="所需工具")
    quality_criteria: str = Field(default="", description="质量标准")
    estimated_hours: float = Field(default=0, description="预计工时（小时）")


class SOPTemplate(BaseModel):
    """SOP 流程模板"""
    template_id: str = Field(..., description="模板编号")
    template_name: str = Field(..., description="模板名称")
    category: str = Field(default="通用", description="模板分类，如'活动策划类'")
    applicable_scenarios: list[str] = Field(default_factory=list, description="适用场景")
    steps: list[SOPStep] = Field(..., description="步骤列表")
    checklist: list[str] = Field(default_factory=list, description="检查清单")
    risk_points: list[str] = Field(default_factory=list, description="风险提示")
    created_from: str = Field(default="", description="来源项目名称")
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"), description="创建时间")
    version: str = Field(default="1.0", description="版本号")


# ────────────────────────── 进度与复盘 ──────────────────────────

class TaskProgressEntry(BaseModel):
    """单条进度记录"""
    task_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    old_status: TaskStatus
    new_status: TaskStatus
    old_progress: int
    new_progress: int
    note: str = Field(default="")


class ProgressReport(BaseModel):
    """进度报告"""
    report_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    project_name: str
    total_tasks: int
    completed: int
    in_progress: int
    pending: int
    delayed: int
    overall_progress: float = Field(description="总体完成百分比")
    task_details: list[dict] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list, description="亮点")
    blockers: list[str] = Field(default_factory=list, description="阻塞项")


class RetrospectiveReport(BaseModel):
    """复盘报告"""
    project_name: str
    report_date: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    summary: str = Field(default="", description="项目总结")
    what_went_well: list[str] = Field(default_factory=list, description="做得好的")
    what_needs_improvement: list[str] = Field(default_factory=list, description="需改进的")
    action_items: list[str] = Field(default_factory=list, description="后续行动项")
    lessons_learned: list[str] = Field(default_factory=list, description="经验教训")
    timeline_analysis: dict = Field(default_factory=dict, description="时间线分析")
    progress_history: list[TaskProgressEntry] = Field(default_factory=list)


# ------------------------------ chat intent ------------------------------

class ChatIntentType(str, Enum):
    """Natural-language chat intent type"""
    UPDATE_TASK = "update_task"
    CLARIFY = "clarify"
    UNKNOWN = "unknown"


class ChatIntent(BaseModel):
    """Structured intent for conversational task updates"""
    intent: ChatIntentType = Field(
        default=ChatIntentType.UNKNOWN,
        description="intent type: update_task / clarify / unknown",
    )
    task_id: Optional[str] = Field(default=None, description="matched task id like T001")
    task_query: str = Field(default="", description="keywords pointing to a task")
    status: Optional[TaskStatus] = Field(default=None, description="new status or null")
    progress: Optional[int] = Field(default=None, ge=0, le=100, description="progress 0-100 or null")
    assignee: Optional[str] = Field(default=None, description="new assignee or null")
    deadline: Optional[str] = Field(default=None, description="YYYY-MM-DD or null")
    note: str = Field(default="", description="note retaining user intent")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="confidence 0-1")
    need_clarification: bool = Field(default=False, description="whether clarification is needed")
    clarify_question: str = Field(default="", description="question when clarifying")
    candidate_task_ids: list[str] = Field(default_factory=list, description="candidate task ids")
