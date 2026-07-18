"""
Boss Task Agent - GUI 入口 (CustomTkinter 现代版)

面向用户的现代化图形界面，基于 CustomTkinter 框架构建。
具备深色/浅色自适应主题、卡片化 Fluent 布局、多线程安全机制和智能指令对话框。
"""

import os
import queue
import re
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
import tkinter as tk
from tkinter import StringVar, END, DISABLED, NORMAL, filedialog, messagebox
import customtkinter as ctk

import config
from boss_task_agent import (
    InputReader, SUPPORTED_INPUT_EXTENSIONS, TaskParser, SOPGenerator, ProgressTracker,
    LocalTableExporter, RetrospectiveGenerator, ChatIntentParser,
)
from models import ChatIntentType, TaskStatus
from dashboard_generator import generate_dashboard

# ════════════════════════════════════════════════════════════════
#  主题与颜色系统配置
# ════════════════════════════════════════════════════════════════

ctk.set_appearance_mode("System")  # 默认跟随系统
ctk.set_default_color_theme("blue")  # 蓝色主题

# 高级配色方案 (Light, Dark)
COLOR_BRAND = ("#1a73e8", "#4285f4")        # 品牌蓝色
COLOR_SUCCESS = ("#2ecc71", "#2ecc71")      # 成功绿色
COLOR_WARNING = ("#f1c40f", "#f1c40f")      # 警告黄色
COLOR_DANGER = ("#e74c3c", "#e74c3c")       # 危险红色
COLOR_INFO = ("#3498db", "#3498db")         # 信息蓝色

COLOR_SIDEBAR_BG = ("#ebebeb", "#17171c")   # 侧边栏背景
COLOR_CARD_BG = ("#ffffff", "#222227")      # 卡片背景
COLOR_TEXT_MAIN = ("#111827", "#f3f4f6")    # 主文本
COLOR_TEXT_MUTED = ("#6b7280", "#9ca3af")   # 辅助文本


# ════════════════════════════════════════════════════════════════
#  线程安全的日志转发：后台 print → queue → 主线程 Textbox
# ════════════════════════════════════════════════════════════════

class QueueWriter:
    """把 stdout 写入队列，主线程定期消费。"""

    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, text: str):
        if text:
            self.q.put(text)

    def flush(self):
        pass


# ════════════════════════════════════════════════════════════════
#  主界面类
# ════════════════════════════════════════════════════════════════

