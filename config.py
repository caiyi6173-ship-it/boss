"""
配置管理 - 老板语音→结构化工作指令系统
管理 LLM API、文件路径等配置。
API Key 从 .env 文件读取，不会泄露到代码中。
"""

import os
import sys
from pathlib import Path


# ────────────────────────── 运行根目录 ──────────────────────────
# 源码模式：项目目录即根目录
# PyInstaller 打包模式：sys.frozen 为 True，此时 __file__ 指向临时解压目录，
# 用户可见的目录是 exe 所在目录（sys.executable 的父目录）。
# 所有用户数据（.env / input / output / sop_templates）必须落在 exe 同级，
# 否则用户看不到生成物，也无法编辑配置。

if getattr(sys, "frozen", False):
    # 打包后运行：以 exe 所在目录为根
    PROJECT_ROOT = Path(sys.executable).parent
else:
    # 源码运行：以本文件所在目录为根
    PROJECT_ROOT = Path(__file__).parent


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


def reload_env():
    """重新从 PROJECT_ROOT/.env 加载并刷新 API 与音频转写变量。
    GUI 保存 .env 后调用，避免用户重启 exe。"""
    global OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
    global AUDIO_TRANSCRIPTION_MODEL, AUDIO_TRANSCRIPTION_DEVICE
    global AUDIO_TRANSCRIPTION_COMPUTE_TYPE, AUDIO_TRANSCRIPTION_LANGUAGE
    global DEFAULT_SPEAKER_ROLE
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    # 允许覆盖：先清掉旧值，再加载
    for k in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "BOSS_WHISPER_MODEL",
        "BOSS_WHISPER_DEVICE",
        "BOSS_WHISPER_COMPUTE_TYPE",
        "BOSS_WHISPER_LANGUAGE",
        "BOSS_SPEAKER_ROLE",
    ):
        os.environ.pop(k, None)
    _load_env(env_path)
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "qwen-plus")
    AUDIO_TRANSCRIPTION_MODEL = os.environ.get("BOSS_WHISPER_MODEL", "small")
    AUDIO_TRANSCRIPTION_DEVICE = os.environ.get("BOSS_WHISPER_DEVICE", "auto")
    AUDIO_TRANSCRIPTION_COMPUTE_TYPE = os.environ.get("BOSS_WHISPER_COMPUTE_TYPE", "default")
    AUDIO_TRANSCRIPTION_LANGUAGE = os.environ.get("BOSS_WHISPER_LANGUAGE", "zh")
    DEFAULT_SPEAKER_ROLE = os.environ.get("BOSS_SPEAKER_ROLE", "老板")


# 自动加载 .env
_load_env(PROJECT_ROOT / ".env")


# ────────────────────────── 路径配置 ──────────────────────────

# 输入文件：默认放在 exe/源码同级的 input/Workbook.xlsx。
# 新配置使用 BOSS_INPUT_PATH；仍兼容旧的 BOSS_WORKBOOK_PATH。
# 注意：这里必须用 PROJECT_ROOT，不能用 Path(__file__).parent——
# 打包后 __file__ 指向解压临时目录，用户在那里看不到文件。
INPUT_DIR = PROJECT_ROOT / "input"
INPUT_DIR.mkdir(exist_ok=True)

INPUT_PATH = Path(
    os.environ.get("BOSS_INPUT_PATH")
    or os.environ.get("BOSS_WORKBOOK_PATH")
    or str(INPUT_DIR / "Workbook.xlsx")
)

# 向后兼容旧代码与已有配置。
WORKBOOK_PATH = INPUT_PATH

# 输出目录
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# SOP 模板目录
SOP_DIR = PROJECT_ROOT / "sop_templates"
SOP_DIR.mkdir(exist_ok=True)

# SQLite 主数据库
DATABASE_PATH = OUTPUT_DIR / "boss_tasks.db"

# 旧版 JSON 路径：仅用于首次启动时迁移，迁移后保留为备份。
TASKS_JSON = OUTPUT_DIR / "structured_tasks.json"
PROGRESS_HISTORY_JSON = OUTPUT_DIR / "progress_history.json"

# Dashboard HTML
DASHBOARD_HTML = OUTPUT_DIR / "task_dashboard.html"

# 复盘报告
RETROSPECTIVE_MD = OUTPUT_DIR / "retrospective_report.md"

