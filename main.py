"""
Boss Task Agent - CLI 入口
统一命令行接口，支持全流程操作。

用法:
    python main.py parse           # 解析语音 → 结构化任务
    python main.py sop             # 生成 SOP 模板
    python main.py status          # 查看任务进度
    python main.py update T001 进行中 50  # 更新任务状态和进度
    python main.py dashboard       # 生成进度看板 HTML
    python main.py table           # 导出本地 Excel 表格
    python main.py retrospective   # 生成复盘报告
    python main.py run-all         # 一键全流程
"""

import argparse
import json
import sys
import webbrowser
from pathlib import Path

# 确保能导入项目模块
sys.path.insert(0, str(Path(__file__).parent))

import config
from models import StructuredInstruction, TaskStatus
from boss_task_agent import (
    ExcelReader, TaskParser, SOPGenerator,
    ProgressTracker, LocalTableExporter, RetrospectiveGenerator,
)
from dashboard_generator import generate_dashboard


def cmd_parse(args):
    """解析语音 → 结构化任务"""
    print("=" * 60)
    print("📢 步骤 1: 读取老板语音摘要")
    print("=" * 60)

    reader = ExcelReader(args.input if hasattr(args, 'input') and args.input else None)
    raw_text = reader.read()
    print(f"📄 读取到 {len(raw_text)} 字符的语音内容:\n")
    print(f"  {raw_text[:200]}{'...' if len(raw_text) > 200 else ''}\n")

    print("=" * 60)
    print("🧠 步骤 2: 调用 LLM 解析为结构化任务")
    print("=" * 60)

    parser = TaskParser()
    instruction = parser.parse(raw_text)

    # 保存
    tracker = ProgressTracker()
    tracker.save_tasks(instruction)

    print(f"\n✅ 解析完成！项目: {instruction.overview.project_name}")
    print(f"   目标: {instruction.overview.objective}")
    print(f"   截止: {instruction.overview.overall_deadline or '未设定'}")
    print(f"   共 {len(instruction.tasks)} 个任务:\n")

    for t in instruction.tasks:
        print(f"   [{t.id}] {t.title}")
        print(f"        优先级: {t.priority.value} | 分类: {t.category.value} | 截止: {t.deadline or '未设定'}")
        if t.deliverables:
            delivs = ", ".join(d.name for d in t.deliverables)
            print(f"        交付物: {delivs}")
        print()

    print(f"💾 结构化任务已保存: {config.TASKS_JSON}")
    return instruction


