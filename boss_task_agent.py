"""
Boss Task Agent - 核心智能体
将老板语音摘要解析为结构化任务、生成 SOP、跟踪进度、生成复盘。
"""

import json
import re
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Type, TypeVar

import openpyxl
from openai import OpenAI
from pydantic import BaseModel, ValidationError

import config
from models import (
    StructuredInstruction, ProjectOverview, Task, TaskStatus, TaskPriority,
    TaskCategory, Deliverable, SOPTemplate, SOPStep,
    ProgressReport, RetrospectiveReport, TaskProgressEntry,
)

T = TypeVar("T", bound=BaseModel)


# ════════════════════════════════════════════════════════════════
#  0. LLM 自我修正重试引擎 (Auto-Retry with Self-Correction)
# ════════════════════════════════════════════════════════════════

MAX_RETRIES = 3  # 最大重试次数


def _llm_call_with_retry(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
    target_model: Type[T],
    temperature: float = 0.2,
    extra_data: dict | None = None,
) -> T:
    """
    带自我修正的 LLM 调用封装。

    流程:
      1. 调用 LLM 获取 JSON 响应
      2. 用 Pydantic 模型校验
      3. 若校验失败，将错误信息反馈给 LLM 并要求修正
      4. 最多重试 MAX_RETRIES 次

    Args:
        client: OpenAI 客户端
        model: 模型名称
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        target_model: 目标 Pydantic 模型类
        temperature: 生成温度
        extra_data: 额外注入到 JSON 中的字段（如 raw_input）

    Returns:
        校验通过的 Pydantic 模型实例
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # ── Step 1: 调用 LLM ──
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content

            # ── Step 2: 解析 JSON ──
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON 解析失败: {e}\n原始返回:\n{content[:500]}")

            # 注入额外字段
            if extra_data:
                data.update(extra_data)

            # ── Step 3: Pydantic 强类型校验 ──
            result = target_model(**data)

            if attempt > 1:
                print(f"   ✅ 第 {attempt} 次重试成功！自我修正生效。")

            return result

        except (ValidationError, ValueError, KeyError, TypeError) as e:
            last_error = e
            error_type = type(e).__name__
            error_msg = str(e)

            # 截断过长的错误信息，避免 Token 浪费
            if len(error_msg) > 800:
                error_msg = error_msg[:800] + "...(截断)"

            if attempt < MAX_RETRIES:
                print(f"   ⚠️ 第 {attempt} 次解析失败 ({error_type})，正在自我修正...")

                # ── Step 4: 构造修正指令，追加到对话历史 ──
                correction_prompt = (
                    f"你刚才返回的 JSON 数据校验失败。\n"
                    f"错误类型: {error_type}\n"
                    f"错误详情:\n{error_msg}\n\n"
                    f"请仔细检查并修正以下问题：\n"
                    f"1. 确保所有必填字段都存在且类型正确\n"
                    f"2. 枚举字段只能使用指定的值\n"
                    f"3. 数组字段不能为 null，至少为空数组 []\n"
                    f"4. 只输出修正后的完整合法 JSON，不要输出任何解释文字"
                )

                # 将 LLM 上一次的回复和修正指令加入对话上下文
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": correction_prompt})
            else:
                print(f"   ❌ 第 {attempt} 次解析仍然失败，已达最大重试次数。")

    # 所有重试都失败，抛出最后一个错误
    raise RuntimeError(
        f"LLM 输出经过 {MAX_RETRIES} 次自我修正后仍无法通过校验。\n"
        f"最后一次错误: {last_error}"
    )


# ════════════════════════════════════════════════════════════════
#  1. Excel 读取器
# ════════════════════════════════════════════════════════════════

class ExcelReader:
    """从 Workbook.xlsx 读取老板语音转录内容"""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else config.WORKBOOK_PATH

    def read(self) -> str:
        """读取全部内容并拼接为文本"""
        wb = openpyxl.load_workbook(str(self.path), read_only=True)
        ws = wb.active
        lines: list[str] = []
        for row in ws.iter_rows(min_row=1, values_only=True):
            for cell in row:
                if cell is not None:
                    text = str(cell).strip()
                    if text:
                        lines.append(text)
        wb.close()
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
#  2. LLM 任务解析器
# ════════════════════════════════════════════════════════════════

class TaskParser:
    """调用 OpenAI API 将自然语言转为结构化任务"""

    def __init__(self):
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
        )
        self.model = config.OPENAI_MODEL

    def parse(self, raw_text: str) -> StructuredInstruction:
        """解析语音文本 → 结构化指令（带自我修正重试）"""
        today = datetime.now().strftime("%Y-%m-%d")

        # 构造 JSON Schema 描述供 LLM 参考
        schema_hint = self._build_schema_hint()

        system_prompt = config.TASK_PARSE_SYSTEM_PROMPT.replace("{today}", today)
        user_prompt = f"""以下是老板的语音转录内容：