# 本地表格（替代飞书多维表格）
LOCAL_TABLE_XLSX = OUTPUT_DIR / "task_table.xlsx"

# 业务同义词词典（可编辑 JSON，打包后放在 exe 同级）
DOMAIN_GLOSSARY_JSON = PROJECT_ROOT / "domain_glossary.json"

# 通用中文同义词库（chi-syn），用于业务词 soft 扩展；不直接整库塞进 prompt
RESOURCES_DIR = PROJECT_ROOT / "resources"
CHINESE_SYNONYM_TXT = RESOURCES_DIR / "chinese_synonym.txt"


# ────────────────────────── LLM API 配置 ──────────────────────────
# API Key 从 .env 文件或环境变量读取，绝不硬编码在代码中

# 默认走阿里云百炼（DashScope）的 OpenAI 兼容端点，配合 qwen-plus 模型。
# 若要换 Moonshot Kimi：BASE_URL=https://api.moonshot.cn/v1, MODEL=moonshot-v1-8k。
# 若要换 OpenAI 官方：BASE_URL=https://api.openai.com/v1, MODEL=gpt-4o-mini。
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "qwen-plus")

# 本地音频转写配置。faster-whisper 仅在选择 MP3/WAV/M4A 时按需导入。
AUDIO_TRANSCRIPTION_MODEL = os.environ.get("BOSS_WHISPER_MODEL", "small")
AUDIO_TRANSCRIPTION_DEVICE = os.environ.get("BOSS_WHISPER_DEVICE", "auto")
AUDIO_TRANSCRIPTION_COMPUTE_TYPE = os.environ.get("BOSS_WHISPER_COMPUTE_TYPE", "default")
AUDIO_TRANSCRIPTION_LANGUAGE = os.environ.get("BOSS_WHISPER_LANGUAGE", "zh")
DEFAULT_SPEAKER_ROLE = os.environ.get("BOSS_SPEAKER_ROLE", "老板")


# ────────────────────────── 系统 Prompt ──────────────────────────

TASK_PARSE_SYSTEM_PROMPT = """你是一个专业的项目管理助手。你的任务是将老板的语音转录内容解析为结构化的工作指令。

你的目标：把口语化、跳跃、不完整的老板指令，拆成可执行、可交付、可跟踪的任务清单。
今天日期是 {today}。所有相对时间都以此为基准。

## 核心规则
1. 先理解整段话的项目背景与目标，再拆任务；不要把寒暄、重复句当成任务。
2. 一句口语可能对应多个任务；按“可独立交付的工作单元”拆分，不要把整段只压成 1 个大任务。
3. 每个任务必须有：标题、描述、分类、优先级、负责人、截止日期（可推断）、至少一个交付物。
4. 分类只能用：策划、执行、内容制作、审核、汇报、其他。
5. 优先级：
   - P0-紧急：今天/明天、先做、最重要、不能耽误、卡点
   - P1-重要：主线任务、明确要求完成
   - P2-一般：可往后放、顺带、有空再做
6. 识别依赖：如“拍完再发”“方案确认后才执行”，用 dependencies 填前置任务 ID（T001/T002...）。
7. 任务 ID 从 T001 连续编号，顺序尽量符合执行先后。
8. 交付物要具体：文档/视频/图文/表格/确认结果等，不要写空泛的“完成工作”。
9. 负责人：
   - 明确点名则填真实称呼（小李/运营/设计）
   - 只说“你来/帮我”可填“执行团队”或“待分配”
10. 只输出合法 JSON，严格遵循给定结构，不要解释。

## 口语时间理解（以 {today} 为基准）
- 今天/今日 → 当天
- 明天/明日 → +1 天
- 后天 → +2 天
- 这两天/这两日/尽快这两天 → 默认截止到 +2 天
- 这周/本周内 → 本周日
- 下周/下周前 → 下周五（若已过则取下周日）
- 月底/这个月底 → 本月最后一天
- 尽快/马上/抓紧 → 默认 +1 天，优先级至少 P1，必要时 P0
- 先/先做/优先 → 对应任务提高优先级，并尽量排在前面
- 随后/然后/之后 → 作为依赖后置任务
- 没说时间但有项目总截止 → 任务截止不超过 overall_deadline
- 完全没时间线索 → deadline 可为空，但 overall_deadline 有则尽量填项目截止

## 口语责任人与动作
- “让小李跟/小王负责/运营那边做” → assignee 填对应角色
- “帮我策划一下/你来接收一下” → 这是派活，要拆成可执行任务，不是忽略
- “拍视频并上传小红书/抖音” → 拍摄、平台内容制作/发布可拆开（有先后依赖）
- “整理文档/总结成文档” → 单独成汇报/文档任务
- “确认/审核/过一下” → 审核类任务

## 拆任务边界示例
输入大意：明天商场活动，宣传音乐节，拍视频，上小红书和抖音，整理文档，这两天结束，还要总结。
合理拆分：
1) 活动/宣传策划方案
2) 宣传视频拍摄
3) 小红书内容制作与发布
4) 抖音内容制作与发布
5) 项目总结文档
并体现 2 依赖 1，3/4 依赖 2，5 依赖 3/4。

## 输出质量要求
- title 简短可扫读（8-20 字为佳）
- description 写清“做什么、做成什么样、为何做”
- notes 可记录语音中的原始约束（预算、场地、客户确认等）
- key_stakeholders 提取老板、执行人、协作方
- 不要编造语音中完全不存在的业务事实；可合理补全交付物名称与执行顺序"""

