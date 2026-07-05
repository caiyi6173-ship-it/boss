"""
模拟数据测试 - 验证 Dashboard 和表格导出功能
无需 OpenAI API Key
"""
import sys
sys.path.insert(0, '.')

from models import *
from boss_task_agent import LocalTableExporter, ProgressTracker
from dashboard_generator import generate_dashboard
import config

# 模拟结构化指令数据
instruction = StructuredInstruction(
    overview=ProjectOverview(
        project_name="商场音乐节活动策划",
        background="老板要求策划一场商场音乐节宣传活动",
        objective="通过视频拍摄和社交媒体发布，为商场音乐节活动做宣传推广",
        scope="活动策划、视频拍摄、小红书/抖音内容发布、文档整理",
        overall_deadline="2026-07-06",
        key_stakeholders=["老板", "执行团队"],
    ),
    tasks=[
        Task(
            id="T001",
            title="商场音乐节活动策划方案",
            description="制定完整的商场音乐节活动策划方案，包括活动流程、宣传策略、人员安排等",
            category=TaskCategory.PLANNING,
            priority=TaskPriority.P0,
            assignee="待分配",
            deadline="2026-07-05",
            deliverables=[
                Deliverable(name="活动策划方案文档", format="PDF/Word", description="完整的策划方案"),
                Deliverable(name="活动时间表", format="Excel", description="详细时间安排"),
            ],
            status=TaskStatus.PENDING,
            progress=0,
        ),
        Task(
            id="T002",
            title="宣传视频拍摄",
            description="为音乐节活动拍摄宣传视频素材",
            category=TaskCategory.CONTENT,
            priority=TaskPriority.P0,
            assignee="待分配",
            deadline="2026-07-06",
            deliverables=[
                Deliverable(name="宣传视频", format="MP4", description="15-60秒短视频"),
                Deliverable(name="视频素材原片", format="MOV/MP4", description="未剪辑原始素材"),
            ],
            status=TaskStatus.PENDING,
            progress=0,
            dependencies=["T001"],
        ),
        Task(
            id="T003",
            title="小红书内容制作与发布",
            description="整理并制作小红书平台的推广内容，包括图文和短视频",
            category=TaskCategory.CONTENT,
            priority=TaskPriority.P1,
            assignee="待分配",
            deadline="2026-07-06",
            deliverables=[
                Deliverable(name="小红书图文内容", format="图文", description="至少3篇推广帖"),
                Deliverable(name="小红书文档整理", format="Word/Excel", description="内容规划和发布记录"),
            ],
            status=TaskStatus.PENDING,
            progress=0,
            dependencies=["T002"],
        ),
        Task(
            id="T004",
            title="抖音内容制作与发布",
            description="制作抖音平台的短视频内容并发布",
            category=TaskCategory.CONTENT,
            priority=TaskPriority.P1,
            assignee="待分配",
            deadline="2026-07-06",
            deliverables=[
                Deliverable(name="抖音短视频", format="MP4", description="适配抖音的竖版短视频"),
                Deliverable(name="抖音内容文档", format="Word/Excel", description="内容规划和发布记录"),
            ],
            status=TaskStatus.PENDING,
            progress=0,
            dependencies=["T002"],
        ),
        Task(
            id="T005",
            title="项目总结文档",
            description="汇总整个项目的执行情况，撰写总结文档",
            category=TaskCategory.REPORTING,
            priority=TaskPriority.P1,
            assignee="待分配",
            deadline="2026-07-06",
            deliverables=[
                Deliverable(name="项目总结文档", format="Word/PDF", description="完整的项目总结报告"),
            ],
            status=TaskStatus.PENDING,
            progress=0,
            dependencies=["T003", "T004"],
        ),
    ],
    raw_input="我有一个新工作，你来接收一下。\n明天有个商场的活动，帮我策划一下。\n主要内容是宣传下一个音乐节。\n需要拍视频和上传小红书。\n你需要整理小红书的文档和抖音的内容。\n这两天之内把这个任务结束。\n还要总结成文档。\n你好。",
)

# 保存任务
tracker = ProgressTracker()
tracker.save_tasks(instruction)
print(f"✅ 模拟任务数据已保存: {config.TASKS_JSON}")

# 生成 Dashboard
dashboard_path = generate_dashboard(instruction)
print(f"✅ Dashboard 已生成: {dashboard_path}")

# 导出 Excel
exporter = LocalTableExporter()
table_path = exporter.export(instruction)
print(f"✅ Excel 表格已导出: {table_path}")

# 显示进度
report = tracker.get_progress_report()
print(f"\n📊 进度报告:")
print(f"   项目: {report.project_name}")
print(f"   总任务: {report.total_tasks}")
print(f"   总体进度: {report.overall_progress}%")
for d in report.task_details:
    print(f"   [{d['id']}] {d['title']} - {d['status']} ({d['progress']}%)")
