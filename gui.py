"""
Boss Task Agent - GUI 入口

面向零编程知识用户的图形界面。
套壳现有 cmd_* 逻辑，不改核心代码。

架构要点：
1. LLM 调用一律走后台线程，避免主线程卡死
2. 后台线程 print 的内容通过 queue 转发到主线程更新 Text 控件（tkinter 非线程安全）
3. 首次运行若 .env 不存在，引导用户填 API Key 并写盘
"""

import os
import queue
import sys
import threading
import traceback
import webbrowser
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import Tk, StringVar, END, DISABLED, NORMAL, filedialog, messagebox
from tkinter import ttk, scrolledtext

import config
from boss_task_agent import (
    ExcelReader, TaskParser, SOPGenerator, ProgressTracker,
    LocalTableExporter, RetrospectiveGenerator,
)
from dashboard_generator import generate_dashboard


APP_BG = "#f6f8f8"
SIDEBAR_BG = "#eef8fb"
CARD_BG = "#ffffff"
TEXT = "#111827"
MUTED = "#667085"
BORDER = "#dfe5e7"
ACCENT = "#111827"
ACCENT_HOVER = "#2d3642"
SOFT_BUTTON = "#f3f5f6"
SOFT_BUTTON_HOVER = "#e8eef0"
SUCCESS = "#157347"
WARNING = "#b7791f"


# ════════════════════════════════════════════════════════════════
#  线程安全的日志转发：后台 print → queue → 主线程 Text 控件
# ════════════════════════════════════════════════════════════════

class QueueWriter:
    """把 stdout 写入队列，主线程定期消费。tkinter 只允许主线程操作控件。"""

    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, text: str):
        if text:
            self.q.put(text)

    def flush(self):
        pass


# ════════════════════════════════════════════════════════════════
#  主界面
# ════════════════════════════════════════════════════════════════

