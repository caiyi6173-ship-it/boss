"""
Dashboard Generator - 生成精美的 HTML 任务进度看板
纯静态 HTML，双击即可在浏览器中查看，无需服务器。
"""

import html
from pathlib import Path
from models import StructuredInstruction, TaskStatus
import config

# LLM 输出不可信，所有插入 HTML 的字符串必须转义，防止 XSS 或 dashboard 结构被破坏
esc = html.escape


def generate_dashboard(instruction: StructuredInstruction) -> Path:
    """生成静态 HTML 进度看板"""

    tasks = instruction.tasks
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
    pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
    delayed = sum(1 for t in tasks if t.status == TaskStatus.DELAYED)
    blocked = sum(1 for t in tasks if t.status == TaskStatus.BLOCKED)
    overall_progress = round(sum(t.progress for t in tasks) / total, 1) if total else 0

    # 构建任务卡片 HTML
    task_cards_html = ""
    for t in tasks:
        status_class = {
            TaskStatus.PENDING: "status-pending",
            TaskStatus.IN_PROGRESS: "status-progress",
            TaskStatus.COMPLETED: "status-completed",
            TaskStatus.DELAYED: "status-delayed",
            TaskStatus.BLOCKED: "status-blocked",
        }.get(t.status, "status-pending")

        priority_class = {
            "P0-紧急": "priority-p0",
            "P1-重要": "priority-p1",
            "P2-一般": "priority-p2",
        }.get(t.priority.value, "priority-p2")

        deliverables_html = "".join(
            f'<span class="deliverable-tag">{esc(d.name)}</span>' for d in t.deliverables
        )
        deps_html = "".join(
            f'<span class="dep-tag">{esc(d)}</span>' for d in t.dependencies
        ) if t.dependencies else '<span class="no-deps">无依赖</span>'

        task_cards_html += f"""
        <div class="task-card {status_class}">
            <div class="task-header">
                <span class="task-id">{esc(t.id)}</span>
                <span class="priority-badge {priority_class}">{t.priority.value}</span>
            </div>
            <h3 class="task-title">{esc(t.title)}</h3>
            <p class="task-desc">{esc(t.description)}</p>
            <div class="task-meta">
                <div class="meta-item">
                    <span class="meta-icon">👤</span>
                    <span>{esc(t.assignee)}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-icon">📅</span>
                    <span>{esc(t.deadline or '未设定')}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-icon">📂</span>
                    <span>{t.category.value}</span>
                </div>
            </div>
            <div class="progress-section">
                <div class="progress-bar-container">
                    <div class="progress-bar-fill" style="width: {t.progress}%"></div>
                </div>
                <span class="progress-text">{t.progress}%</span>
            </div>
            <div class="task-status-badge {status_class}">{t.status.value}</div>
            <div class="deliverables-section">
                <span class="section-label">📦 交付物:</span>
                <div class="tags-container">{deliverables_html}</div>
            </div>
            <div class="deps-section">
                <span class="section-label">🔗 依赖:</span>
                <div class="tags-container">{deps_html}</div>
            </div>
        </div>"""

    # 预转义所有会插入 HTML 的 LLM 输出字段
    project_name = esc(instruction.overview.project_name)
    objective = esc(instruction.overview.objective)
    scope_or_obj = esc(instruction.overview.scope or instruction.overview.objective)
    overall_deadline = esc(instruction.overview.overall_deadline or "未设定")
    parsed_at = esc(instruction.parsed_at)

    html_output = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📋 {project_name} - 任务看板</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

        :root {{
            --bg-primary: #0f0f23;
            --bg-secondary: #1a1a3e;
            --bg-card: rgba(255, 255, 255, 0.04);
            --bg-glass: rgba(255, 255, 255, 0.08);
            --text-primary: #e8e8f0;
            --text-secondary: #a0a0c0;
            --text-muted: #6b6b8d;
            --accent-blue: #667eea;
            --accent-purple: #764ba2;
            --accent-pink: #f093fb;
            --accent-green: #43e97b;
            --accent-orange: #f5576c;
            --accent-yellow: #f6d365;
            --border-color: rgba(255, 255, 255, 0.08);
            --shadow-glow: 0 0 40px rgba(102, 126, 234, 0.15);
        }}

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }}

        /* ── Animated Background ── */
        body::before {{
            content: '';
            position: fixed;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle at 20% 50%, rgba(102, 126, 234, 0.08) 0%, transparent 50%),
                        radial-gradient(circle at 80% 20%, rgba(118, 75, 162, 0.08) 0%, transparent 50%),
                        radial-gradient(circle at 50% 80%, rgba(240, 147, 251, 0.05) 0%, transparent 50%);
            animation: bgShift 20s ease-in-out infinite;
            z-index: -1;
        }}

        @keyframes bgShift {{
            0%, 100% {{ transform: translate(0, 0); }}
            33% {{ transform: translate(-5%, 3%); }}
            66% {{ transform: translate(3%, -5%); }}
        }}

        /* ── Header ── */
        .header {{
            padding: 2rem 3rem;
            background: linear-gradient(135deg, rgba(102, 126, 234, 0.15), rgba(118, 75, 162, 0.1));
            border-bottom: 1px solid var(--border-color);
            backdrop-filter: blur(20px);
        }}

        .header h1 {{
            font-size: 1.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-pink));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.3rem;
        }}

        .header .subtitle {{
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}

        .header-meta {{
            display: flex;
            gap: 2rem;
            margin-top: 0.8rem;
            flex-wrap: wrap;
        }}

        .header-meta span {{
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        /* ── Stats Grid ── */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1.2rem;
            padding: 2rem 3rem;
        }}

        .stat-card {{
            background: var(--bg-glass);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(10px);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}

        .stat-card:hover {{
            transform: translateY(-4px);
            border-color: var(--accent-blue);
            box-shadow: var(--shadow-glow);
        }}

        .stat-card::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            border-radius: 16px 16px 0 0;
        }}

        .stat-card:nth-child(1)::after {{ background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple)); }}
        .stat-card:nth-child(2)::after {{ background: linear-gradient(90deg, var(--accent-green), #38f9d7); }}
        .stat-card:nth-child(3)::after {{ background: linear-gradient(90deg, var(--accent-blue), #00f2fe); }}
        .stat-card:nth-child(4)::after {{ background: linear-gradient(90deg, var(--accent-yellow), #fda085); }}
        .stat-card:nth-child(5)::after {{ background: linear-gradient(90deg, var(--accent-orange), #c471ed); }}
        .stat-card:nth-child(6)::after {{ background: linear-gradient(90deg, var(--accent-pink), var(--accent-purple)); }}

        .stat-value {{
            font-size: 2.2rem;
            font-weight: 800;
            line-height: 1;
            margin-bottom: 0.3rem;
        }}

        .stat-card:nth-child(1) .stat-value {{ color: var(--accent-blue); }}
        .stat-card:nth-child(2) .stat-value {{ color: var(--accent-green); }}
        .stat-card:nth-child(3) .stat-value {{ color: #00f2fe; }}
        .stat-card:nth-child(4) .stat-value {{ color: var(--accent-yellow); }}
        .stat-card:nth-child(5) .stat-value {{ color: var(--accent-orange); }}
        .stat-card:nth-child(6) .stat-value {{ color: var(--accent-pink); }}

        .stat-label {{
            font-size: 0.8rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        /* ── Overall Progress ── */
        .overall-progress {{
            margin: 0 3rem 2rem;
            background: var(--bg-glass);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem 2rem;
            backdrop-filter: blur(10px);
        }}

        .overall-progress h2 {{
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text-secondary);
        }}

        .overall-bar {{
            width: 100%;
            height: 20px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            overflow: hidden;
            position: relative;
        }}

        .overall-bar-fill {{
            height: 100%;
            border-radius: 10px;
            background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple), var(--accent-pink));
            background-size: 200% 100%;
            animation: gradientSlide 3s ease infinite;
            transition: width 1s ease;
            position: relative;
        }}

        .overall-bar-fill::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            animation: shimmer 2s infinite;
        }}

        @keyframes gradientSlide {{
            0%, 100% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
        }}

        @keyframes shimmer {{
            0% {{ transform: translateX(-100%); }}
            100% {{ transform: translateX(100%); }}
        }}

        .overall-text {{
            text-align: right;
            margin-top: 0.5rem;
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--accent-pink);
        }}

        /* ── Section Title ── */
        .section-title {{
            padding: 0 3rem;
            margin-bottom: 1.5rem;
            font-size: 1.3rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        /* ── Task Cards Grid ── */
        .tasks-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 1.5rem;
            padding: 0 3rem 3rem;
        }}

        .task-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(10px);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}

        .task-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
        }}

        .task-card.status-pending::before {{ background: var(--accent-yellow); }}
        .task-card.status-progress::before {{ background: linear-gradient(90deg, var(--accent-blue), #00f2fe); }}
        .task-card.status-completed::before {{ background: var(--accent-green); }}
        .task-card.status-delayed::before {{ background: var(--accent-orange); }}
        .task-card.status-blocked::before {{ background: #888; }}

        .task-card:hover {{
            transform: translateY(-4px);
            box-shadow: var(--shadow-glow);
            border-color: rgba(102, 126, 234, 0.3);
        }}

        .task-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.8rem;
        }}

        .task-id {{
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--accent-blue);
            background: rgba(102, 126, 234, 0.15);
            padding: 0.2rem 0.6rem;
            border-radius: 6px;
        }}

        .priority-badge {{
            font-size: 0.7rem;
            font-weight: 700;
            padding: 0.2rem 0.6rem;
            border-radius: 6px;
            text-transform: uppercase;
        }}

        .priority-p0 {{ background: rgba(245, 87, 108, 0.2); color: var(--accent-orange); }}
        .priority-p1 {{ background: rgba(246, 211, 101, 0.2); color: var(--accent-yellow); }}
        .priority-p2 {{ background: rgba(160, 160, 192, 0.15); color: var(--text-muted); }}

        .task-title {{
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            color: var(--text-primary);
        }}

        .task-desc {{
            font-size: 0.82rem;
            color: var(--text-secondary);
            line-height: 1.5;
            margin-bottom: 1rem;
        }}

        .task-meta {{
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }}

        .meta-item {{
            display: flex;
            align-items: center;
            gap: 0.3rem;
            font-size: 0.78rem;
            color: var(--text-muted);
        }}

        .meta-icon {{ font-size: 0.9rem; }}

        .progress-section {{
            display: flex;
            align-items: center;
            gap: 0.8rem;
            margin-bottom: 1rem;
        }}

        .progress-bar-container {{
            flex: 1;
            height: 8px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
            overflow: hidden;
        }}

        .progress-bar-fill {{
            height: 100%;
            border-radius: 4px;
            background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple));
            transition: width 0.8s ease;
        }}

        .progress-text {{
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--accent-blue);
            min-width: 35px;
            text-align: right;
        }}

        .task-status-badge {{
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 600;
            padding: 0.25rem 0.7rem;
            border-radius: 8px;
            margin-bottom: 0.8rem;
        }}

        .task-status-badge.status-pending {{ background: rgba(246, 211, 101, 0.15); color: var(--accent-yellow); }}
        .task-status-badge.status-progress {{ background: rgba(102, 126, 234, 0.15); color: var(--accent-blue); }}
        .task-status-badge.status-completed {{ background: rgba(67, 233, 123, 0.15); color: var(--accent-green); }}
        .task-status-badge.status-delayed {{ background: rgba(245, 87, 108, 0.15); color: var(--accent-orange); }}
        .task-status-badge.status-blocked {{ background: rgba(136, 136, 136, 0.15); color: #aaa; }}

        .section-label {{
            font-size: 0.72rem;
            color: var(--text-muted);
            margin-right: 0.3rem;
        }}

        .deliverables-section, .deps-section {{
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.3rem;
        }}

        .tags-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.3rem;
        }}

        .deliverable-tag {{
            font-size: 0.68rem;
            background: rgba(102, 126, 234, 0.12);
            color: var(--accent-blue);
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
        }}

        .dep-tag {{
            font-size: 0.68rem;
            background: rgba(240, 147, 251, 0.12);
            color: var(--accent-pink);
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
        }}

        .no-deps {{
            font-size: 0.68rem;
            color: var(--text-muted);
        }}

        /* ── Footer ── */
        .footer {{
            text-align: center;
            padding: 2rem;
            color: var(--text-muted);
            font-size: 0.75rem;
            border-top: 1px solid var(--border-color);
        }}

        /* ── Responsive ── */
        @media (max-width: 768px) {{
            .header, .stats-grid, .tasks-grid, .overall-progress, .section-title {{
                padding-left: 1.2rem;
                padding-right: 1.2rem;
            }}
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .tasks-grid {{ grid-template-columns: 1fr; }}
        }}

        /* ── Fade-in animation ── */
        .task-card {{
            animation: fadeInUp 0.5s ease both;
        }}

        .task-card:nth-child(1) {{ animation-delay: 0.05s; }}
        .task-card:nth-child(2) {{ animation-delay: 0.1s; }}
        .task-card:nth-child(3) {{ animation-delay: 0.15s; }}
        .task-card:nth-child(4) {{ animation-delay: 0.2s; }}
        .task-card:nth-child(5) {{ animation-delay: 0.25s; }}
        .task-card:nth-child(6) {{ animation-delay: 0.3s; }}
        .task-card:nth-child(7) {{ animation-delay: 0.35s; }}
        .task-card:nth-child(8) {{ animation-delay: 0.4s; }}

        @keyframes fadeInUp {{
            from {{
                opacity: 0;
                transform: translateY(20px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}

        .stat-card {{
            animation: fadeInUp 0.5s ease both;
        }}
        .stat-card:nth-child(1) {{ animation-delay: 0.05s; }}
        .stat-card:nth-child(2) {{ animation-delay: 0.1s; }}
        .stat-card:nth-child(3) {{ animation-delay: 0.15s; }}
        .stat-card:nth-child(4) {{ animation-delay: 0.2s; }}
        .stat-card:nth-child(5) {{ animation-delay: 0.25s; }}
        .stat-card:nth-child(6) {{ animation-delay: 0.3s; }}
    </style>
</head>
<body>

    <!-- ── Header ── -->
    <div class="header">
        <h1>📋 {project_name}</h1>
        <div class="subtitle">{objective}</div>
        <div class="header-meta">
            <span>🎯 目标: {scope_or_obj}</span>
            <span>⏰ 截止: {overall_deadline}</span>
            <span>📊 解析时间: {parsed_at}</span>
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
            <div class="stat-value">{round(overall_progress)}%</div>
            <div class="stat-label">总体进度</div>
        </div>
    </div>

    <!-- ── Overall Progress Bar ── -->
    <div class="overall-progress">
        <h2>📈 总体进度</h2>
        <div class="overall-bar">
            <div class="overall-bar-fill" style="width: {overall_progress}%"></div>
        </div>
        <div class="overall-text">{overall_progress}% 完成</div>
    </div>

    <!-- ── Task Cards ── -->
    <div class="section-title">🗂️ 任务详情</div>
    <div class="tasks-grid">
        {task_cards_html}
    </div>

    <!-- ── Footer ── -->
    <div class="footer">
        Boss Task Agent &copy; 2026 · 由 AI 智能体自动生成 · 最后更新: {parsed_at}
    </div>

</body>
</html>"""

    output_path = config.DASHBOARD_HTML
    output_path.write_text(html_output, encoding="utf-8")
    return output_path