---
{raw_text}
---

请将上述内容解析为结构化工作指令。今天日期是 {today}。

输出必须是合法 JSON，严格遵循以下结构：
{schema_hint}

注意：
- deadline 格式为 YYYY-MM-DD，根据语音中"这两天"等线索推断
- 每个任务必须有至少一个交付物
- 识别任务间的先后依赖关系
- 只输出 JSON，不要输出其他内容"""

        return _llm_call_with_retry(
            client=self.client,
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            target_model=StructuredInstruction,
            temperature=0.2,
            extra_data={"raw_input": raw_text},
        )

    def _build_schema_hint(self) -> str:
        """构建供 LLM 参考的 JSON 结构提示"""
        return json.dumps({
            "overview": {
                "project_name": "项目名称",
                "background": "项目背景",
                "objective": "项目目标",
                "scope": "项目范围",
                "overall_deadline": "YYYY-MM-DD",
                "key_stakeholders": ["干系人1"]
            },
            "tasks": [{
                "id": "T001",
                "title": "任务标题",
                "description": "任务详细描述",
                "category": "策划|执行|内容制作|审核|汇报|其他",
                "priority": "P0-紧急|P1-重要|P2-一般",
                "assignee": "待分配",
                "deadline": "YYYY-MM-DD",
                "deliverables": [{"name": "交付物名称", "format": "格式", "description": "描述"}],
                "status": "待开始",
                "dependencies": [],
                "notes": ""
            }]
        }, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════
#  3. SOP 流程生成器
# ════════════════════════════════════════════════════════════════

class SOPGenerator:
    """从结构化任务自动生成可复用的 SOP 模板"""

    def __init__(self):
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
        )
        self.model = config.OPENAI_MODEL

    def generate(self, instruction: StructuredInstruction) -> SOPTemplate:
        """根据项目任务生成 SOP 模板"""
        tasks_summary = json.dumps(
            [t.model_dump() for t in instruction.tasks],
            ensure_ascii=False, indent=2
        )

        schema_hint = json.dumps({
            "template_id": "SOP-001",
            "template_name": "模板名称",
            "category": "活动策划类",
            "applicable_scenarios": ["场景1", "场景2"],
            "steps": [{
                "step_number": 1,
                "action": "动作描述",
                "responsible": "负责角色",
                "inputs": ["输入物"],
                "outputs": ["输出物"],
                "tools": ["所需工具"],
                "quality_criteria": "质量标准",
                "estimated_hours": 2.0
            }],
            "checklist": ["检查项1"],
            "risk_points": ["风险1"],
            "created_from": instruction.overview.project_name
        }, ensure_ascii=False, indent=2)

        user_prompt = f"""以下是一个项目的结构化任务清单：

项目名称：{instruction.overview.project_name}
项目目标：{instruction.overview.objective}

任务列表：
{tasks_summary}

请基于这些任务提炼一份通用 SOP 流程模板。
- 去除项目特定细节，保留通用步骤
- 适用于同类型项目的复用

输出必须是合法 JSON，结构如下：
{schema_hint}