CHAT_INTENT_SYSTEM_PROMPT = """你是项目管理场景下的中文口语意图理解助手。
用户会用很口语的话更新已有任务；你必须结合“当前任务清单”判断他想改哪个任务、改成什么。
今天日期是 {today}。

## 你的输出只能是 JSON，字段如下
- intent: update_task | clarify | unknown
- task_id: 唯一确定时的任务编号（如 T003），否则 null
- task_query: 用户话里指向任务的关键词
- status: 待开始 | 进行中 | 已完成 | 已延期 | 被阻塞 | null
- progress: 0-100 的整数，或 null
- assignee: 新负责人或 null
- deadline: YYYY-MM-DD 或 null
- note: 保留用户原意的简短备注
- confidence: 0~1
- need_clarification: true/false
- clarify_question: 需要反问时给出简洁中文问题
- candidate_task_ids: 候选任务编号数组

## 判定规则
1. 先匹配任务：优先看任务编号（T001），再看标题/描述/交付物/分类中的关键词与同义说法。
2. 同义示例：
   - 小红书 ≈ 红薯/种草/笔记
   - 抖音 ≈ 短视频/发抖音
   - 方案 ≈ 策划案/执行案/PPT
   - 拍摄 ≈ 拍视频/出镜/拍素材
   - 总结 ≈ 复盘文档/结项文档
3. 状态口语：
   - 完成/做完/搞定/过了/交付了 → 已完成，progress=100
   - 开始做/在做/推进中 → 进行中；若无进度默认 50
   - 延期/往后放/先放一放/推迟 → 已延期
   - 卡住/阻塞/等确认/没法推进 → 被阻塞
   - 重置/还没开始 → 待开始，progress=0
4. 进度口语：
   - “60% / 百分之六十 / 大概七成 / 一半” → 映射为 60/70/50
   - 只报进度未报状态：progress>=100 → 已完成，否则 → 进行中
5. 负责人：出现“交给小李/让运营跟”等则填 assignee。
6. 截止时间：相对时间按今天推断成 YYYY-MM-DD（明天=+1，这两天=+2，本周=本周日，下周=下周五，月底=月末）。
7. 唯一高置信匹配且至少有一个可更新字段 → intent=update_task，need_clarification=false。
8. 多个任务都像，或关键字段缺失导致不能安全更新 → intent=clarify，列出 candidate_task_ids，并写 clarify_question。
9. 完全听不懂或与任务无关 → intent=unknown。
10. 不要编造任务；task_id 必须来自给定清单。不要输出 JSON 以外的文字。

## 示例
用户：小红书任务完成了
→ 匹配到唯一小红书任务，status=已完成，progress=100，intent=update_task

用户：那个发抖音的先放一放
→ 匹配抖音任务，status=已延期，intent=update_task

用户：方案那块小李先别做了，等客户确认
→ 匹配方案任务，status=被阻塞，assignee=小李，note 保留“等客户确认”

用户：内容做完了
→ 若有小红书和抖音两个内容任务，intent=clarify，请用户选择"""


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