class BossTaskGUI:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Boss Task Agent - 老板语音任务智能体")
        self.root.geometry("1120x720")
        self.root.minsize(980, 640)

        self.log_queue: queue.Queue = queue.Queue()
        self.busy = False
        self.action_buttons: list[tk.Button | ttk.Button] = []

        # StringVar 绑定输入框
        self.var_api_key = StringVar(value=config.OPENAI_API_KEY)
        self.var_base_url = StringVar(value=config.OPENAI_BASE_URL)
        self.var_model = StringVar(value=config.OPENAI_MODEL)
        self.var_workbook = StringVar(value=str(config.WORKBOOK_PATH))
        self.var_api_state = StringVar(value="")
        self.var_file_state = StringVar(value="")
        self.var_run_state = StringVar(value="就绪")

        self._configure_styles()
        self._build_ui()
        for var in (self.var_api_key, self.var_base_url, self.var_model, self.var_workbook):
            var.trace_add("write", lambda *_: self._refresh_readiness())
        self._refresh_readiness()
        self._pump_log()  # 启动日志泵

    # ─────────── UI 构建 ───────────

    def _configure_styles(self):
        self.root.configure(bg=APP_BG)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("App.TFrame", background=APP_BG)
        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("Field.TEntry", fieldbackground="#ffffff", padding=(8, 6))
        style.configure("Body.TLabel", background=CARD_BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=CARD_BG, foreground=MUTED, font=("Segoe UI", 9))

    def _build_ui(self):
        shell = tk.Frame(self.root, bg=APP_BG)
        shell.pack(fill="both", expand=True)

        sidebar = tk.Frame(shell, bg=SIDEBAR_BG, width=250)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=SIDEBAR_BG)
        brand.pack(fill="x", padx=18, pady=(24, 18))
        tk.Label(
            brand, text="▣ Boss Task Agent",
            bg=SIDEBAR_BG, fg=TEXT, anchor="w",
            font=("Segoe UI", 16, "bold"),
        ).pack(fill="x")
        tk.Label(
            brand, text="语音摘要 → 任务 / SOP / 看板",
            bg=SIDEBAR_BG, fg=MUTED, anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(4, 0))

        self._sidebar_item(sidebar, "新建处理", active=True)
        self._sidebar_item(sidebar, "配置")
        self._sidebar_item(sidebar, "输出结果")
        self._sidebar_item(sidebar, "帮助")

        tk.Frame(sidebar, bg=SIDEBAR_BG).pack(fill="both", expand=True)
        state_box = tk.Frame(sidebar, bg="#e6f3f6", highlightbackground="#d5e9ee", highlightthickness=1)
        state_box.pack(fill="x", padx=14, pady=(0, 16))
        tk.Label(
            state_box, text="当前状态", bg="#e6f3f6", fg=TEXT,
            anchor="w", font=("Segoe UI", 10, "bold"),
        ).pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(
            state_box, textvariable=self.var_api_state, bg="#e6f3f6", fg=MUTED,
            anchor="w", font=("Segoe UI", 9),
        ).pack(fill="x", padx=12, pady=2)
        tk.Label(
            state_box, textvariable=self.var_file_state, bg="#e6f3f6", fg=MUTED,
            anchor="w", font=("Segoe UI", 9),
        ).pack(fill="x", padx=12, pady=2)
        tk.Label(
            state_box, textvariable=self.var_run_state, bg="#e6f3f6", fg=MUTED,
            anchor="w", font=("Segoe UI", 9),
        ).pack(fill="x", padx=12, pady=(2, 12))

        content = tk.Frame(shell, bg=APP_BG)
        content.pack(side="left", fill="both", expand=True)

        header = tk.Frame(content, bg=APP_BG)
        header.pack(fill="x", padx=28, pady=(22, 14))
        title_group = tk.Frame(header, bg=APP_BG)
        title_group.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_group, text="老板语音任务智能体",
            bg=APP_BG, fg=TEXT, anchor="w",
            font=("Segoe UI", 18, "bold"),
        ).pack(fill="x")
        tk.Label(
            title_group, text="把语音摘要整理成结构化任务、SOP、Excel 和可视化看板",
            bg=APP_BG, fg=MUTED, anchor="w",
            font=("Segoe UI", 10),
        ).pack(fill="x", pady=(4, 0))
        self._plain_button(header, "打开输出目录", self.open_output_dir).pack(side="right", padx=(8, 0))

        api_body = self._card(content, "API 配置", "支持阿里云百炼、Moonshot、OpenAI 兼容接口")
        api_body.columnconfigure(1, weight=1)
        self._field_label(api_body, "API Key").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Entry(api_body, textvariable=self.var_api_key, show="*", style="Field.TEntry").grid(row=0, column=1, sticky="ew", pady=6)
        self._plain_button(api_body, "保存配置", self.save_env, compact=False).grid(row=0, column=2, rowspan=3, sticky="nsew", padx=(12, 0), pady=6)
        self._field_label(api_body, "Base URL").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Entry(api_body, textvariable=self.var_base_url, style="Field.TEntry").grid(row=1, column=1, sticky="ew", pady=6)
        self._field_label(api_body, "模型").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Entry(api_body, textvariable=self.var_model, style="Field.TEntry").grid(row=2, column=1, sticky="ew", pady=6)

        file_body = self._card(content, "语音摘要文件", "选择包含语音转文字内容的 Excel 文件")
        file_body.columnconfigure(0, weight=1)
        ttk.Entry(file_body, textvariable=self.var_workbook, style="Field.TEntry").grid(row=0, column=0, sticky="ew", pady=4)
        self._plain_button(file_body, "浏览", self.pick_workbook).grid(row=0, column=1, padx=(10, 0), pady=4)

        action_body = self._card(content, "任务处理", "先解析语音，再按需生成 SOP、Excel、看板和复盘")
        action_body.columnconfigure(0, weight=1)
        primary = self._action_button(action_body, "🚀 一键全流程", self.run_all, primary=True)
        primary.grid(row=0, column=0, sticky="ew", pady=(2, 12))
        self.action_buttons.append(primary)

        quick = tk.Frame(action_body, bg=CARD_BG)
        quick.grid(row=1, column=0, sticky="ew")
        for c in range(3):
            quick.columnconfigure(c, weight=1, uniform="action")
        actions = [
            ("📢 解析语音", self.run_parse, True),
            ("📑 生成 SOP", self.run_sop, True),
            ("📊 导出 Excel", self.run_table, True),
            ("🌐 打开看板", self.run_dashboard, False),
            ("📝 生成复盘", self.run_retrospective, True),
            ("📂 输出目录", self.open_output_dir, False),
        ]
        for i, (label, cmd, lock_when_busy) in enumerate(actions):
            btn = self._action_button(quick, label, cmd)
            btn.grid(row=i // 3, column=i % 3, sticky="ew", padx=4, pady=4)
            if lock_when_busy:
                self.action_buttons.append(btn)

        log_body = self._card(content, "运行日志", "只显示关键过程；详细错误会写入 output/error.log")
        log_body.master.pack_configure(fill="both", expand=True)
        log_body.pack_configure(fill="both", expand=True)
        self.log_text = scrolledtext.ScrolledText(
            log_body, wrap="word", font=("Cascadia Mono", 10),
            bg="#171923", fg="#e8edf2", insertbackground="#e8edf2",
            relief="flat", padx=12, pady=10,
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state=DISABLED)

        # 状态栏
        self.status_var = StringVar(value="就绪")
        status = tk.Label(
            content, textvariable=self.status_var, anchor="w",
            bg=APP_BG, fg=MUTED, font=("Segoe UI", 9),
        )
        status.pack(fill="x", padx=28, pady=(0, 10))

    def _sidebar_item(self, parent, text: str, active: bool = False):
        bg = "#dfecef" if active else SIDEBAR_BG
        fg = TEXT if active else "#46505a"
        item = tk.Label(
            parent, text=text, bg=bg, fg=fg, anchor="w",
            font=("Segoe UI", 10, "bold" if active else "normal"),
            padx=14, pady=10,
        )
        item.pack(fill="x", padx=12, pady=2)
        return item

    def _card(self, parent, title: str, subtitle: str):
        outer = tk.Frame(parent, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
        outer.pack(fill="x", padx=28, pady=7)
        header = tk.Frame(outer, bg=CARD_BG)
        header.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(
            header, text=title, bg=CARD_BG, fg=TEXT, anchor="w",
            font=("Segoe UI", 12, "bold"),
        ).pack(fill="x")
        tk.Label(
            header, text=subtitle, bg=CARD_BG, fg=MUTED, anchor="w",
            font=("Segoe UI", 9),
        ).pack(fill="x", pady=(2, 0))
        body = tk.Frame(outer, bg=CARD_BG)
        body.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        return body

    def _field_label(self, parent, text: str):
        return tk.Label(parent, text=text, bg=CARD_BG, fg=TEXT, font=("Segoe UI", 10))

    def _plain_button(self, parent, text: str, command, compact: bool = True):
        return tk.Button(
            parent, text=text, command=command, bg=SOFT_BUTTON, fg=TEXT,
            activebackground=SOFT_BUTTON_HOVER, activeforeground=TEXT,
            relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 10),
            padx=12 if compact else 20, pady=7 if compact else 10,
        )

    def _action_button(self, parent, text: str, command, primary: bool = False):
        bg = ACCENT if primary else SOFT_BUTTON
        fg = "#ffffff" if primary else TEXT
        active_bg = ACCENT_HOVER if primary else SOFT_BUTTON_HOVER
        return tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=active_bg, activeforeground=fg,
            disabledforeground="#9aa3ad", relief="flat", bd=0,
            cursor="hand2", font=("Segoe UI", 11 if primary else 10, "bold" if primary else "normal"),
            padx=12, pady=12 if primary else 9,
        )

    # ─────────── 日志泵：主线程消费 queue ───────────

    def _pump_log(self):
        try:
            while True:
                text = self.log_queue.get_nowait()
                self.log_text.configure(state=NORMAL)
                self.log_text.insert(END, text)
                self.log_text.see(END)
                self.log_text.configure(state=DISABLED)
        except queue.Empty:
            pass
        # 100ms 后再拉一次
        self.root.after(100, self._pump_log)

    def _log(self, msg: str):
        """主线程直接写日志的快捷方式"""
        self.log_queue.put(msg + "\n")

    def _refresh_readiness(self):
        key = self.var_api_key.get().strip()
        model = self.var_model.get().strip() or "未填写模型"
        workbook = Path(self.var_workbook.get().strip()) if self.var_workbook.get().strip() else None

        if self._looks_like_placeholder_key(key):
            self.var_api_state.set("● API 未配置")
        else:
            self.var_api_state.set(f"● API 已填写 · {model}")

        if workbook and workbook.exists():
            self.var_file_state.set("● Excel 已选择")
        else:
            self.var_file_state.set("● 等待 Excel 文件")

        self.var_run_state.set(f"● {self.status_var.get() if hasattr(self, 'status_var') else '就绪'}")

    def _looks_like_placeholder_key(self, key: str) -> bool:
        if not key:
            return True
        lowered = key.lower()
        placeholders = ("your-api-key", "sk-your-api-key", "api-key-here", "填入", "替换", "example")
        return any(token in lowered for token in placeholders)

    def _sync_runtime_config(self):
        """让未点击保存的界面输入也能参与本次运行。"""
        key = self.var_api_key.get().strip()
        base = self.var_base_url.get().strip()
        model = self.var_model.get().strip()
        config.OPENAI_API_KEY = key
        config.OPENAI_BASE_URL = base
        config.OPENAI_MODEL = model
        os.environ["OPENAI_API_KEY"] = key
        os.environ["OPENAI_BASE_URL"] = base
        os.environ["OPENAI_MODEL"] = model

    def _friendly_error(self, exc: Exception) -> str:
        text = str(exc)
        if "invalid_api_key" in text or "Incorrect API key" in text:
            return "API Key 无效。请确认填写的是当前平台的大模型 API Key，不是账号密码或 AccessKey。"
        if "401" in text or "AuthenticationError" in type(exc).__name__:
            return "认证失败。请检查 API Key、Base URL 和模型是否属于同一个平台。"
        if "model" in text.lower() and ("not found" in text.lower() or "does not exist" in text.lower()):
            return "模型名称不可用。请检查模型名是否被当前平台支持。"
        if "Connection" in type(exc).__name__ or "connect" in text.lower() or "timeout" in text.lower():
            return "网络连接失败。请检查网络、代理或 API 服务地址。"
        return f"任务失败：{type(exc).__name__}: {exc}"

    def _write_error_log(self, tb: str) -> Path:
        config.OUTPUT_DIR.mkdir(exist_ok=True)
        path = config.OUTPUT_DIR / "error.log"
        with path.open("a", encoding="utf-8") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write(tb)
            if not tb.endswith("\n"):
                f.write("\n")
        return path

    # ─────────── 通用后台执行封装 ───────────

    def _run_bg(self, name: str, fn):
        """把 fn 丢到后台线程跑；期间禁用按钮、重定向 stdout。"""
        if self.busy:
            messagebox.showwarning("请稍候", "上一个任务尚未完成")
            return

        self.busy = True
        for b in self.action_buttons:
            b.configure(state=DISABLED)
        self.status_var.set(f"运行中：{name}")
        self.var_run_state.set(f"● 运行中：{name}")

        def worker():
            old_stdout = sys.stdout
            sys.stdout = QueueWriter(self.log_queue)
            try:
                fn()
            except Exception as e:
                tb = traceback.format_exc()
                err_path = self._write_error_log(tb)
                friendly = self._friendly_error(e)
                self._log(f"\n❌ {friendly}")
                self._log(f"   详细错误已写入：{err_path}")
                self.root.after(0, lambda: messagebox.showerror("任务失败", friendly))
            finally:
                sys.stdout = old_stdout
                # 回主线程恢复 UI
                self.root.after(0, self._done, name)

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, name: str):
        self.busy = False
        for b in self.action_buttons:
            b.configure(state=NORMAL)
        self.status_var.set(f"完成：{name}")
        self.var_run_state.set(f"● 完成：{name}")
        self._log("─" * 60 + "\n")
        self._refresh_readiness()

    # ─────────── 前置检查 ───────────

    def _check_api_key(self) -> bool:
        key = self.var_api_key.get().strip()
        base = self.var_base_url.get().strip()
        model = self.var_model.get().strip()
        if self._looks_like_placeholder_key(key):
            messagebox.showerror(
                "未配置 API Key",
                "请填写真实的大模型 API Key。\n\n"
                "如果使用阿里云百炼，请填写 Model Studio / 百炼里的 API Key，"
                "不是阿里云账号的 AccessKey。"
            )
            return False
        if not base or not model:
            messagebox.showerror("配置不完整", "请填写 Base URL 和模型名称。")
            return False
        self._sync_runtime_config()
        self._refresh_readiness()
        return True

    def _check_workbook(self) -> bool:
        path = Path(self.var_workbook.get())
        if not path.exists():
            messagebox.showerror("找不到文件", f"语音摘要文件不存在：\n{path}")
            return False
        return True

    def _load_instruction_or_warn(self):
        tracker = ProgressTracker()
        instruction = tracker.load_tasks()
        if not instruction:
            messagebox.showwarning("请先解析", "尚未解析任务。请先点击「📢 解析语音」。")
            return None
        return tracker, instruction

    # ─────────── 具体动作 ───────────

    def save_env(self):
        """把当前 API 配置写入 exe 同级的 .env"""
        key = self.var_api_key.get().strip()
        base = self.var_base_url.get().strip()
        model = self.var_model.get().strip()
        if not key:
            messagebox.showerror("API Key 不能为空", "请填写 API Key")
            return

        env_path = config.PROJECT_ROOT / ".env"
        content = (
            "# 由 GUI 自动生成，可手动编辑\n"
            f"OPENAI_API_KEY={key}\n"
            f"OPENAI_BASE_URL={base}\n"
            f"OPENAI_MODEL={model}\n"
        )
        env_path.write_text(content, encoding="utf-8")
        self._sync_runtime_config()
        self._refresh_readiness()

        self._log(f"✅ 配置已保存至：{env_path}")
        messagebox.showinfo("已保存", f"配置已写入：\n{env_path}")

    def pick_workbook(self):
        path = filedialog.askopenfilename(
            title="选择老板语音摘要 Excel 文件",
            filetypes=[("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")],
            initialdir=str(config.PROJECT_ROOT / "input"),
        )
        if path:
            self.var_workbook.set(path)
            # 同步给 config 里的路径，后续 ExcelReader() 使用
            os.environ["BOSS_WORKBOOK_PATH"] = path
            config.WORKBOOK_PATH = Path(path)
            self._refresh_readiness()

    def open_output_dir(self):
        path = str(config.OUTPUT_DIR)
        os.startfile(path) if os.name == "nt" else webbrowser.open(f"file://{path}")

    # ── 后台任务 ──

    def run_parse(self):
        if not (self._check_api_key() and self._check_workbook()):
            return

        def task():
            print("=" * 60)
            print("📢 解析语音 → 结构化任务")
            print("=" * 60)
            reader = ExcelReader(self.var_workbook.get())
            raw_text = reader.read()
            print(f"📄 读取到 {len(raw_text)} 字符\n")

            parser = TaskParser()
            instruction = parser.parse(raw_text)

            tracker = ProgressTracker()
            tracker.save_tasks(instruction)
            print(f"\n✅ 已解析 {len(instruction.tasks)} 个任务：")
            for t in instruction.tasks:
                print(f"   [{t.id}] {t.title}  ({t.priority.value})")

        self._run_bg("解析语音", task)

    def run_sop(self):
        if not self._check_api_key():
            return
        loaded = self._load_instruction_or_warn()
        if not loaded:
            return
        _, instruction = loaded

        def task():
            print("=" * 60)
            print("📑 生成 SOP 流程模板")
            print("=" * 60)
            generator = SOPGenerator()
            sop = generator.generate(instruction)
            md_path = generator.save_as_markdown(sop)
            print(f"✅ SOP 模板已生成：{md_path}")

        self._run_bg("生成 SOP", task)

    def run_table(self):
        loaded = self._load_instruction_or_warn()
        if not loaded:
            return
        _, instruction = loaded

        def task():
            print("=" * 60)
            print("📊 导出 Excel 表格")
            print("=" * 60)
            exporter = LocalTableExporter()
            path = exporter.export(instruction)
            print(f"✅ Excel 已导出：{path}")

        self._run_bg("导出 Excel", task)

    def run_dashboard(self):
        """生成看板并用默认浏览器打开。快速操作，主线程即可。"""
        loaded = self._load_instruction_or_warn()
        if not loaded:
            return
        _, instruction = loaded
        try:
            path = generate_dashboard(instruction)
            self._log(f"✅ 看板已生成：{path}")
            webbrowser.open(str(path))
        except Exception as e:
            messagebox.showerror("生成看板失败", str(e))

    def run_retrospective(self):
        if not self._check_api_key():
            return
        loaded = self._load_instruction_or_warn()
        if not loaded:
            return
        tracker, instruction = loaded

        def task():
            print("=" * 60)
            print("📝 生成复盘报告")
            print("=" * 60)
            generator = RetrospectiveGenerator()
            report, _md = generator.generate(instruction, tracker.history)
            print(f"✅ 复盘报告已生成：{config.RETROSPECTIVE_MD}")
            print(f"   做得好 {len(report.what_went_well)} 条 / "
                  f"需改进 {len(report.what_needs_improvement)} 条 / "
                  f"行动项 {len(report.action_items)} 条")

        self._run_bg("生成复盘", task)

    def run_all(self):
        if not (self._check_api_key() and self._check_workbook()):
            return

        def task():
            print("🚀 " + "=" * 56)
            print("   一键全流程")
            print("🚀 " + "=" * 56 + "\n")

            # 1. 解析
            print("─── 步骤 1/4: 解析语音 ───")
            reader = ExcelReader(self.var_workbook.get())
            raw_text = reader.read()
            parser = TaskParser()
            instruction = parser.parse(raw_text)
            tracker = ProgressTracker()
            tracker.save_tasks(instruction)
            print(f"✅ 已解析 {len(instruction.tasks)} 个任务\n")

            # 2. SOP
            print("─── 步骤 2/4: 生成 SOP ───")
            sop_gen = SOPGenerator()
            sop = sop_gen.generate(instruction)
            md_path = sop_gen.save_as_markdown(sop)
            print(f"✅ SOP：{md_path}\n")

            # 3. Excel
            print("─── 步骤 3/4: 导出 Excel ───")
            xlsx = LocalTableExporter().export(instruction)
            print(f"✅ Excel：{xlsx}\n")

            # 4. 看板
            print("─── 步骤 4/4: 生成看板 ───")
            html_path = generate_dashboard(instruction)
            print(f"✅ 看板：{html_path}\n")

            print("🎉 全流程完成！可在「打开输出目录」查看所有产物。")
            # 主线程打开浏览器
            self.root.after(0, lambda: webbrowser.open(str(html_path)))

        self._run_bg("一键全流程", task)


def main():
    root = Tk()
    # 使用系统主题
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    BossTaskGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
