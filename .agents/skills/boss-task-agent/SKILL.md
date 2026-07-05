---
name: boss-task-agent
description: 自动将老板语音摘要解析为结构化工作指令，生成可复用 SOP 模板，提供可视化 HTML 看板、Excel 导出与任务进度自动跟踪复盘。
---

# 老板语音与任务自动化管理技能 (Boss Task Agent Skill)

本 Skill 用于处理老板发出的模糊、口语化语音指令，将其转化为标准化的团队工作任务、SOP 指导文档和可视化进度看板。

## 核心功能与使用指令

所有功能可通过根目录下的命令行工具 `main.py` 调用：

### 1. 解析语音 → 结构化任务
将 `Workbook.xlsx` 中的语音摘要解析为包含标题、分类、优先级、截止日期、交付物的 JSON 任务集。
```bash
python main.py parse
```

### 2. 生成 SOP 流程模板
基于解析出的任务，自动提炼通用 SOP 操作标准并沉淀到 `sop_templates/` 目录。
```bash
python main.py sop
```

### 3. 查看与更新任务进度
查看整体进度，或更新某个任务的状态与完成百分比：
```bash
# 查看进度
python main.py status

# 更新任务状态 (格式: python main.py update <任务ID> <状态> <完成百分比> --note "备注")
python main.py update T001 进行中 50 --note "策划方案撰写中"
```

### 4. 导出可视化成果
```bash
# 生成高颜值暗色毛玻璃静态 HTML 看板 (网页打卡)
python main.py dashboard

# 导出本地带排版着色的 Excel 任务大表
python main.py table
```

### 5. 生成复盘报告
项目结束后，基于历史进度变更记录自动生成 Markdown 复盘报告：
```bash
python main.py retrospective
```

### 6. 一键全流程执行
一键自动运行从语音读取、任务解析、SOP 生成到本地表格和看板输出的整套工作流：
```bash
python main.py run-all
```

---

## 配置文件规范 (`.env`)
API 密钥等敏感信息统一置于项目根目录的 `.env` 文件中，并已被 `.gitignore` 保护：
```env
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=kimi-k2.5
```