class BossTaskGUI:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("Boss Task Agent - 老板语音任务智能体")
        self.root.geometry("1180x760")
        self.root.minsize(1020, 680)

        self.log_queue: queue.Queue = queue.Queue()
        self.busy = False
        self.action_buttons: list[ctk.CTkButton] = []

        # 状态控制变量
        self.api_key_hidden = True

        # StringVar 绑定输入框与显示变量
        self.var_api_key = StringVar(value=config.OPENAI_API_KEY)
        self.var_base_url = StringVar(value=config.OPENAI_BASE_URL)
        self.var_model = StringVar(value=config.OPENAI_MODEL)
        self.var_input = StringVar(value=str(config.INPUT_PATH))
        self.var_speaker_role = StringVar(value=config.DEFAULT_SPEAKER_ROLE)
        self.var_api_state = StringVar(value="● 检测中...")
        self.var_file_state = StringVar(value="● 检测中...")
        self.var_run_state = StringVar(value="● 就绪")
        self.var_chat = StringVar(value="")
        self.status_var = StringVar(value="就绪")

        self._build_ui()
        
        # 绑定实时变动监听
        for var in (
            self.var_api_key,
            self.var_base_url,
            self.var_model,
            self.var_input,
            self.var_speaker_role,
        ):
            var.trace_add("write", lambda *_: self._refresh_readiness())
        self._refresh_readiness()
        self._pump_log()  # 启动日志泵

    def _build_ui(self):
        # ── 1. 侧边栏 (Sidebar) ──
        sidebar = ctk.CTkFrame(self.root, width=260, corner_radius=0, fg_color=COLOR_SIDEBAR_BG)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # 侧边栏品牌区
        brand_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand_frame.pack(fill="x", padx=24, pady=(32, 24))
        
        logo = ctk.CTkLabel(
            brand_frame, text="▣ Boss Task Agent", 
            font=ctk.CTkFont(size=20, weight="bold"), 
            text_color=COLOR_BRAND, anchor="w"
        )
        logo.pack(fill="x")
        
        subtitle = ctk.CTkLabel(
            brand_frame, text="语音摘要 → 任务/SOP/看板/复盘", 
            font=ctk.CTkFont(size=11), 
            text_color=COLOR_TEXT_MUTED, anchor="w"
        )
        subtitle.pack(fill="x", pady=(4, 0))

        # 侧边栏导航模拟项
        self._sidebar_item(sidebar, "📋 任务中心", active=True)
        self._sidebar_item(sidebar, "⚙️ 系统设置")
        self._sidebar_item(sidebar, "📂 历史归档")

        # 伸缩空白区
        spacer = ctk.CTkFrame(sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # 状态看板框架
        state_box = ctk.CTkFrame(sidebar, corner_radius=12, border_width=1, border_color=("#dcdcdc", "#2d2d32"))
        state_box.pack(fill="x", padx=16, pady=(0, 16))
        
        state_title = ctk.CTkLabel(
            state_box, text="系统监控指示", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_TEXT_MAIN, anchor="w"
        )
        state_title.pack(fill="x", padx=14, pady=(12, 6))

        self.label_api_state = ctk.CTkLabel(
            state_box, textvariable=self.var_api_state, 
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_MUTED, anchor="w"
        )
        self.label_api_state.pack(fill="x", padx=14, pady=2)

        self.label_file_state = ctk.CTkLabel(
            state_box, textvariable=self.var_file_state, 
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_MUTED, anchor="w"
        )
        self.label_file_state.pack(fill="x", padx=14, pady=2)

        self.label_run_state = ctk.CTkLabel(
            state_box, textvariable=self.var_run_state, 
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_MUTED, anchor="w"
        )
        self.label_run_state.pack(fill="x", padx=14, pady=(2, 14))

        # 主题切换
        theme_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        theme_frame.pack(fill="x", padx=16, pady=(0, 24))
        
        theme_label = ctk.CTkLabel(theme_frame, text="主题模式", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED)
        theme_label.pack(side="left", padx=4)
        
        theme_menu = ctk.CTkOptionMenu(
            theme_frame, values=["System", "Dark", "Light"], 
            width=100, height=28, font=ctk.CTkFont(size=11),
            command=self.change_appearance_mode_event
        )
        theme_menu.pack(side="right")
        theme_menu.set("System")

        # ── 2. 右侧主工作区 (Main Pane) ──
        main_pane = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        main_pane.pack(side="right", fill="both", expand=True)

        # 顶部标题栏
        header = ctk.CTkFrame(main_pane, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 16))
        
        title_group = ctk.CTkFrame(header, fg_color="transparent")
        title_group.pack(side="left", fill="x", expand=True)
        
        main_title = ctk.CTkLabel(
            title_group, text="老板语音任务智能体中心", 
            font=ctk.CTkFont(size=22, weight="bold"), 
            text_color=COLOR_TEXT_MAIN, anchor="w"
        )
        main_title.pack(fill="x")
        
        main_subtitle = ctk.CTkLabel(
            title_group, text="智能解析非结构化指令，自动流转并沉淀为业务规范 SOP 看板", 
            font=ctk.CTkFont(size=12), 
            text_color=COLOR_TEXT_MUTED, anchor="w"
        )
        main_subtitle.pack(fill="x", pady=(4, 0))

        dir_btn = ctk.CTkButton(
            header, text="📂 打开输出目录", width=120, height=36,
            font=ctk.CTkFont(size=12), fg_color="transparent", 
            border_width=1, text_color=COLOR_TEXT_MAIN,
            hover_color=("#e5e5e5", "#2d2d32"), command=self.open_output_dir
        )
        dir_btn.pack(side="right", padx=(8, 0))

        # 主滚动面板 (内容自适应)
        content_scroll = ctk.CTkScrollableFrame(main_pane, fg_color="transparent")
        content_scroll.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        # ── 卡片 A: API 配置 ──
        api_body = self._card(content_scroll, "🔑 大模型 API 接口配置", "支持阿里云百炼（Kimi 等模型）、Moonshot 及 OpenAI 规范端点")
        api_body.columnconfigure(1, weight=1)



        # Labels
        self._field_label(api_body, "API Key").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self._field_label(api_body, "Base URL").grid(row=1, column=0, sticky="w", padx=(0, 12))
        self._field_label(api_body, "使用模型").grid(row=2, column=0, sticky="w", padx=(0, 12))

        # Entries & Toggle
        key_frame = ctk.CTkFrame(api_body, fg_color="transparent")
        key_frame.grid(row=0, column=1, sticky="ew")
        key_frame.columnconfigure(0, weight=1)
        
        self.api_key_entry = ctk.CTkEntry(
            key_frame, textvariable=self.var_api_key, show="*", 
            placeholder_text="sk-...", height=32, font=ctk.CTkFont(size=12)
        )
        self.api_key_entry.grid(row=0, column=0, sticky="ew")
        
        self.show_hide_btn = ctk.CTkButton(
            key_frame, text="显示", width=50, height=32, 
            fg_color="transparent", hover_color=("#e5e5e5", "#2d2d32"),
            text_color=COLOR_TEXT_MAIN, command=self.toggle_api_key_visibility
        )
        self.show_hide_btn.grid(row=0, column=1, padx=(6, 0))

        ctk.CTkEntry(
            api_body, textvariable=self.var_base_url, height=32, 
            placeholder_text="https://...", font=ctk.CTkFont(size=12)
        ).grid(row=1, column=1, sticky="ew")
        
        ctk.CTkEntry(
            api_body, textvariable=self.var_model, height=32, 
            placeholder_text="kimi-k2.5", font=ctk.CTkFont(size=12)
        ).grid(row=2, column=1, sticky="ew")

        # Save Button
        save_btn = ctk.CTkButton(
            api_body, text="保存配置", width=90, 
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.save_env
        )
        save_btn.grid(row=0, column=2, rowspan=3, sticky="nsew", padx=(16, 0))

        # ── 卡片 B: 输入文件选择 ──
        file_body = self._card(
            content_scroll,
            "🎧 语音或转写数据源",
            "支持 Excel 转写稿，以及 MP3/WAV/M4A 本地音频转写",
        )
        file_body.columnconfigure(0, weight=1)

        file_entry = ctk.CTkEntry(
            file_body, textvariable=self.var_input, height=32,
            placeholder_text="D:\\...", font=ctk.CTkFont(size=12)
        )
        file_entry.grid(row=0, column=0, sticky="ew")
        
        browse_btn = ctk.CTkButton(
            file_body, text="浏览文件", width=90, height=32,
            font=ctk.CTkFont(size=12), fg_color="transparent", 
            border_width=1, text_color=COLOR_TEXT_MAIN,
            hover_color=("#e5e5e5", "#2d2d32"), command=self.pick_input
        )
        browse_btn.grid(row=0, column=1, padx=(12, 0))

        ctk.CTkLabel(
            file_body,
            text="每条信息前缀职位",
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))
        ctk.CTkEntry(
            file_body,
            textvariable=self.var_speaker_role,
            height=30,
            width=150,
            placeholder_text="例如：老板 / 项目经理",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=1, padx=(12, 0), pady=(10, 0))

        # ── 卡片 C: 任务智能处理 ──
        action_body = self._card(content_scroll, "⚡ 智能体控制台与交互中心", "执行一键流水线处理，或使用下方输入框直接与智能体进行对话更新")
        action_body.columnconfigure(0, weight=1)

        # 一键全流程大按钮
        primary = ctk.CTkButton(
            action_body, text="🚀 开始一键全流程自动化处理", height=42,
            font=ctk.CTkFont(size=14, weight="bold"), fg_color=COLOR_BRAND,
            hover_color=("#155fa0", "#357ae8"), command=self.run_all
        )
        primary.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.action_buttons.append(primary)

        # 对话交互行
        chat_row = ctk.CTkFrame(action_body, fg_color="transparent")
        chat_row.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        chat_row.columnconfigure(0, weight=1)
        
        chat_entry = ctk.CTkEntry(
            chat_row, textvariable=self.var_chat, height=36,
            placeholder_text="💬 在这里输入自然语言，例如：'T001 进度 60%' 或 '视频拍摄任务搞定了'",
            font=ctk.CTkFont(size=12)
        )
        chat_entry.grid(row=0, column=0, sticky="ew")
        chat_entry.bind("<Return>", lambda _event: self.run_chat_command())
        
        chat_btn = ctk.CTkButton(
            chat_row, text="发送指令", width=90, height=36,
            font=ctk.CTkFont(size=12, weight="bold"), command=self.run_chat_command
        )
        chat_btn.grid(row=0, column=1, padx=(12, 0))
        self.action_buttons.append(chat_btn)

        # 快捷按钮面板 (2x3 Grid)
        quick_grid = ctk.CTkFrame(action_body, fg_color="transparent")
        quick_grid.grid(row=2, column=0, sticky="ew")
        for c in range(3):
            quick_grid.columnconfigure(c, weight=1, uniform="action")

        actions = [
            ("📢 解析语音", self.run_parse, True),
            ("📑 生成 SOP", self.run_sop, True),
            ("📊 导出 Excel", self.run_table, True),
            ("🌐 打开看板", self.run_dashboard, False),
            ("📝 生成复盘", self.run_retrospective, True),
            ("📂 输出目录", self.open_output_dir, False),
        ]
        for idx, (label, cmd, lock_when_busy) in enumerate(actions):
            btn = ctk.CTkButton(
                quick_grid, text=label, height=32,
                font=ctk.CTkFont(size=12), fg_color=("#f3f4f6", "#2d2d32"),
                border_width=1, border_color=("#dcdcdc", "#3d3d42"),
                text_color=COLOR_TEXT_MAIN, hover_color=("#e5e5e5", "#3a3a42"),
                command=cmd
            )
            btn.grid(row=idx // 3, column=idx % 3, sticky="ew", padx=4, pady=4)
            if lock_when_busy:
                self.action_buttons.append(btn)

        # ── 卡片 D: 运行日志控制台 ──
        log_body = self._card(content_scroll, "🖥️ 实时日志输出", "主进程及智能体后台日志，滚动记录工作轨迹")
        log_body.master.pack_configure(fill="both", expand=True)
        log_body.pack_configure(fill="both", expand=True)

        self.log_text = ctk.CTkTextbox(
            log_body, height=180, wrap="word", 
            font=ctk.CTkFont(family="Cascadia Mono", size=11),
            fg_color=("#111116", "#0a0a0f"), text_color="#e0e0e8",
            border_width=1, border_color="#1e1e24"
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state=DISABLED)

        # ── 3. 底栏状态栏 ──
        self.status_bar = ctk.CTkLabel(
            main_pane, textvariable=self.status_var, height=24,
            font=ctk.CTkFont(size=11), text_color=COLOR_TEXT_MUTED, anchor="w"
        )
        self.status_bar.pack(fill="x", padx=24, pady=(4, 8))

    def _sidebar_item(self, parent, text: str, active: bool = False):
        bg = ("#d5d5d8", "#242429") if active else "transparent"
        fg = COLOR_TEXT_MAIN if active else COLOR_TEXT_MUTED
        
        item = ctk.CTkLabel(
            parent, text=text, fg_color=bg, text_color=fg, anchor="w",
            font=ctk.CTkFont(size=13, weight="bold" if active else "normal"),
            corner_radius=8, height=36
        )
        item.pack(fill="x", padx=12, pady=3)
        return item

    def _card(self, parent, title: str, subtitle: str):
        outer = ctk.CTkFrame(
            parent, corner_radius=12, border_width=1, 
            border_color=("#dcdcdc", "#2d2d32"), fg_color=COLOR_CARD_BG
        )
        outer.pack(fill="x", padx=4, pady=6)
        
        header = ctk.CTkFrame(outer, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 4))
        
        tk_title = ctk.CTkLabel(
            header, text=title, font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT_MAIN, anchor="w"
        )
        tk_title.pack(fill="x")
        
        tk_subtitle = ctk.CTkLabel(
            header, text=subtitle, font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_MUTED, anchor="w"
        )
        tk_subtitle.pack(fill="x", pady=(2, 0))
        
        body = ctk.CTkFrame(outer, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(6, 12))
        return body

    def _field_label(self, parent, text: str):
        return ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_MAIN)

    def change_appearance_mode_event(self, new_appearance_mode: str):
        """响应侧边栏的主题选择切换"""
        ctk.set_appearance_mode(new_appearance_mode)

    def toggle_api_key_visibility(self):
        """一键隐藏/显式 API Key"""
        if self.api_key_hidden:
            self.api_key_entry.configure(show="")
            self.show_hide_btn.configure(text="隐藏")
            self.api_key_hidden = False
        else:
            self.api_key_entry.configure(show="*")
            self.show_hide_btn.configure(text="显示")
            self.api_key_hidden = True

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
        """日志写入快捷函数"""
        self.log_queue.put(msg + "\n")

    def _refresh_readiness(self):
        key = self.var_api_key.get().strip()
        model = self.var_model.get().strip() or "未知模型"
        input_str = self.var_input.get().strip()
        input_path = Path(input_str) if input_str else None

        # 1. 监测 API 状态
        if self._looks_like_placeholder_key(key):
            self.var_api_state.set("● API 未配置")
            if hasattr(self, 'label_api_state'):
                self.label_api_state.configure(text_color=COLOR_DANGER)
        else:
            self.var_api_state.set(f"● API 已就绪 ({model})")
            if hasattr(self, 'label_api_state'):
                self.label_api_state.configure(text_color=COLOR_SUCCESS)

        # 2. 监测输入文件状态
        if (
            input_path
            and input_path.exists()
            and input_path.suffix.lower() in SUPPORTED_INPUT_EXTENSIONS
        ):
            source_type = "音频" if input_path.suffix.lower() != ".xlsx" else "Excel"
            self.var_file_state.set(f"● {source_type} 数据源有效")
            if hasattr(self, 'label_file_state'):
                self.label_file_state.configure(text_color=COLOR_SUCCESS)
        else:
            self.var_file_state.set("● 缺少有效输入文件")
            if hasattr(self, 'label_file_state'):
                self.label_file_state.configure(text_color=COLOR_WARNING)

        # 3. 监测当前系统状态
        status_text = self.status_var.get()
        self.var_run_state.set(f"● 引擎状态: {status_text}")
        if hasattr(self, 'label_run_state'):
            if "运行中" in status_text:
                self.label_run_state.configure(text_color=COLOR_INFO)
            elif "失败" in status_text or "错误" in status_text:
                self.label_run_state.configure(text_color=COLOR_DANGER)
            else:
                self.label_run_state.configure(text_color=COLOR_SUCCESS)

    def _looks_like_placeholder_key(self, key: str) -> bool:
        if not key:
            return True
        lowered = key.lower()
        placeholders = ("your-api-key", "sk-your-api-key", "api-key-here", "填入", "替换", "example")
        return any(token in lowered for token in placeholders)

    def _sync_runtime_config(self):
        """让界面实时填写的 API 信息加入 runtime 变量中"""
        key = self.var_api_key.get().strip()
        base = self.var_base_url.get().strip()
        model = self.var_model.get().strip()
        config.OPENAI_API_KEY = key
        config.OPENAI_BASE_URL = base
        config.OPENAI_MODEL = model
        config.DEFAULT_SPEAKER_ROLE = self.var_speaker_role.get().strip() or "老板"
        os.environ["OPENAI_API_KEY"] = key
        os.environ["OPENAI_BASE_URL"] = base
        os.environ["OPENAI_MODEL"] = model
        os.environ["BOSS_SPEAKER_ROLE"] = config.DEFAULT_SPEAKER_ROLE

    def _friendly_error(self, exc: Exception) -> str:
        text = str(exc)
        if "音频转写组件未安装" in text:
            return "音频转写组件未安装。请运行 pip install -r requirements-audio.txt。"
        if "音频转写失败" in text:
            return text
        if "invalid_api_key" in text or "Incorrect API key" in text:
            return "API Key 校验未通过，请检查所填写的 Key 是否合法有效。"
        if "401" in text or "AuthenticationError" in type(exc).__name__:
            return "鉴权错误。请核对 API Key、Base URL 以及模型配置。"
        if "model" in text.lower() and ("not found" in text.lower() or "does not exist" in text.lower()):
            return "当前选择的 AI 模型名称在云端无法找到，请确认名称。"
        if "Connection" in type(exc).__name__ or "connect" in text.lower() or "timeout" in text.lower():
            return "与大模型服务器连接失败，请检查网络链接或代理。"
        return f"任务执行遇到异常：{type(exc).__name__}: {exc}"

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
        """多线程后台任务调度，防止 UI 主线程阻塞卡死。"""
        if self.busy:
            messagebox.showwarning("处理中", "前一处理流程尚未结束，请稍候。")
            return

        self.busy = True
        for btn in self.action_buttons:
            btn.configure(state=DISABLED)
        self.status_var.set(f"正在进行：{name}")
        self.var_run_state.set(f"● 正在进行：{name}")

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
                self._log(f"   详情请查阅错误日志：{err_path}")
                self.root.after(0, lambda: messagebox.showerror("任务失败", friendly))
            finally:
                sys.stdout = old_stdout
                self.root.after(0, self._done, name)

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, name: str):
        self.busy = False
        for btn in self.action_buttons:
            btn.configure(state=NORMAL)
        self.status_var.set(f"就绪 (完成：{name})")
        self.var_run_state.set(f"● 就绪")
        self._log("─" * 60 + "\n")
        self._refresh_readiness()

    # ─────────── 前置检查与加载 ───────────

    def _check_api_key(self) -> bool:
        key = self.var_api_key.get().strip()
        base = self.var_base_url.get().strip()
        model = self.var_model.get().strip()
        if self._looks_like_placeholder_key(key):
            messagebox.showerror(
                "API 未配置",
                "请输入正确有效的大模型 API 密钥。\n\n"
                "如使用阿里云百炼，请输入您的百炼 API Key。"
            )
            return False
        if not base or not model:
            messagebox.showerror("配置不完整", "API Base URL 和模型名称不可为空。")
            return False
        self._sync_runtime_config()
        self._refresh_readiness()
        return True

    def _check_input(self) -> bool:
        path = Path(self.var_input.get())
        if not path.exists():
            messagebox.showerror("文件不存在", f"无法定位输入文件：\n{path}")
            return False
        if path.suffix.lower() not in SUPPORTED_INPUT_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_INPUT_EXTENSIONS))
            messagebox.showerror("格式不支持", f"请选择以下格式：{supported}")
            return False
        if not self.var_speaker_role.get().strip():
            messagebox.showerror("职位不能为空", "请填写每条信息前缀使用的发言人职位。")
            return False
        return True

    def _load_instruction_or_warn(self):
        tracker = ProgressTracker()
        instruction = tracker.load_tasks()
        if not instruction:
            messagebox.showwarning("未找到数据", "请先解析任务。单击「📢 解析语音」开始。")
            return None
        return tracker, instruction

    def _parse_chat_intent(self, command: str):
        """自然语言任务进度及状态智能意图理解。"""
        status = None
        progress = None

        percent_match = re.search(r"(\d{1,3})\s*%|百分之\s*(\d{1,3})", command)
        if percent_match:
            raw = percent_match.group(1) or percent_match.group(2)
            progress = max(0, min(100, int(raw)))

        if any(k in command for k in ("完成", "做完", "搞定", "结束", "交付了", "已交付")):
            status = "已完成"
            progress = 100 if progress is None else progress
        elif any(k in command for k in ("开始", "进行中", "在做", "处理中", "推进中", "已启动")):
            status = "进行中"
            progress = 50 if progress is None else progress
        elif any(k in command for k in ("延期", "延后", "推迟", "来不及")):
            status = "已延期"
        elif any(k in command for k in ("阻塞", "卡住", "卡了", "被卡", "无法推进")):
            status = "被阻塞"
        elif any(k in command for k in ("待开始", "未开始", "重置")):
            status = "待开始"
            progress = 0 if progress is None else progress

        if status is None and progress is not None:
            status = "已完成" if progress >= 100 else "进行中"

        return status, progress

    def _clean_task_query(self, command: str) -> str:
        query = re.sub(r"T\d{1,4}", " ", command, flags=re.IGNORECASE)
        query = re.sub(r"\d{1,3}\s*%|百分之\s*\d{1,3}", " ", query)
        for word in (
            "任务", "事项", "工作", "项目", "帮我", "请", "把", "将", "一下", "这个", "那个",
            "已经", "已", "了", "啦", "完成", "做完", "搞定", "结束", "交付", "开始",
            "进行中", "在做", "处理中", "推进中", "启动", "延期", "延后", "推迟",
            "阻塞", "卡住", "卡了", "无法推进", "待开始", "未开始", "重置", "进度"
        ):
            query = query.replace(word, " ")
        query = re.sub(r"[，。！？、,.!?:：;；()\[\]【】\"'“”‘’]", " ", query)
        return re.sub(r"\s+", " ", query).strip().lower()

    def _task_search_text(self, task) -> str:
        deliverables = " ".join(d.name + " " + d.description for d in task.deliverables)
        return f"{task.id} {task.title} {task.description} {task.category.value} {task.notes} {deliverables}".lower()

    def _match_task_from_command(self, command: str, instruction):
        id_match = re.search(r"\b(T\d{1,4})\b", command, flags=re.IGNORECASE)
        if id_match:
            task_id = id_match.group(1).upper()
            for task in instruction.tasks:
                if task.id.upper() == task_id:
                    return task, []
            return None, []

        query = self._clean_task_query(command)
        if not query:
            return None, []

        scored = []
        for task in instruction.tasks:
            title = task.title.lower()
            text = self._task_search_text(task)
            score = SequenceMatcher(None, query, title).ratio() * 0.55
            if query in text:
                score += 0.55
            if query in title:
                score += 0.25
            if any(ch in text for ch in query if not ch.isspace()):
                common = sum(1 for ch in set(query) if ch in text and not ch.isspace())
                score += min(0.25, common / max(len(set(query)), 1) * 0.25)
            scored.append((score, task))

        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] < 0.28:
            return None, [task for _, task in scored[:3]]
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.06:
            return None, [task for _, task in scored[:3]]
        return scored[0][1], []

    # ─────────── 核心功能逻辑按钮响应 ───────────

    def save_env(self):
        """保存 API 配置到本地环境文件"""
        key = self.var_api_key.get().strip()
        base = self.var_base_url.get().strip()
        model = self.var_model.get().strip()
        if not key:
            messagebox.showerror("API Key 为空", "API Key 字段不可为空！")
            return

        env_path = config.PROJECT_ROOT / ".env"
        content = (
            "# 由 GUI 自动生成，可手动编辑\n"
            f"OPENAI_API_KEY={key}\n"
            f"OPENAI_BASE_URL={base}\n"
            f"OPENAI_MODEL={model}\n"
            f"BOSS_WHISPER_MODEL={config.AUDIO_TRANSCRIPTION_MODEL}\n"
            f"BOSS_WHISPER_DEVICE={config.AUDIO_TRANSCRIPTION_DEVICE}\n"
            f"BOSS_WHISPER_COMPUTE_TYPE={config.AUDIO_TRANSCRIPTION_COMPUTE_TYPE}\n"
            f"BOSS_WHISPER_LANGUAGE={config.AUDIO_TRANSCRIPTION_LANGUAGE}\n"
            f"BOSS_SPEAKER_ROLE={self.var_speaker_role.get().strip() or '老板'}\n"
        )
        env_path.write_text(content, encoding="utf-8")
        self._sync_runtime_config()
        self._refresh_readiness()

        self._log(f"✅ 配置文件已保存至：{env_path}")
        messagebox.showinfo("保存成功", f"配置已保存至：\n{env_path}")

    def pick_input(self):
        path = filedialog.askopenfilename(
            title="选择语音或转写文件",
            filetypes=[
                ("支持的输入文件", "*.xlsx *.mp3 *.wav *.m4a"),
                ("Excel 转写稿", "*.xlsx"),
                ("音频文件", "*.mp3 *.wav *.m4a"),
                ("所有文件", "*.*"),
            ],
            initialdir=str(config.PROJECT_ROOT / "input"),
        )
        if path:
            self.var_input.set(path)
            os.environ["BOSS_INPUT_PATH"] = path
            config.INPUT_PATH = Path(path)
            config.WORKBOOK_PATH = config.INPUT_PATH
            self._refresh_readiness()

    def open_output_dir(self):
        path = str(config.OUTPUT_DIR)
        os.startfile(path) if os.name == "nt" else webbrowser.open(f"file://{path}")

    # ── 后台任务 ──

    def run_parse(self):
        if not (self._check_api_key() and self._check_input()):
            return

        def task():
            print("=" * 60)
            print("📢 解析语音 → 结构化任务")
            print("=" * 60)
            reader = InputReader(
                self.var_input.get(),
                speaker_role=self.var_speaker_role.get().strip(),
            )
            raw_text = reader.read()
            print(f"📄 读取原始文本字数: {len(raw_text)} 字\n")

            parser = TaskParser()
            instruction = parser.parse(raw_text, reader.segments)

            tracker = ProgressTracker()
            tracker.save_tasks(instruction, new_project=True)
            print(f"\n✅ 解析成功。提取出 {len(instruction.tasks)} 个核心任务：")
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
            print(f"✅ 通用 SOP 模板已生成成功：{md_path}")

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
            print(f"✅ 本地 Excel 任务大表导出成功：{path}")

        self._run_bg("导出 Excel", task)

    def run_dashboard(self):
        loaded = self._load_instruction_or_warn()
        if not loaded:
            return
        _, instruction = loaded
        try:
            path = generate_dashboard(instruction)
            self._log(f"✅ 可视化看板更新成功：{path}")
            webbrowser.open(str(path))
        except Exception as e:
            messagebox.showerror("更新看板失败", str(e))

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
            report = generator.generate(instruction, tracker.history)
            print(f"✅ 复盘总结生成成功，已写入：{config.RETROSPECTIVE_MD}")

        self._run_bg("生成复盘", task)

    def run_chat_command(self):
        command = self.var_chat.get().strip()
        if not command:
            messagebox.showinfo("指示为空", "请输入自然语言，例如：'T001 完成 100%' 或 '策划任务完成了'")
            return
        loaded = self._load_instruction_or_warn()
        if not loaded:
            return
        if not self._check_api_key():
            return

        self.var_chat.set("")

        def task():
            print("=" * 60)
            print("对话交互状态更新（LLM 意图理解）")
            print("=" * 60)
            print(f"输入指令：{command}")

            tracker = ProgressTracker()
            instruction = tracker.load_tasks()
            if not instruction:
                print("无法加载已结构化的任务数据库")
                return

            try:
                parser = ChatIntentParser()
                intent = parser.parse(command, instruction)
            except Exception as e:
                print(f"意图解析失败：{e}")
                print("可改用更明确的说法，例如：'T003 进度 60%'、'小红书任务完成'")
                return

            print(f"意图：{intent.intent.value} | 置信度：{intent.confidence:.2f}")
            if intent.task_query:
                print(f"任务线索：{intent.task_query}")

            if intent.intent == ChatIntentType.UNKNOWN:
                print(intent.clarify_question or "没有听懂这条指令。")
                return

            if intent.intent == ChatIntentType.CLARIFY or intent.need_clarification:
                print(intent.clarify_question or "需要你补充更具体的任务信息。")
                if intent.candidate_task_ids:
                    task_map = {t.id: t for t in instruction.tasks}
                    print("候选任务：")
                    for tid in intent.candidate_task_ids:
                        t = task_map.get(tid)
                        if t:
                            print(f"  - [{t.id}] {t.title}（{t.status.value} / {t.progress}%）")
                return

            if not intent.task_id:
                print("未能确定任务编号，请带上如 T001 的编号再试。")
                return

            # 进行中时避免把进度往回调
            progress = intent.progress
            status_value = intent.status.value if intent.status else None
            target = next((t for t in instruction.tasks if t.id == intent.task_id), None)
            if target and status_value == TaskStatus.IN_PROGRESS.value and progress is not None:
                progress = max(progress, target.progress)

            updated = tracker.update_task(
                task_id=intent.task_id,
                new_status=status_value,
                new_progress=progress,
                note=intent.note or f"对话修改：{command}",
                new_assignee=intent.assignee,
                new_deadline=intent.deadline,
            )
            if not updated:
                return

            fresh = tracker.load_tasks()
            if fresh:
                LocalTableExporter().export(fresh)
                generate_dashboard(fresh)
                print(f"已成功更新任务：[{updated.id}] {updated.title}")
                print(f"状态：{updated.status.value}，进度：{updated.progress}%")
                if intent.assignee:
                    print(f"负责人：{updated.assignee}")
                if intent.deadline:
                    print(f"截止日期：{updated.deadline}")
                print("已自动刷新 Excel 大表与网页看板")

        self._run_bg("对话执行", task)

    def run_all(self):
        if not (self._check_api_key() and self._check_input()):
            return

        def task():
            print("🚀 " + "=" * 56)
            print("   开始运行智能任务全流程处理")
            print("🚀 " + "=" * 56 + "\n")

            # 1. 解析
            print("─── 步骤 1/4: 调用大模型提取结构化任务 ───")
            reader = InputReader(
                self.var_input.get(),
                speaker_role=self.var_speaker_role.get().strip(),
            )
            raw_text = reader.read()
            parser = TaskParser()
            instruction = parser.parse(raw_text, reader.segments)
            tracker = ProgressTracker()
            tracker.save_tasks(instruction, new_project=True)
            print(f"✅ 解析出 {len(instruction.tasks)} 个核心任务\n")

            # 2. SOP
            print("─── 步骤 2/4: 构建标准化 SOP 流程 ───")
            sop_gen = SOPGenerator()
            sop = sop_gen.generate(instruction)
            md_path = sop_gen.save_as_markdown(sop)
            print(f"✅ SOP 生成成功：{md_path}\n")

            # 3. Excel
            print("─── 步骤 3/4: 同步数据导出 Excel 大表 ───")
            xlsx = LocalTableExporter().export(instruction)
            print(f"✅ Excel 导出成功：{xlsx}\n")

            # 4. 看板
            print("─── 步骤 4/4: 构建高颜值可视化网页看板 ───")
            html_path = generate_dashboard(instruction)
            print(f"✅ 看板构建成功：{html_path}\n")

            print("🎉 一键流水线处理已全部圆满完成！")
            self.root.after(0, lambda: webbrowser.open(str(html_path)))

        self._run_bg("一键全流程", task)


def main():
    root = ctk.CTk()
    BossTaskGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
