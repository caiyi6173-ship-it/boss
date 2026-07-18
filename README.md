# Boss Task Agent

Boss Task Agent 是一个面向项目执行场景的桌面工具，可以把老板语音音频或会议转录 Excel 自动整理成结构化任务，并继续生成 SOP、Excel 任务表、HTML 看板和复盘报告。

项目提供命令行和 GUI 两种入口，GUI 版本可以通过 PyInstaller 打包成 Windows 桌面应用分发给非技术用户。

## 功能亮点

- 导入 MP3/WAV/M4A 并使用本地 Whisper 转写，也兼容 Excel 转写稿
- 每条输入自动添加分段 ID、职位、来源与音频时间范围，形成字段级证据链
- 解析语音转录内容，生成结构化任务清单
- 自动提炼可复用 SOP 流程模板
- 导出本地 Excel 任务表
- 生成可视化 HTML 任务看板
- 基于进度历史生成项目复盘报告
- 使用 SQLite 事务保存项目、任务、依赖、交付物和进度事件
- 提供浅色桌面 GUI，支持一键全流程处理
- 支持对话式任务更新（LLM 意图理解），例如输入“小红书任务完成”“那个发抖音的先放一放”，自动匹配并更新；听不准时会反问
- 支持 OpenAI 兼容接口，例如阿里云百炼 DashScope、Moonshot、OpenAI

## 项目结构

```text
.
├── gui.py                    # 桌面 GUI 入口
├── main.py                   # 命令行入口
├── boss_task_agent.py        # 核心任务解析、SOP、复盘逻辑
├── database.py               # SQLite schema、事务存储与旧 JSON 迁移
├── dashboard_generator.py    # HTML 看板生成
├── models.py                 # Pydantic 数据模型
├── config.py                 # 配置与路径管理
├── build.bat                 # Windows 打包脚本
├── input/                    # 输入 Excel 目录，本地数据不提交
├── output/                   # 运行产物目录，本地数据不提交
├── domain_glossary.json      # 业务同义词词典（可编辑）
├── resources/                # 通用资源（含 chi-syn 中文同义词库）
│   └── chinese_synonym.txt
├── tools/                    # 辅助脚本
│   └── import_chinese_synonyms.py
└── sop_templates/            # SOP 输出目录，本地生成内容不提交
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

如果需要直接导入 MP3、WAV 或 M4A 音频，再安装本地转写依赖：

```bash
pip install -r requirements-audio.txt
```

首次转写会自动下载 `small` Whisper 模型；可以在 `.env` 中通过
`BOSS_WHISPER_MODEL` 切换模型。

开发和打包环境还需要：

```bash
pip install -r requirements-dev.txt
```

### 2. 配置 API

复制 `.env.example` 为 `.env`，并填写真实 API Key：

```env
OPENAI_API_KEY=sk-your-real-api-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus
```

注意：如果使用阿里云百炼，需要填写百炼 / Model Studio 的 API Key，不是阿里云账号的 AccessKey。

### 3. 准备输入文件

默认输入文件路径：

```text
input/Workbook.xlsx
```

可以使用影刀 RPA 自动生成该文件：

[影刀 Workbook 生成工具](https://api.winrobot360.com/redirect/robot/share?inviteKey=c7b51ef45fe9af10)

执行影刀流程后，将生成的 Excel 保存为 `input/Workbook.xlsx`。也可以在 GUI 中点击「浏览」选择其他 `.xlsx`、`.mp3`、`.wav` 或 `.m4a` 文件。音频会先在本地转写，再继续调用现有 `TaskParser`。

GUI 中需要填写“每条信息前缀职位”，默认是“老板”。音频转写结果示例：

```text
[S0001][职位:总经理][时间:00:03.200-00:08.100][来源:meeting.m4a] 下周一把活动方案交给我
```

AI 生成的任务、负责人、截止日期、交付物和依赖会引用对应分段 ID，且引文必须逐字存在于原话中。

### 4. 启动 GUI

```bash
python gui.py
```

进入窗口后点击「一键全流程」，会依次完成：

```text
解析语音 -> 生成 SOP -> 导出 Excel -> 生成看板
```

解析完成后，也可以在「对话执行」输入自然语言更新已有任务，例如：

```text
小红书任务完成
T003 进度 60%
方案任务延期
拍摄任务卡住了
```

系统会调用 LLM 结合当前任务清单理解意图，匹配任务并更新状态/进度/负责人/截止日期；若无法唯一确定会反问，而不是硬猜。成功后会刷新 Excel 任务表与 HTML 看板。

## 命令行用法

```bash
python main.py parse
python main.py parse --input input/meeting.m4a --speaker-role 总经理
python main.py sop
python main.py table
python main.py dashboard
python main.py retrospective
python main.py run-all
```

查看或更新任务进度：

```bash
python main.py status
python main.py update T001 进行中 50 --note "策划方案撰写中"
```

## 输出文件

```text
output/boss_tasks.db               SQLite 主数据库（任务、依赖、交付物、进度历史）
output/task_table.xlsx             Excel 任务表格
output/task_dashboard.html         可视化看板
output/retrospective_report.md     复盘报告
sop_templates/                     SOP 流程模板
```

Excel 导出包含独立的“证据链”和“来源分段”工作表，可查看字段、职位、时间、来源原话和置信度。

旧版本的 `output/structured_tasks.json` 和 `output/progress_history.json` 会在
数据库首次创建时自动迁移。迁移成功后原 JSON 文件保留为备份，但不再作为运行时主存储。

## 打包 Windows 桌面版

```bat
build.bat
```

打包完成后，发布目录为：

```text
dist/BossTaskAgent/
```

也可以将 `dist/BossTaskAgent.zip` 发给用户。用户电脑不需要安装 Python，但仍需要准备 API Key、输入 Excel，并保持网络可用。

## 安全说明

- `.env`、`input/` 下的 Excel/音频、`output/`、`dist/`、`build/` 已被 `.gitignore` 忽略
- 不要把真实 API Key、客户语音转录、项目输出结果提交到公开仓库
- README 中只保留示例配置，不包含任何真实密钥

## License

本项目基于 [MIT License](LICENSE) 开源。