只输出 JSON，不要输出其他内容。"""

        return _llm_call_with_retry(
            client=self.client,
            model=self.model,
            system_prompt=config.SOP_GENERATE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            target_model=SOPTemplate,
            temperature=0.3,
            extra_data={"created_from": instruction.overview.project_name},
        )

    def save_as_markdown(self, sop: SOPTemplate) -> Path:
        """将 SOP 模板保存为 Markdown 文件"""
        filename = f"{sop.template_id}_{sop.template_name}.md"
        # 清理文件名中的特殊字符
        filename = re.sub(r'[\\/:*?"<>|]', '_', filename)
        filepath = config.SOP_DIR / filename

        lines = [
            f"# {sop.template_name}",
            f"\n> **模板编号**: {sop.template_id}  ",
            f"> **分类**: {sop.category}  ",
            f"> **版本**: {sop.version}  ",
            f"> **创建时间**: {sop.created_at}  ",
            f"> **来源项目**: {sop.created_from}",
            f"\n## 适用场景\n",
        ]
        for s in sop.applicable_scenarios:
            lines.append(f"- {s}")

        lines.append(f"\n## 操作步骤\n")
        for step in sop.steps:
            lines.append(f"### 步骤 {step.step_number}: {step.action}\n")
            lines.append(f"- **负责人**: {step.responsible}")
            if step.inputs:
                lines.append(f"- **输入**: {', '.join(step.inputs)}")
            if step.outputs:
                lines.append(f"- **输出**: {', '.join(step.outputs)}")
            if step.tools:
                lines.append(f"- **工具**: {', '.join(step.tools)}")
            if step.quality_criteria:
                lines.append(f"- **质量标准**: {step.quality_criteria}")
            if step.estimated_hours > 0:
                lines.append(f"- **预计工时**: {step.estimated_hours} 小时")
            lines.append("")

        if sop.checklist:
            lines.append("## 检查清单\n")
            for item in sop.checklist:
                lines.append(f"- [ ] {item}")
            lines.append("")

        if sop.risk_points:
            lines.append("## ⚠️ 风险提示\n")
            for risk in sop.risk_points:
                lines.append(f"- ⚠️ {risk}")
            lines.append("")

        filepath.write_text("\n".join(lines), encoding="utf-8")
        return filepath


# ════════════════════════════════════════════════════════════════
#  4. 进度跟踪器
# ════════════════════════════════════════════════════════════════

class ProgressTracker:
    """任务进度跟踪与状态更新"""

    def __init__(self):
        self.history: list[TaskProgressEntry] = []
        self._load_history()

    def _load_history(self):
        """加载历史进度记录"""
        if config.PROGRESS_HISTORY_JSON.exists():
            data = json.loads(config.PROGRESS_HISTORY_JSON.read_text(encoding="utf-8"))
            self.history = [TaskProgressEntry(**e) for e in data]

    def _save_history(self):
        """保存进度记录"""
        data = [e.model_dump() for e in self.history]
        config.PROGRESS_HISTORY_JSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_tasks(self) -> StructuredInstruction | None:
        """加载当前任务数据"""
        if not config.TASKS_JSON.exists():
            return None
        data = json.loads(config.TASKS_JSON.read_text(encoding="utf-8"))
        return StructuredInstruction(**data)

    def save_tasks(self, instruction: StructuredInstruction):
        """保存任务数据"""
        config.TASKS_JSON.write_text(
            json.dumps(instruction.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def update_task(self, task_id: str, new_status: str | None = None,
                    new_progress: int | None = None, note: str = "") -> Task | None:
        """更新单个任务的状态和进度"""
        instruction = self.load_tasks()
        if not instruction:
            print("❌ 未找到任务数据，请先执行 parse 命令")
            return None

        target = None
        for task in instruction.tasks:
            if task.id == task_id:
                target = task
                break

        if not target:
            print(f"❌ 未找到任务 {task_id}")
            return None

        old_status = target.status
        old_progress = target.progress

        if new_status:
            target.status = TaskStatus(new_status)
        if new_progress is not None:
            target.progress = new_progress

        target.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 记录进度历史
        entry = TaskProgressEntry(
            task_id=task_id,
            old_status=old_status,
            new_status=target.status,
            old_progress=old_progress,
            new_progress=target.progress,
            note=note,
        )
        self.history.append(entry)

        self.save_tasks(instruction)
        self._save_history()

        print(f"✅ 任务 {task_id} 已更新: {old_status.value} → {target.status.value}, "
              f"进度 {old_progress}% → {target.progress}%")
        return target

    def get_progress_report(self) -> ProgressReport | None:
        """生成进度报告"""
        instruction = self.load_tasks()
        if not instruction:
            return None

        tasks = instruction.tasks
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
        pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        delayed = sum(1 for t in tasks if t.status == TaskStatus.DELAYED)

        overall = sum(t.progress for t in tasks) / total if total > 0 else 0

        details = []
        for t in tasks:
            details.append({
                "id": t.id,
                "title": t.title,
                "status": t.status.value,
                "progress": t.progress,
                "priority": t.priority.value,
                "deadline": t.deadline or "未设定",
                "assignee": t.assignee,
            })

        # 找出阻塞项和亮点
        blockers = [f"{t.id} {t.title}: 已延期" for t in tasks if t.status == TaskStatus.DELAYED]
        highlights = [f"{t.id} {t.title}: 已完成" for t in tasks if t.status == TaskStatus.COMPLETED]

        return ProgressReport(
            project_name=instruction.overview.project_name,
            total_tasks=total,
            completed=completed,
            in_progress=in_progress,
            pending=pending,
            delayed=delayed,
            overall_progress=round(overall, 1),
            task_details=details,
            highlights=highlights,
            blockers=blockers,
        )


# ════════════════════════════════════════════════════════════════
#  5. 本地表格生成器（替代飞书多维表格）
# ════════════════════════════════════════════════════════════════

class LocalTableExporter:
    """将任务导出为本地 Excel 表格"""

    def export(self, instruction: StructuredInstruction) -> Path:
        """导出任务到本地 Excel"""
        wb = openpyxl.Workbook()

        # ── Sheet 1: 任务清单 ──
        ws = wb.active
        ws.title = "任务清单"

        headers = ["任务ID", "标题", "描述", "分类", "优先级", "负责人",
                    "截止日期", "状态", "进度%", "交付物", "依赖任务", "备注",
                    "创建时间", "更新时间"]
        ws.append(headers)

        # 设置表头样式
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin'),
        )

        for col_idx, _ in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = thin_border

        # 写入数据
        status_colors = {
            "待开始": "FFF2CC",
            "进行中": "D6E4F0",
            "已完成": "C6EFCE",
            "已延期": "FFC7CE",
            "被阻塞": "F4B084",
        }

        for task in instruction.tasks:
            deliverables_str = "; ".join([d.name for d in task.deliverables])
            deps_str = ", ".join(task.dependencies) if task.dependencies else ""

            row_data = [
                task.id, task.title, task.description, task.category.value,
                task.priority.value, task.assignee, task.deadline or "",
                task.status.value, task.progress, deliverables_str, deps_str,
                task.notes, task.created_at, task.updated_at
            ]
            ws.append(row_data)

            # 状态列着色
            row_num = ws.max_row
            status_cell = ws.cell(row=row_num, column=8)
            color = status_colors.get(task.status.value, "FFFFFF")
            status_cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")

            # 设置边框
            for col_idx in range(1, len(headers) + 1):
                ws.cell(row=row_num, column=col_idx).border = thin_border

        # 调整列宽
        col_widths = [8, 20, 30, 10, 10, 10, 12, 10, 8, 25, 12, 20, 16, 16]
        for i, width in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width

        # ── Sheet 2: 项目概览 ──
        ws2 = wb.create_sheet("项目概览")
        overview_data = [
            ["项目名称", instruction.overview.project_name],
            ["项目目标", instruction.overview.objective],
            ["项目背景", instruction.overview.background],
            ["项目范围", instruction.overview.scope],
            ["总体截止", instruction.overview.overall_deadline or ""],
            ["干系人", ", ".join(instruction.overview.key_stakeholders)],
            ["解析时间", instruction.parsed_at],
        ]
        for row in overview_data:
            ws2.append(row)

        ws2.column_dimensions['A'].width = 15
        ws2.column_dimensions['B'].width = 50

        for row_num in range(1, len(overview_data) + 1):
            ws2.cell(row=row_num, column=1).font = Font(bold=True)
            ws2.cell(row=row_num, column=1).fill = PatternFill(
                start_color="E2EFDA", end_color="E2EFDA", fill_type="solid"
            )

        output_path = config.LOCAL_TABLE_XLSX
        wb.save(str(output_path))
        return output_path


# ════════════════════════════════════════════════════════════════
#  6. 复盘报告生成器
# ════════════════════════════════════════════════════════════════

class RetrospectiveGenerator:
    """生成复盘报告：LLM → 结构化 RetrospectiveReport → Markdown 渲染"""

    def __init__(self):
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
        )
        self.model = config.OPENAI_MODEL

    def generate(self, instruction: StructuredInstruction,
                 history: list[TaskProgressEntry]) -> tuple[RetrospectiveReport, str]:
        """生成结构化复盘报告并渲染为 Markdown。

        Returns:
            (report, markdown_text)
        """
        tasks_data = json.dumps(
            [t.model_dump() for t in instruction.tasks],
            ensure_ascii=False, indent=2
        )
        history_data = json.dumps(
            [h.model_dump() for h in history],
            ensure_ascii=False, indent=2
        )

        schema_hint = json.dumps({
            "project_name": instruction.overview.project_name,
            "report_date": "YYYY-MM-DD",
            "summary": "项目总体总结，2-4 句话",
            "what_went_well": ["做得好的点1", "做得好的点2"],
            "what_needs_improvement": ["需改进点1", "需改进点2"],
            "action_items": ["具体行动项1", "具体行动项2"],
            "lessons_learned": ["经验教训1", "经验教训2"],
            "timeline_analysis": {
                "on_time_tasks": 0,
                "delayed_tasks": 0,
                "bottleneck": "关键瓶颈描述",
                "notes": "时间线其他观察"
            },
            "progress_history": []
        }, ensure_ascii=False, indent=2)

        user_prompt = f"""请为以下项目生成结构化复盘报告：