def cmd_sop(args):
    """生成 SOP 模板"""
    print("=" * 60)
    print("📑 生成 SOP 流程模板")
    print("=" * 60)

    tracker = ProgressTracker()
    instruction = tracker.load_tasks()
    if not instruction:
        print("❌ 请先执行 parse 命令解析任务")
        return

    generator = SOPGenerator()
    sop = generator.generate(instruction)

    # 保存为 Markdown
    md_path = generator.save_as_markdown(sop)

    # 同时保存 JSON
    sop_json_path = config.SOP_DIR / f"{sop.template_id}.json"
    sop_json_path.write_text(
        json.dumps(sop.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n✅ SOP 模板已生成:")
    print(f"   模板名称: {sop.template_name}")
    print(f"   分类: {sop.category}")
    print(f"   步骤数: {len(sop.steps)} 步")
    print(f"   📄 Markdown: {md_path}")
    print(f"   📄 JSON: {sop_json_path}")

    print(f"\n📋 步骤概览:")
    for step in sop.steps:
        print(f"   {step.step_number}. {step.action} ({step.responsible}, ~{step.estimated_hours}h)")

    if sop.risk_points:
        print(f"\n⚠️ 风险提示:")
        for risk in sop.risk_points:
            print(f"   - {risk}")


def cmd_status(args):
    """查看任务进度"""
    tracker = ProgressTracker()
    report = tracker.get_progress_report()
    if not report:
        print("❌ 请先执行 parse 命令解析任务")
        return

    print("=" * 60)
    print(f"📊 项目进度报告: {report.project_name}")
    print("=" * 60)
    print(f"   日期: {report.report_date}")
    print(f"   总体进度: {report.overall_progress}%")
    print()

    # 进度条
    bar_width = 40
    filled = int(bar_width * report.overall_progress / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    print(f"   [{bar}] {report.overall_progress}%")
    print()

    print(f"   📋 总任务: {report.total_tasks}")
    print(f"   ✅ 已完成: {report.completed}")
    print(f"   🔄 进行中: {report.in_progress}")
    print(f"   ⏳ 待开始: {report.pending}")
    print(f"   ⚠️ 已延期: {report.delayed}")
    print()

    print("   ─── 任务详情 ───")
    for d in report.task_details:
        status_icon = {
            "待开始": "⏳", "进行中": "🔄", "已完成": "✅",
            "已延期": "⚠️", "被阻塞": "🚫"
        }.get(d["status"], "❓")
        print(f"   {status_icon} [{d['id']}] {d['title']}")
        print(f"      状态: {d['status']} | 进度: {d['progress']}% | "
              f"优先级: {d['priority']} | 截止: {d['deadline']}")

    if report.blockers:
        print(f"\n   🚨 阻塞项:")
        for b in report.blockers:
            print(f"   - {b}")


def cmd_update(args):
    """更新任务状态"""
    tracker = ProgressTracker()
    tracker.update_task(
        task_id=args.task_id,
        new_status=args.status if args.status else None,
        new_progress=int(args.progress) if args.progress else None,
        note=args.note if args.note else "",
    )


def cmd_dashboard(args):
    """生成进度看板"""
    print("=" * 60)
    print("📊 生成任务进度看板")
    print("=" * 60)

    tracker = ProgressTracker()
    instruction = tracker.load_tasks()
    if not instruction:
        print("❌ 请先执行 parse 命令解析任务")
        return

    path = generate_dashboard(instruction)
    print(f"\n✅ 看板已生成: {path}")

    if not (hasattr(args, 'no_open') and args.no_open):
        print("🌐 正在打开浏览器...")
        webbrowser.open(str(path))


def cmd_table(args):
    """导出本地 Excel 表格"""
    print("=" * 60)
    print("📊 导出本地 Excel 表格")
    print("=" * 60)

    tracker = ProgressTracker()
    instruction = tracker.load_tasks()
    if not instruction:
        print("❌ 请先执行 parse 命令解析任务")
        return

    exporter = LocalTableExporter()
    path = exporter.export(instruction)
    print(f"\n✅ 表格已导出: {path}")


def cmd_retrospective(args):
    """生成复盘报告"""
    print("=" * 60)
    print("📝 生成复盘报告")
    print("=" * 60)

    tracker = ProgressTracker()
    instruction = tracker.load_tasks()
    if not instruction:
        print("❌ 请先执行 parse 命令解析任务")
        return

    generator = RetrospectiveGenerator()
    report, markdown = generator.generate(instruction, tracker.history)

    print(f"\n✅ 复盘报告已生成: {config.RETROSPECTIVE_MD}")
    print(f"   项目: {report.project_name}  报告日期: {report.report_date}")
    print(f"   做得好 {len(report.what_went_well)} 条 / "
          f"需改进 {len(report.what_needs_improvement)} 条 / "
          f"行动项 {len(report.action_items)} 条 / "
          f"经验教训 {len(report.lessons_learned)} 条")
    print("\n" + "─" * 60)
    print(markdown[:500])
    if len(markdown) > 500:
        print(f"\n... (完整报告请查看 {config.RETROSPECTIVE_MD})")


def cmd_run_all(args):
    """一键全流程"""
    print("🚀 " + "=" * 56 + " 🚀")
    print("   Boss Task Agent - 一键全流程执行")
    print("🚀 " + "=" * 56 + " 🚀\n")

    # Step 1: 解析
    instruction = cmd_parse(args)
    if not instruction:
        return
    print("\n" + "─" * 60 + "\n")

    # Step 2: SOP
    cmd_sop(args)
    print("\n" + "─" * 60 + "\n")

    # Step 3: 导出表格
    cmd_table(args)
    print("\n" + "─" * 60 + "\n")

    # Step 4: 看板
    args.no_open = True  # 不自动打开浏览器
    cmd_dashboard(args)
    print("\n" + "─" * 60 + "\n")

    # Step 5: 进度报告
    cmd_status(args)

    print("\n" + "═" * 60)
    print("🎉 全流程执行完成！")
    print(f"   📄 结构化任务: {config.TASKS_JSON}")
    print(f"   📑 SOP 模板:   {config.SOP_DIR}")
    print(f"   📊 Excel 表格: {config.LOCAL_TABLE_XLSX}")
    print(f"   🌐 进度看板:   {config.DASHBOARD_HTML}")
    print("═" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Boss Task Agent - 老板语音→结构化工作指令智能体",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py parse                      # 解析语音
  python main.py sop                        # 生成 SOP
  python main.py status                     # 查看进度
  python main.py update T001 进行中 50      # 更新任务
  python main.py dashboard                  # 生成看板
  python main.py table                      # 导出表格
  python main.py retrospective              # 生成复盘
  python main.py run-all                    # 一键全流程
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # parse
    p_parse = subparsers.add_parser("parse", help="解析语音 → 结构化任务")
    p_parse.add_argument("--input", "-i", help="指定输入 Excel 文件路径")
    p_parse.set_defaults(func=cmd_parse)

    # sop
    p_sop = subparsers.add_parser("sop", help="生成 SOP 流程模板")
    p_sop.set_defaults(func=cmd_sop)

    # status
    p_status = subparsers.add_parser("status", help="查看任务进度")
    p_status.set_defaults(func=cmd_status)

    # update
    p_update = subparsers.add_parser("update", help="更新任务状态")
    p_update.add_argument("task_id", help="任务编号，如 T001")
    p_update.add_argument("status", nargs="?", default=None, help="新状态: 待开始/进行中/已完成/已延期/被阻塞")
    p_update.add_argument("progress", nargs="?", default=None, help="完成百分比 0-100")
    p_update.add_argument("--note", "-n", default="", help="备注说明")
    p_update.set_defaults(func=cmd_update)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="生成进度看板 HTML")
    p_dash.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    p_dash.set_defaults(func=cmd_dashboard)

    # table
    p_table = subparsers.add_parser("table", help="导出本地 Excel 表格")
    p_table.set_defaults(func=cmd_table)

    # retrospective
    p_retro = subparsers.add_parser("retrospective", help="生成复盘报告")
    p_retro.set_defaults(func=cmd_retrospective)

    # run-all
    p_all = subparsers.add_parser("run-all", help="一键全流程")
    p_all.add_argument("--input", "-i", help="指定输入 Excel 文件路径")
    p_all.set_defaults(func=cmd_run_all)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 检查 API Key
    if args.command in ("parse", "sop", "retrospective", "run-all"):
        if not config.OPENAI_API_KEY:
            print("❌ 错误: 未设置 OPENAI_API_KEY 环境变量")
            print("   请设置: $env:OPENAI_API_KEY = 'your-api-key'")
            sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
