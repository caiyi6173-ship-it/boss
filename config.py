"""
配置管理 - 老板语音→结构化工作指令系统
管理 LLM API、文件路径等配置。
API Key 从 .env 文件读取，不会泄露到代码中。
"""

import os
from pathlib import Path


# ────────────────────────── .env 文件加载 ──────────────────────────

def _load_env(env_path: Path):
    """从 .env 文件加载环境变量（仅加载尚未设置的变量）"""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            # 不覆盖已有的环境变量
            if key and key not in os.environ:
                os.environ[key] = value


# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 自动加载 .env
_load_env(PROJECT_ROOT / ".env")


# ────────────────────────── 路径配置 ──────────────────────────

# 输入文件：默认相对路径 ./input/Workbook.xlsx，可通过 BOSS_WORKBOOK_PATH 覆盖
WORKBOOK_PATH = Path(os.environ.get(
    "BOSS_WORKBOOK_PATH",
    str(Path(__file__).parent / "input" / "Workbook.xlsx")
))

# 输出目录
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# SOP 模板目录
SOP_DIR = PROJECT_ROOT / "sop_templates"
SOP_DIR.mkdir(exist_ok=True)

# 结构化任务输出
TASKS_JSON = OUTPUT_DIR / "structured_tasks.json"

# 进度历史
PROGRESS_HISTORY_JSON = OUTPUT_DIR / "progress_history.json"

# Dashboard HTML
DASHBOARD_HTML = OUTPUT_DIR / "task_dashboard.html"

# 复盘报告
RETROSPECTIVE_MD = OUTPUT_DIR / "retrospective_report.md"

# 本地表格（替代飞书多维表格）
LOCAL_TABLE_XLSX = OUTPUT_DIR / "task_table.xlsx"


# ────────────────────────── LLM API 配置 ──────────────────────────
# API Key 从 .env 文件或环境变量读取，绝不硬编码在代码中

# 默认走阿里云百炼（DashScope）的 OpenAI 兼容端点，配合 qwen-plus 模型。
# 若要换 Moonshot Kimi：BASE_URL=https://api.moonshot.cn/v1, MODEL=moonshot-v1-8k。
# 若要换 OpenAI 官方：BASE_URL=https://api.openai.com/v1, MODEL=gpt-4o-mini。
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "qwen-plus")


# ────────────────────────── 系统 Prompt ──────────────────────────

TASK_PARSE_SYSTEM_PROMPT = """你是一个专业的项目管理助手。你的任务是将老板的语音转录内容解析为结构化的工作指令。

规则：
1. 仔细分析语音内容，提取所有任务项
2. 每个任务必须有明确的标题、描述、分类、优先级和交付物
3. 根据语音中的时间线索推断截止日期（以今天 {today} 为基准）
4. 识别任务之间的依赖关系
5. 分类包括：策划、执行、内容制作、审核、汇报、其他
6. 优先级根据紧迫程度和重要性判断：P0-紧急、P1-重要、P2-一般

请严格按照指定的 JSON Schema 输出。"""

SOP_GENERATE_SYSTEM_PROMPT = """你是一个流程优化专家。基于已完成的项目任务清单，生成一份可复用的 SOP（标准操作流程）模板。

规则：
1. 提炼通用步骤，去除项目特定细节
2. 每个步骤需要明确输入、输出、负责角色和质量标准
3. 加入风险提示和检查清单
4. 模板应可应用于同类型项目
5. 标注适用场景

请严格按照指定的 JSON Schema 输出。"""

RETROSPECTIVE_SYSTEM_PROMPT = """你是一个项目复盘专家。基于项目的任务执行数据和进度历史，生成一份结构化复盘报告。

规则：
1. 分析什么做得好、什么需要改进
2. 提出具体的后续行动项
3. 总结经验教训，便于未来参考
4. 分析时间线，找出瓶颈和效率提升点
5. 语言要具体、可操作，避免空洞的总结

请严格按照指定的 JSON Schema 输出，不要输出任何解释文字或 Markdown。"""