## 项目信息
- 项目名称：{instruction.overview.project_name}
- 项目目标：{instruction.overview.objective}
- 总体截止：{instruction.overview.overall_deadline or '未设定'}

## 任务执行情况
{tasks_data}

## 进度变更历史
{history_data}

输出必须是合法 JSON，严格遵循以下结构：
{schema_hint}

要求：
- 每个列表字段至少 2 条，具体且可操作，避免空话
- timeline_analysis 中的数字必须从任务数据中真实统计
- progress_history 字段固定输出空数组 []（由系统自动注入完整记录）
- 只输出 JSON，不要输出解释或 Markdown"""

        history_payload = [h.model_dump(mode="json") for h in history]

        report = _llm_call_with_retry(
            client=self.client,
            model=self.model,
            system_prompt=config.RETROSPECTIVE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            target_model=RetrospectiveReport,
            temperature=0.4,
            extra_data={
                "project_name": instruction.overview.project_name,
                "progress_history": history_payload,
            },
        )

        markdown_text = self._render_markdown(report)
        config.RETROSPECTIVE_MD.write_text(markdown_text, encoding="utf-8")
        return report, markdown_text

    @staticmethod
    def _render_markdown(report: RetrospectiveReport) -> str:
        """将结构化报告渲染为可读的 Markdown。"""
        lines = [
            f"# {report.project_name} 复盘报告",
            "",
            f"> 报告日期：{report.report_date}",
            "",
            "## 项目总结",
            "",
            report.summary or "_（无）_",
            "",
            "## 做得好的方面",
            "",
        ]
        lines += [f"- {item}" for item in report.what_went_well] or ["_（无）_"]
        lines += ["", "## 需要改进的方面", ""]
        lines += [f"- {item}" for item in report.what_needs_improvement] or ["_（无）_"]
        lines += ["", "## 经验教训", ""]
        lines += [f"- {item}" for item in report.lessons_learned] or ["_（无）_"]
        lines += ["", "## 后续行动项", ""]
        lines += [f"- [ ] {item}" for item in report.action_items] or ["_（无）_"]

        lines += ["", "## 时间线分析", ""]
        if report.timeline_analysis:
            for k, v in report.timeline_analysis.items():
                lines.append(f"- **{k}**: {v}")
        else:
            lines.append("_（无）_")

        if report.progress_history:
            lines += ["", "## 进度变更历史", ""]
            lines.append("| 时间 | 任务 | 状态变化 | 进度变化 | 备注 |")
            lines.append("|---|---|---|---|---|")
            for h in report.progress_history:
                status_change = f"{h.old_status.value} → {h.new_status.value}"
                progress_change = f"{h.old_progress}% → {h.new_progress}%"
                lines.append(
                    f"| {h.timestamp} | {h.task_id} | {status_change} | {progress_change} | {h.note} |"
                )

        return "\n".join(lines) + "\n"
