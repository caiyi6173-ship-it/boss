"""
Dashboard Generator - 生成精美的 HTML 任务进度看板
包含高级毛玻璃拟态暗色主题、实时过滤检索、以及基于依赖推导的自适应 Gantt 进度时间线。
纯静态单文件 HTML，支持离线加载与完美移动端响应。
"""

import json
import html
from pathlib import Path
from models import StructuredInstruction, TaskStatus
import config


def _format_evidence_time(seconds: float) -> str:
    total_ms = max(0, round(float(seconds) * 1000))
    minutes, remainder = divmod(total_ms, 60_000)
    secs, millis = divmod(remainder, 1_000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def generate_dashboard(instruction: StructuredInstruction) -> Path:
    """生成包含动态甘特图与实时过滤的 HTML 看板"""

    tasks = instruction.tasks
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
    pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
    delayed = sum(1 for t in tasks if t.status == TaskStatus.DELAYED)
    blocked = sum(1 for t in tasks if t.status == TaskStatus.BLOCKED)
    overall_progress = round(sum(t.progress for t in tasks) / total, 1) if total else 0

    # 导出任务 JSON 供前端 JavaScript 交互使用
    tasks_json_data = json.dumps(
        [json.loads(t.model_dump_json()) for t in tasks], ensure_ascii=False
    ).replace("</", "<\\/")
    segments_json_data = json.dumps(
        [json.loads(segment.model_dump_json()) for segment in instruction.source_segments],
        ensure_ascii=False,
    ).replace("</", "<\\/")

    # 页面基础数据（HTML 转义防止 XSS）
    esc = html.escape
    project_name = esc(instruction.overview.project_name)
    objective = esc(instruction.overview.objective)
    scope_or_obj = esc(instruction.overview.scope or instruction.overview.objective)
    overall_deadline = esc(instruction.overview.overall_deadline or "未设定")
    parsed_at = esc(instruction.parsed_at)
    segment_map = {segment.id: segment for segment in instruction.source_segments}
    project_evidence_parts = []
    for item in instruction.overview.evidence:
        segment = segment_map.get(item.source_segment_id)
        role = esc(segment.speaker_role if segment else "来源未知")
        source_meta = role
        if segment:
            if segment.start_seconds is not None and segment.end_seconds is not None:
                source_meta += " · " + esc(
                    f"{_format_evidence_time(segment.start_seconds)}-"
                    f"{_format_evidence_time(segment.end_seconds)}"
                )
            source_meta += " · " + esc(segment.source_file)
        project_evidence_parts.append(
            '<div class="project-evidence-item">'
            f'<strong>{esc(item.field.value)}</strong> · {source_meta} · '
            f'“{esc(item.source_quote)}” · {item.confidence * 100:.0f}%'
            "</div>"
        )
    project_evidence_html = "".join(project_evidence_parts) or (
        '<div class="project-evidence-item">历史项目暂无项目级证据</div>'
    )

    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📋 {project_name} - 任务看板</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

        :root {
            --bg-primary: #0a0a16;
            --bg-secondary: #111126;
            --bg-card: rgba(255, 255, 255, 0.03);
            --bg-glass: rgba(255, 255, 255, 0.06);
            --text-primary: #f1f1f8;
            --text-secondary: #9e9eb8;
            --text-muted: #626280;
            --accent-blue: #3b82f6;
            --accent-purple: #8b5cf6;
            --accent-pink: #ec4899;
            --accent-green: #10b981;
            --accent-orange: #f97316;
            --accent-yellow: #f59e0b;
            --border-color: rgba(255, 255, 255, 0.08);
            --border-glow: rgba(59, 130, 246, 0.15);
            --shadow-glow: 0 0 40px rgba(59, 130, 246, 0.08);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
            padding-bottom: 3rem;
        }

        /* ── 背景光晕动效 ── */
        body::before {
            content: '';
            position: fixed;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle at 15% 30%, rgba(59, 130, 246, 0.08) 0%, transparent 50%),
                        radial-gradient(circle at 85% 15%, rgba(139, 92, 246, 0.08) 0%, transparent 50%),
                        radial-gradient(circle at 50% 85%, rgba(236, 72, 153, 0.05) 0%, transparent 50%);
            animation: bgShift 25s ease-in-out infinite;
            z-index: -1;
        }

        @keyframes bgShift {
            0%, 100% { transform: translate(0, 0); }
            50% { transform: translate(-3%, -5%); }
        }

        /* ── 全局页面容器 ── */
        .page-container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }

        /* ── Header ── */
        .header {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 2.5rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            box-shadow: var(--shadow-glow);
            position: relative;
            overflow: hidden;
        }

        .header::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: linear-gradient(to bottom, var(--accent-blue), var(--accent-purple));
        }

        .header h1 {
            font-size: 2.2rem;
            font-weight: 800;
            background: linear-gradient(135deg, #ffffff 30%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.6rem;
        }

        .subtitle {
            font-size: 1.1rem;
            color: var(--text-secondary);
            margin-bottom: 1.5rem;
            line-height: 1.5;
        }

        .header-meta {
            display: flex;
            gap: 1.8rem;
            font-size: 0.88rem;
            color: var(--text-muted);
            flex-wrap: wrap;
        }

        .header-meta span {
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }

        .project-evidence-list {
            margin-top: 1rem;
            padding-top: 0.8rem;
            border-top: 1px solid var(--border-color);
        }

        .project-evidence-item {
            color: var(--text-secondary);
            font-size: 0.76rem;
            line-height: 1.5;
            margin-top: 0.25rem;
        }

        .project-evidence-item strong { color: #93c5fd; }

        /* ── 仪表盘卡片 ── */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.2rem;
            text-align: center;
            backdrop-filter: blur(12px);
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
            transition: transform 0.25s ease, border-color 0.25s ease;
        }

        .stat-card:hover {
            transform: translateY(-3px);
            border-color: var(--border-glow);
        }

        .stat-value {
            font-size: 1.8rem;
            font-weight: 800;
            margin-bottom: 0.3rem;
            color: #ffffff;
        }

        .stat-label {
            font-size: 0.8rem;
            color: var(--text-muted);
            font-weight: 500;
        }

        .stat-card:nth-child(2) .stat-value { color: var(--accent-green); }
        .stat-card:nth-child(3) .stat-value { color: var(--accent-blue); }
        .stat-card:nth-child(4) .stat-value { color: var(--accent-yellow); }
        .stat-card:nth-child(5) .stat-value { color: var(--accent-orange); }
        .stat-card:nth-child(6) .stat-value {
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        /* ── 进度条 ── */
        .overall-progress {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.8rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(12px);
        }

        .overall-progress h2 {
            font-size: 1.1rem;
            margin-bottom: 1rem;
            font-weight: 700;
        }

        .overall-bar {
            height: 12px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            overflow: hidden;
            margin-bottom: 0.6rem;
            position: relative;
        }

        .overall-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple));
            border-radius: 6px;
            transition: width 0.8s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
        }

        .overall-text {
            font-size: 0.85rem;
            color: var(--text-secondary);
            text-align: right;
            font-weight: 600;
        }

        /* ── 交互过滤与检索区 ── */
        .filter-section {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.2rem 1.6rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(12px);
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1.5rem;
            flex-wrap: wrap;
        }

        .search-box {
            flex: 1;
            min-width: 280px;
            position: relative;
        }

        .search-input {
            width: 100%;
            height: 40px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 0 1rem 0 2.5rem;
            color: #ffffff;
            font-family: inherit;
            font-size: 0.9rem;
            transition: all 0.25s ease;
        }

        .search-input:focus {
            outline: none;
            border-color: var(--accent-blue);
            background: rgba(255, 255, 255, 0.07);
            box-shadow: 0 0 12px rgba(59, 130, 246, 0.2);
        }

        .search-icon {
            position: absolute;
            left: 0.8rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            pointer-events: none;
            font-size: 0.9rem;
        }

        .filter-tabs {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .filter-tab {
            height: 38px;
            padding: 0 1.1rem;
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-secondary);
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }

        .filter-tab:hover {
            background: rgba(255, 255, 255, 0.04);
            color: #ffffff;
        }

        .filter-tab.active {
            background: rgba(59, 130, 246, 0.12);
            border-color: rgba(59, 130, 246, 0.3);
            color: #60a5fa;
        }

        /* ── 甘特图模块 (Gantt Chart) ── */
        .gantt-section {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.8rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(12px);
            overflow: hidden;
        }

        .gantt-wrapper {
            overflow-x: auto;
            margin-top: 1.2rem;
            position: relative;
        }

        .gantt-table {
            min-width: 800px;
            width: 100%;
            display: flex;
            flex-direction: column;
            border-collapse: collapse;
        }

        .gantt-header-row {
            display: flex;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 0.8rem;
            margin-bottom: 0.8rem;
        }

        .gantt-header-task {
            width: 220px;
            flex-shrink: 0;
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 700;
            padding-left: 0.5rem;
        }

        .gantt-header-timeline {
            flex-grow: 1;
            display: flex;
            justify-content: space-between;
            position: relative;
        }

        .gantt-timeline-day {
            flex: 1;
            text-align: center;
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            border-left: 1px dashed rgba(255, 255, 255, 0.03);
            position: relative;
        }

        .gantt-timeline-day::after {
            content: '';
            position: absolute;
            top: 2rem;
            left: 0;
            bottom: -500px; /* 贯穿竖线 */
            width: 1px;
            border-left: 1px dashed rgba(255, 255, 255, 0.03);
            pointer-events: none;
            z-index: 1;
        }

        .gantt-rows {
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
            position: relative;
        }

        .gantt-row {
            display: flex;
            align-items: center;
            padding: 0.4rem 0;
            transition: all 0.2s ease;
        }

        .gantt-row.hidden {
            display: none;
        }

        .gantt-task-meta {
            width: 220px;
            flex-shrink: 0;
            display: flex;
            flex-direction: column;
            padding-right: 1rem;
        }

        .gantt-task-id-title {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.82rem;
            font-weight: 700;
            color: #ffffff;
        }

        .gantt-task-id {
            font-family: monospace;
            background: rgba(255, 255, 255, 0.05);
            padding: 1px 4px;
            border-radius: 4px;
            font-size: 0.75rem;
            color: var(--accent-blue);
        }

        .gantt-task-dates {
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-top: 2px;
        }

        .gantt-bar-track {
            flex-grow: 1;
            height: 24px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 6px;
            position: relative;
            display: flex;
            align-items: center;
        }

        .gantt-bar-fill {
            height: 18px;
            border-radius: 4px;
            position: absolute;
            transition: all 0.3s ease;
            cursor: pointer;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            display: flex;
            align-items: center;
            padding-left: 8px;
            overflow: hidden;
        }

        .gantt-bar-inner-progress {
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0.18);
            pointer-events: none;
            transition: width 0.3s ease;
        }

        .gantt-bar-text {
            font-size: 0.7rem;
            font-weight: 700;
            color: #ffffff;
            z-index: 2;
            white-space: nowrap;
            text-shadow: 0 1px 3px rgba(0,0,0,0.6);
        }

        /* 甘特条颜色 */
        .gantt-bar-fill.status-pending { background: linear-gradient(90deg, #f59e0b, #d97706); }
        .gantt-bar-fill.status-progress { background: linear-gradient(90deg, #3b82f6, #1d4ed8); }
        .gantt-bar-fill.status-completed { background: linear-gradient(90deg, #10b981, #047857); }
        .gantt-bar-fill.status-delayed { background: linear-gradient(90deg, #f97316, #c2410c); }
        .gantt-bar-fill.status-blocked { background: linear-gradient(90deg, #6b7280, #374151); }

        /* ── 任务卡片 Grid ── */
        .section-title {
            font-size: 1.2rem;
            margin-bottom: 1.2rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .tasks-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.2rem;
        }

        .task-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            position: relative;
            backdrop-filter: blur(12px);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            animation: fadeInUp 0.4s ease both;
        }

        .task-card.hidden {
            display: none !important;
        }

        .task-card:hover {
            transform: translateY(-5px) scale(1.01);
            border-color: var(--border-glow);
            box-shadow: var(--shadow-glow);
        }

        .task-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.8rem;
        }

        .task-id {
            font-family: monospace;
            font-size: 0.85rem;
            font-weight: 700;
            color: var(--accent-blue);
            background: rgba(59, 130, 246, 0.1);
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            border: 1px solid rgba(59, 130, 246, 0.15);
        }

        .priority-badge {
            font-size: 0.72rem;
            font-weight: 700;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
        }

        .priority-p0 { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); }
        .priority-p1 { background: rgba(249, 115, 22, 0.15); color: #f97316; border: 1px solid rgba(249, 115, 22, 0.2); }
        .priority-p2 { background: rgba(59, 130, 246, 0.15); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.2); }

        .task-title {
            font-size: 1.1rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 0.6rem;
            line-height: 1.4;
        }

        .task-desc {
            font-size: 0.85rem;
            color: var(--text-secondary);
            line-height: 1.6;
            margin-bottom: 1.2rem;
            flex-grow: 1;
        }

        .task-meta {
            border-top: 1px solid rgba(255, 255, 255, 0.04);
            padding-top: 0.8rem;
            margin-bottom: 1rem;
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.6rem;
        }

        .meta-item {
            display: flex;
            align-items: center;
            gap: 0.4rem;
            font-size: 0.78rem;
            color: var(--text-secondary);
        }

        .meta-icon {
            font-size: 0.85rem;
            color: var(--text-muted);
        }

        .progress-section {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            margin-bottom: 1rem;
        }

        .progress-bar-container {
            flex-grow: 1;
            height: 6px;
            background: rgba(255, 255, 255, 0.04);
            border-radius: 3px;
            overflow: hidden;
        }

        .progress-bar-fill {
            height: 100%;
            background: var(--accent-blue);
            border-radius: 3px;
            transition: width 0.5s ease;
        }

        .progress-text {
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--accent-blue);
            min-width: 35px;
            text-align: right;
        }

        .task-status-badge {
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 0.25rem 0.7rem;
            border-radius: 8px;
            margin-bottom: 0.8rem;
            width: fit-content;
        }

        .task-status-badge.status-pending { background: rgba(245, 158, 11, 0.12); color: var(--accent-yellow); }
        .task-status-badge.status-progress { background: rgba(59, 130, 246, 0.12); color: var(--accent-blue); }
        .task-status-badge.status-completed { background: rgba(16, 185, 129, 0.12); color: var(--accent-green); }
        .task-status-badge.status-delayed { background: rgba(249, 115, 22, 0.12); color: var(--accent-orange); }
        .task-status-badge.status-blocked { background: rgba(107, 114, 128, 0.12); color: var(--text-secondary); }

        .section-label {
            font-size: 0.72rem;
            color: var(--text-muted);
            margin-right: 0.3rem;
            font-weight: 600;
        }

        .deliverables-section, .deps-section {
            margin-top: 0.5rem;
            display: flex;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 0.3rem;
        }

        .tags-container {
            display: flex;
            flex-wrap: wrap;
            gap: 0.3rem;
        }

        .deliverable-tag {
            font-size: 0.68rem;
            background: rgba(59, 130, 246, 0.08);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.12);
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
        }

        .dep-tag {
            font-size: 0.68rem;
            background: rgba(236, 72, 153, 0.08);
            color: #f472b6;
            border: 1px solid rgba(236, 72, 153, 0.12);
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
        }

        .no-deps {
            font-size: 0.68rem;
            color: var(--text-muted);
        }

        .evidence-section {
            margin-top: 0.75rem;
            padding-top: 0.65rem;
            border-top: 1px solid var(--border-color);
        }

        .evidence-item {
            margin-top: 0.3rem;
            color: var(--text-secondary);
            font-size: 0.72rem;
            line-height: 1.45;
        }

        .evidence-item strong { color: #93c5fd; }

        /* ── Footer ── */
        .footer {
            text-align: center;
            padding: 2.5rem;
            color: var(--text-muted);
            font-size: 0.75rem;
            border-top: 1px solid var(--border-color);
            margin-top: 3rem;
        }

        /* ── 动画定义 ── */
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(15px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        /* ── 响应式适配 ── */
        @media (max-width: 1200px) {
            .tasks-grid { grid-template-columns: repeat(2, 1fr); }
        }

        @media (max-width: 768px) {
            .page-container { padding: 1rem; }
            .stats-grid { grid-template-columns: repeat(3, 1fr); }
            .tasks-grid { grid-template-columns: 1fr; }
            .filter-section { flex-direction: column; align-items: stretch; }
            .header h1 { font-size: 1.8rem; }
        }
    </style>
</head>
<body>

    <div class="page-container">

        <!-- ── Header ── -->
        <div class="header">
            <h1>📋 {project_name}</h1>
            <div class="subtitle">{objective}</div>
            <div class="header-meta">
                <span>🎯 目标: {scope_or_obj}</span>
                <span>⏰ 截止: {overall_deadline}</span>
                <span>📊 编译更新: {parsed_at}</span>
            </div>
            <div class="project-evidence-list">
                <span class="section-label">🔎 项目证据:</span>
                {project_evidence_html}
            </div>
        </div>

        <!-- ── Stats ── -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total}</div>
                <div class="stat-label">总任务数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{completed}</div>
                <div class="stat-label">已完成</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{in_progress}</div>
                <div class="stat-label">进行中</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{pending}</div>
                <div class="stat-label">待开始</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{delayed}</div>
                <div class="stat-label">已延期</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{overall_progress}%</div>
                <div class="stat-label">总体进度</div>
            </div>
        </div>

        <!-- ── Overall Progress Bar ── -->
        <div class="overall-progress">
            <h2>📈 项目总体进度</h2>
            <div class="overall-bar">
                <div class="overall-bar-fill" style="width: {overall_progress}%"></div>
            </div>
            <div class="overall-text">{overall_progress}% 已完成</div>
        </div>

        <!-- ── 检索与状态过滤器 ── -->
        <div class="filter-section">
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" id="searchInput" class="search-input" placeholder="输入任务名称、描述、负责人进行实时搜索...">
            </div>
            <div class="filter-tabs">
                <button class="filter-tab active" data-status="all">全部 ({total})</button>
                <button class="filter-tab" data-status="pending">待开始 ({pending})</button>
                <button class="filter-tab" data-status="progress">进行中 ({in_progress})</button>
                <button class="filter-tab" data-status="completed">已完成 ({completed})</button>
                <button class="filter-tab" data-status="delayed">已延期 ({delayed})</button>
                <button class="filter-tab" data-status="blocked">被阻塞 ({blocked})</button>
            </div>
        </div>

        <!-- ── 甘特图区域 (Gantt Chart) ── -->
        <div class="gantt-section">
            <div class="section-title">📊 进度甘特图 (基于任务依赖链推导)</div>
            <div class="gantt-wrapper">
                <div class="gantt-table">
                    <div class="gantt-header-row">
                        <div class="gantt-header-task">任务名称</div>
                        <div class="gantt-header-timeline" id="ganttTimelineHeader">
                            <!-- 动态生成时间轴天数 -->
                        </div>
                    </div>
                    <div class="gantt-rows" id="ganttRowsContainer">
                        <!-- 动态生成甘特条 -->
                    </div>
                </div>
            </div>
        </div>

        <!-- ── Task Cards ── -->
        <div class="section-title">🗂️ 任务明细卡片</div>
        <div class="tasks-grid" id="tasksGrid">
            <!-- 任务卡片由前端动态加载/渲染 -->
        </div>

        <!-- ── Footer ── -->
        <div class="footer">
            Boss Task Agent &copy; 2026 · 由 AI 智能工作流驱动 · 最后编译时间: {parsed_at}
        </div>

    </div>

    <!-- ── 前端逻辑脚本 (数据驱动) ── -->
    <script>
        // 静态导出的 JSON 数据
        const rawTasks = {tasks_json_data};
        const rawSegments = {segments_json_data};

        // 映射任务状态至 CSS 样式
        const statusClassMap = {
            "待开始": "status-pending",
            "进行中": "status-progress",
            "已完成": "status-completed",
            "已延期": "status-delayed",
            "被阻塞": "status-blocked"
        };

        const priorityClassMap = {
            "P0-紧急": "priority-p0",
            "P1-重要": "priority-p1",
            "P2-一般": "priority-p2"
        };

        const escapeHtml = (value) => String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#039;");

        const formatEvidenceTime = (segment) => {
            if (!segment || segment.start_seconds == null || segment.end_seconds == null) return "";
            const format = (value) => {
                const totalMs = Math.max(0, Math.round(Number(value) * 1000));
                const minutes = Math.floor(totalMs / 60000);
                const seconds = Math.floor((totalMs % 60000) / 1000);
                const millis = totalMs % 1000;
                return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
            };
            return `${format(segment.start_seconds)}-${format(segment.end_seconds)}`;
        };

        // 📌 1. 动态生成任务详情卡片 HTML
        function renderTaskCards(filteredTasks) {
            const grid = document.getElementById("tasksGrid");
            grid.innerHTML = "";

            if (filteredTasks.length === 0) {
                grid.innerHTML = `<div style="grid-column: span 3; text-align: center; color: var(--text-muted); padding: 3rem;">未找到匹配的任务</div>`;
                return;
            }

            filteredTasks.forEach((t, index) => {
                const statusClass = statusClassMap[t.status] || "status-pending";
                const priorityClass = priorityClassMap[t.priority] || "priority-p2";

                const deliverablesHtml = t.deliverables && t.deliverables.length > 0 
                    ? t.deliverables.map(d => `<span class="deliverable-tag" title="${d.description || ''}">${d.name}</span>`).join("")
                    : `<span class="no-deps">无交付物</span>`;

                const depsHtml = t.dependencies && t.dependencies.length > 0
                    ? t.dependencies.map(d => `<span class="dep-tag">${d}</span>`).join("")
                    : `<span class="no-deps">无依赖</span>`;

                const evidenceHtml = t.evidence && t.evidence.length > 0
                    ? t.evidence.map(item => {
                        const segment = rawSegments.find(s => s.id === item.source_segment_id);
                        const time = formatEvidenceTime(segment);
                        const source = segment ? `${segment.speaker_role}${time ? ` · ${time}` : ""} · ${segment.source_file}` : "来源未知";
                        return `<div class="evidence-item"><strong>${escapeHtml(item.field)}</strong> · ${escapeHtml(source)} · “${escapeHtml(item.source_quote)}” · ${(Number(item.confidence) * 100).toFixed(0)}%</div>`;
                    }).join("")
                    : `<div class="evidence-item">暂无字段证据（历史项目）</div>`;

                const delayStyle = `animation-delay: ${index * 0.05}s`;

                const cardHtml = `
                    <div class="task-card ${statusClass}" style="${delayStyle}">
                        <div>
                            <div class="task-header">
                                <span class="task-id">${t.id}</span>
                                <span class="priority-badge ${priorityClass}">${t.priority}</span>
                            </div>
                            <h3 class="task-title">${t.title}</h3>
                            <p class="task-desc">${t.description || '无任务描述'}</p>
                        </div>
                        <div>
                            <div class="task-meta">
                                <div class="meta-item">
                                    <span class="meta-icon">👤</span>
                                    <span title="负责人">${t.assignee || '未分配'}</span>
                                </div>
                                <div class="meta-item">
                                    <span class="meta-icon">📅</span>
                                    <span title="截止日期">${t.deadline || '未设定'}</span>
                                </div>
                                <div class="meta-item">
                                    <span class="meta-icon">📂</span>
                                    <span title="任务分类">${t.category}</span>
                                </div>
                            </div>
                            <div class="progress-section">
                                <div class="progress-bar-container">
                                    <div class="progress-bar-fill" style="width: ${t.progress}%; background: var(--accent-${statusClass === 'status-completed' ? 'green' : (statusClass === 'status-progress' ? 'blue' : (statusClass === 'status-delayed' ? 'orange' : 'yellow'))})"></div>
                                </div>
                                <span class="progress-text">${t.progress}%</span>
                            </div>
                            <div class="task-status-badge ${statusClass}">${t.status}</div>
                            <div class="deliverables-section">
                                <span class="section-label">📦 交付物:</span>
                                <div class="tags-container">${deliverablesHtml}</div>
                            </div>
                            <div class="deps-section">
                                <span class="section-label">🔗 前置依赖:</span>
                                <div class="tags-container">${depsHtml}</div>
                            </div>
                            <div class="evidence-section">
                                <span class="section-label">🔎 证据链:</span>
                                ${evidenceHtml}
                            </div>
                        </div>
                    </div>
                `;
                grid.insertAdjacentHTML("beforeend", cardHtml);
            });
        }

        // 📌 2. 基于任务依赖推导甘特图的开始和截止时间，并进行动态绘制
        function renderGanttChart(filteredTasks) {
            const timelineHeader = document.getElementById("ganttTimelineHeader");
            const rowsContainer = document.getElementById("ganttRowsContainer");
            
            timelineHeader.innerHTML = "";
            rowsContainer.innerHTML = "";

            if (rawTasks.length === 0) return;

            // 格式化时间并过滤无效日期
            const parseDate = (dStr) => {
                if (!dStr) return null;
                const d = new Date(dStr);
                return isNaN(d.getTime()) ? null : d;
            };

            // 提取整个项目的全局起止范围
            const today = new Date();
            today.setHours(0,0,0,0);
            
            const deadlines = rawTasks.map(t => parseDate(t.deadline)).filter(d => d !== null);
            
            // 项目起点取 (今天) 和 (最早截止日期) 之间的较小值
            let projectStart = new Date(Math.min(today, ...deadlines));
            // 项目终点取 (最晚截止日期) 和 (今天) 之间的较大值，最少往后延1天
            let projectEnd = new Date(Math.max(today, ...deadlines));
            
            // 确保至少有 3 天的显示视宽
            if (projectEnd.getTime() - projectStart.getTime() < 3 * 24 * 60 * 60 * 1000) {
                projectEnd.setDate(projectEnd.getDate() + 2);
            }

            const durationMs = projectEnd.getTime() - projectStart.getTime();
            const totalDays = Math.ceil(durationMs / (24 * 60 * 60 * 1000)) + 1;

            // 绘制时间轴头部刻度
            for (let i = 0; i < totalDays; i++) {
                const tickDate = new Date(projectStart);
                tickDate.setDate(projectStart.getDate() + i);
                const month = tickDate.getMonth() + 1;
                const day = tickDate.getDate();
                const isToday = tickDate.getTime() === today.getTime() ? ' <span style="color:var(--accent-pink)">(今)</span>' : '';
                
                timelineHeader.insertAdjacentHTML("beforeend", `
                    <div class="gantt-timeline-day">
                        ${month}/${day}${isToday}
                    </div>
                `);
            }

            // 📌 核心推导每个任务的逻辑开始时间 (Start Date)
            // 规则：
            // A. 如果无前置依赖：开始时间 = 项目开始时间
            // B. 如果有前置依赖：开始时间 = 所有前置依赖任务中最晚截止时间 (Max Deadline of Dependencies)
            // C. 边界处理：若推导出的开始时间 >= 任务截止时间，强制前移 1 天以保证条形图能显示宽度
            const calculatedTasks = rawTasks.map(t => {
                let startDate = new Date(projectStart);
                const deadlineDate = parseDate(t.deadline) || new Date(projectEnd);

                if (t.dependencies && t.dependencies.length > 0) {
                    let maxDepDeadline = new Date(projectStart);
                    t.dependencies.forEach(depId => {
                        const depTask = rawTasks.find(dt => dt.id.toUpperCase() === depId.toUpperCase());
                        if (depTask) {
                            const depDl = parseDate(depTask.deadline);
                            if (depDl && depDl > maxDepDeadline) {
                                maxDepDeadline = new Date(depDl);
                            }
                        }
                    });
                    startDate = maxDepDeadline;
                }

                if (startDate >= deadlineDate) {
                    startDate = new Date(deadlineDate);
                    startDate.setDate(startDate.getDate() - 1);
                }

                return {
                    ...t,
                    parsedStart: startDate,
                    parsedEnd: deadlineDate
                };
            });

            // 绘制任务甘特条
            calculatedTasks.forEach(t => {
                // 检查该任务是否在当前的过滤条件中 (未被搜索或 Tab 过滤隐藏)
                const isVisible = filteredTasks.some(ft => ft.id === t.id);
                const statusClass = statusClassMap[t.status] || "status-pending";

                // 计算横条所占宽度和左侧偏移的百分比
                const leftOffsetOffsetMs = t.parsedStart.getTime() - projectStart.getTime();
                const taskDurationMs = t.parsedEnd.getTime() - t.parsedStart.getTime();
                
                // 加一天的天数毫秒修正，使条形图能占满截止当天
                const rangeSpanMs = durationMs + (24 * 60 * 60 * 1000); 

                const leftPct = (leftOffsetOffsetMs / rangeSpanMs) * 100;
                const widthPct = ((taskDurationMs + 24 * 60 * 60 * 1000) / rangeSpanMs) * 100;

                const startStr = `${t.parsedStart.getMonth() + 1}/${t.parsedStart.getDate()}`;
                const endStr = `${t.parsedEnd.getMonth() + 1}/${t.parsedEnd.getDate()}`;

                const rowHtml = `
                    <div class="gantt-row ${isVisible ? '' : 'hidden'}" data-id="${t.id}">
                        <div class="gantt-task-meta">
                            <div class="gantt-task-id-title">
                                <span class="gantt-task-id">${t.id}</span>
                                <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${t.title}">${t.title}</span>
                            </div>
                            <div class="gantt-task-dates">工期: ${startStr} 至 ${endStr} (${t.status})</div>
                        </div>
                        <div class="gantt-bar-track">
                            <div class="gantt-bar-fill ${statusClass}" style="left: ${leftPct}%; width: ${widthPct}%" title="${t.title} (${t.status} - ${t.progress}%)">
                                <div class="gantt-bar-inner-progress" style="width: ${t.progress}%"></div>
                                <span class="gantt-bar-text">${t.progress}%</span>
                            </div>
                        </div>
                    </div>
                `;
                rowsContainer.insertAdjacentHTML("beforeend", rowHtml);
            });
        }

        // 📌 3. 联合搜索框和状态 Tabs 过滤逻辑
        let activeStatusFilter = "all";
        let activeSearchQuery = "";

        function filterAndRender() {
            const filtered = rawTasks.filter(t => {
                // A. 状态过滤
                let statusMatch = false;
                if (activeStatusFilter === "all") {
                    statusMatch = true;
                } else if (activeStatusFilter === "pending" && t.status === "待开始") {
                    statusMatch = true;
                } else if (activeStatusFilter === "progress" && t.status === "进行中") {
                    statusMatch = true;
                } else if (activeStatusFilter === "completed" && t.status === "已完成") {
                    statusMatch = true;
                } else if (activeStatusFilter === "delayed" && t.status === "已延期") {
                    statusMatch = true;
                } else if (activeStatusFilter === "blocked" && t.status === "被阻塞") {
                    statusMatch = true;
                }

                // B. 搜索匹配 (标题、描述、负责人)
                let searchMatch = false;
                const query = activeSearchQuery.toLowerCase().trim();
                if (!query) {
                    searchMatch = true;
                } else {
                    const title = (t.title || "").toLowerCase();
                    const desc = (t.description || "").toLowerCase();
                    const assignee = (t.assignee || "").toLowerCase();
                    const category = (t.category || "").toLowerCase();
                    const id = (t.id || "").toLowerCase();
                    searchMatch = title.includes(query) || desc.includes(query) || assignee.includes(query) || category.includes(query) || id.includes(query);
                }

                return statusMatch && searchMatch;
            });

            // 重新渲染卡片和甘特条展示
            renderTaskCards(filtered);
            renderGanttChart(filtered);
        }

        // 📌 4. 监听事件绑定
        document.addEventListener("DOMContentLoaded", () => {
            // 初始化渲染
            filterAndRender();

            // 监听搜索框输入
            const searchInput = document.getElementById("searchInput");
            searchInput.addEventListener("input", (e) => {
                activeSearchQuery = e.target.value;
                filterAndRender();
            });

            // 监听 Tab 状态切换
            const tabs = document.querySelectorAll(".filter-tab");
            tabs.forEach(tab => {
                tab.addEventListener("click", () => {
                    tabs.forEach(btn => btn.classList.remove("active"));
                    tab.classList.add("active");
                    activeStatusFilter = tab.getAttribute("data-status");
                    filterAndRender();
                });
            });
        });
    </script>

</body>
</html>"""

    # 替换变量占位符，安全无痛支持大面积的 { 和 }
    html_output = html_template.replace("{project_name}", project_name) \
                               .replace("{objective}", objective) \
                               .replace("{scope_or_obj}", scope_or_obj) \
                               .replace("{overall_deadline}", overall_deadline) \
                               .replace("{parsed_at}", parsed_at) \
                               .replace("{project_evidence_html}", project_evidence_html) \
                               .replace("{segments_json_data}", segments_json_data) \
                               .replace("{total}", str(total)) \
                               .replace("{completed}", str(completed)) \
                               .replace("{in_progress}", str(in_progress)) \
                               .replace("{pending}", str(pending)) \
                               .replace("{delayed}", str(delayed)) \
                               .replace("{blocked}", str(blocked)) \
                               .replace("{overall_progress}", str(overall_progress)) \
                               .replace("{tasks_json_data}", tasks_json_data)

    output_path = config.DASHBOARD_HTML
    output_path.write_text(html_output, encoding="utf-8")
    return output_path
