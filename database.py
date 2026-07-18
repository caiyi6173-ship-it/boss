"""SQLite 持久化层。

SQLite 是任务和进度的主存储。旧版 JSON 仅在数据库首次初始化且数据库为空时
自动迁移，迁移成功后不会再被运行时写入。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from models import (
    Deliverable,
    EvidenceItem,
    ProjectOverview,
    SourceSegment,
    StructuredInstruction,
    Task,
    TaskProgressEntry,
)


SCHEMA_VERSION = 2


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SQLiteTaskStore:
    """负责项目、任务、交付物、依赖和进度事件的事务性存储。"""

    def __init__(
        self,
        db_path: Path | str,
        legacy_tasks_path: Path | str | None = None,
        legacy_history_path: Path | str | None = None,
        migrate_legacy: bool = True,
    ):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(
            str(self.path),
            timeout=30,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.execute("PRAGMA busy_timeout = 30000")
        self._create_schema()
        if migrate_legacy and legacy_tasks_path:
            self.migrate_legacy(
                Path(legacy_tasks_path),
                Path(legacy_history_path) if legacy_history_path else None,
            )

    def close(self) -> None:
        if getattr(self, "conn", None) is not None:
            self.conn.close()
            self.conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self) -> "SQLiteTaskStore":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _create_schema(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    background TEXT NOT NULL DEFAULT '',
                    objective TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT '',
                    overall_deadline TEXT,
                    key_stakeholders_json TEXT NOT NULL DEFAULT '[]',
                    raw_input TEXT NOT NULL DEFAULT '',
                    parsed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    task_rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    task_code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    assignee TEXT NOT NULL,
                    deadline TEXT,
                    status TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    progress INTEGER NOT NULL CHECK(progress >= 0 AND progress <= 100),
                    UNIQUE(project_id, task_code)
                );

                CREATE TABLE IF NOT EXISTS deliverables (
                    deliverable_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    task_code TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    format TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(project_id, task_code)
                        REFERENCES tasks(project_id, task_code) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_dependencies (
                    project_id TEXT NOT NULL,
                    task_code TEXT NOT NULL,
                    depends_on_code TEXT NOT NULL,
                    PRIMARY KEY(project_id, task_code, depends_on_code),
                    FOREIGN KEY(project_id, task_code)
                        REFERENCES tasks(project_id, task_code) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS source_segments (
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    segment_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_file TEXT NOT NULL,
                    speaker_role TEXT NOT NULL,
                    start_seconds REAL,
                    end_seconds REAL,
                    text TEXT NOT NULL,
                    PRIMARY KEY(project_id, segment_id)
                );

                CREATE TABLE IF NOT EXISTS project_evidence (
                    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    field TEXT NOT NULL,
                    source_segment_id TEXT NOT NULL,
                    source_quote TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                    FOREIGN KEY(project_id, source_segment_id)
                        REFERENCES source_segments(project_id, segment_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_evidence (
                    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    task_code TEXT NOT NULL,
                    field TEXT NOT NULL,
                    source_segment_id TEXT NOT NULL,
                    source_quote TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                    FOREIGN KEY(project_id, task_code)
                        REFERENCES tasks(project_id, task_code) ON DELETE CASCADE,
                    FOREIGN KEY(project_id, source_segment_id)
                        REFERENCES source_segments(project_id, segment_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    task_code TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    old_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    old_progress INTEGER NOT NULL,
                    new_progress INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_projects_active
                    ON projects(is_active, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tasks_project
                    ON tasks(project_id, task_rowid);
                CREATE INDEX IF NOT EXISTS idx_events_project
                    ON task_events(project_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_source_segments_project
                    ON source_segments(project_id, segment_id);
                CREATE INDEX IF NOT EXISTS idx_task_evidence_task
                    ON task_evidence(project_id, task_code, evidence_id);
                """
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def _project_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM projects").fetchone()
        return int(row["count"])

    def get_active_project_id(self) -> str | None:
        row = self.conn.execute(
            """
            SELECT project_id FROM projects
            ORDER BY is_active DESC, updated_at DESC, rowid DESC
            LIMIT 1
            """
        ).fetchone()
        return str(row["project_id"]) if row else None

    def _insert_instruction(
        self,
        instruction: StructuredInstruction,
        project_id: str,
        updated_at: str,
    ) -> None:
        overview = instruction.overview
        self.conn.execute(
            """
            INSERT INTO projects(
                project_id, project_name, background, objective, scope,
                overall_deadline, key_stakeholders_json, raw_input, parsed_at,
                created_at, updated_at, is_active
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                project_id,
                overview.project_name,
                overview.background,
                overview.objective,
                overview.scope,
                overview.overall_deadline,
                json.dumps(overview.key_stakeholders, ensure_ascii=False),
                instruction.raw_input,
                instruction.parsed_at,
                instruction.parsed_at,
                updated_at,
            ),
        )
        self._insert_source_segments(project_id, instruction.source_segments)
        self._insert_project_evidence(project_id, overview.evidence)
        self._insert_tasks(project_id, instruction)

    def _insert_source_segments(
        self,
        project_id: str,
        segments: list[SourceSegment],
    ) -> None:
        for segment in segments:
            self.conn.execute(
                """
                INSERT INTO source_segments(
                    project_id, segment_id, source_type, source_file, speaker_role,
                    start_seconds, end_seconds, text
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    segment.id,
                    segment.source_type,
                    segment.source_file,
                    segment.speaker_role,
                    segment.start_seconds,
                    segment.end_seconds,
                    segment.text,
                ),
            )

    def _insert_project_evidence(
        self,
        project_id: str,
        evidence: list[EvidenceItem],
    ) -> None:
        for item in evidence:
            self.conn.execute(
                """
                INSERT INTO project_evidence(
                    project_id, field, source_segment_id, source_quote, confidence
                ) VALUES(?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    item.field.value,
                    item.source_segment_id,
                    item.source_quote,
                    item.confidence,
                ),
            )

    def _insert_tasks(self, project_id: str, instruction: StructuredInstruction) -> None:
        for task in instruction.tasks:
            self.conn.execute(
                """
                INSERT INTO tasks(
                    project_id, task_code, title, description, category, priority,
                    assignee, deadline, status, notes, created_at, updated_at, progress
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    task.id,
                    task.title,
                    task.description,
                    task.category.value,
                    task.priority.value,
                    task.assignee,
                    task.deadline,
                    task.status.value,
                    task.notes,
                    task.created_at,
                    task.updated_at,
                    task.progress,
                ),
            )
            for position, deliverable in enumerate(task.deliverables):
                self.conn.execute(
                    """
                    INSERT INTO deliverables(
                        project_id, task_code, position, name, format, description
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        task.id,
                        position,
                        deliverable.name,
                        deliverable.format,
                        deliverable.description,
                    ),
                )
            for dependency in task.dependencies:
                self.conn.execute(
                    """
                    INSERT INTO task_dependencies(project_id, task_code, depends_on_code)
                    VALUES(?, ?, ?)
                    """,
                    (project_id, task.id, dependency),
                )
            for item in task.evidence:
                self.conn.execute(
                    """
                    INSERT INTO task_evidence(
                        project_id, task_code, field, source_segment_id,
                        source_quote, confidence
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        task.id,
                        item.field.value,
                        item.source_segment_id,
                        item.source_quote,
                        item.confidence,
                    ),
                )

    def _replace_instruction(
        self,
        instruction: StructuredInstruction,
        project_id: str,
        updated_at: str,
    ) -> None:
        overview = instruction.overview
        self.conn.execute(
            """
            UPDATE projects SET
                project_name = ?, background = ?, objective = ?, scope = ?,
                overall_deadline = ?, key_stakeholders_json = ?, raw_input = ?,
                parsed_at = ?, updated_at = ?, is_active = 1
            WHERE project_id = ?
            """,
            (
                overview.project_name,
                overview.background,
                overview.objective,
                overview.scope,
                overview.overall_deadline,
                json.dumps(overview.key_stakeholders, ensure_ascii=False),
                instruction.raw_input,
                instruction.parsed_at,
                updated_at,
                project_id,
            ),
        )
        self.conn.execute("DELETE FROM project_evidence WHERE project_id = ?", (project_id,))
        self.conn.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
        self.conn.execute("DELETE FROM source_segments WHERE project_id = ?", (project_id,))
        self._insert_source_segments(project_id, instruction.source_segments)
        self._insert_project_evidence(project_id, overview.evidence)
        self._insert_tasks(project_id, instruction)

    def _insert_event(self, project_id: str, event: TaskProgressEntry) -> None:
        self.conn.execute(
            """
            INSERT INTO task_events(
                project_id, task_code, timestamp, old_status, new_status,
                old_progress, new_progress, note
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                event.task_id,
                event.timestamp,
                event.old_status.value,
                event.new_status.value,
                event.old_progress,
                event.new_progress,
                event.note,
            ),
        )

    def save_instruction(
        self,
        instruction: StructuredInstruction,
        project_id: str | None = None,
        new_project: bool = False,
        event: TaskProgressEntry | None = None,
    ) -> str:
        """保存项目快照，可选择创建新项目并将任务变更与事件放在同一事务中。"""
        use_existing = (
            not new_project
            and project_id
            and self.conn.execute(
                "SELECT 1 FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        )
        target_id = str(project_id) if use_existing else uuid.uuid4().hex
        updated_at = _now()

        with self.conn:
            self.conn.execute("UPDATE projects SET is_active = 0")
            if use_existing:
                self._replace_instruction(instruction, target_id, updated_at)
            else:
                self._insert_instruction(instruction, target_id, updated_at)
            if event:
                self._insert_event(target_id, event)
        return target_id

    def load_active_instruction(self) -> tuple[StructuredInstruction, str] | None:
        project_id = self.get_active_project_id()
        if not project_id:
            return None
        project = self.conn.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if not project:
            return None

        project_evidence_rows = self.conn.execute(
            """
            SELECT field, source_segment_id, source_quote, confidence
            FROM project_evidence WHERE project_id = ? ORDER BY evidence_id
            """,
            (project_id,),
        ).fetchall()
        overview = ProjectOverview(
            project_name=project["project_name"],
            background=project["background"],
            objective=project["objective"],
            scope=project["scope"],
            overall_deadline=project["overall_deadline"],
            key_stakeholders=json.loads(project["key_stakeholders_json"] or "[]"),
            evidence=[EvidenceItem(**dict(item)) for item in project_evidence_rows],
        )
        source_rows = self.conn.execute(
            """
            SELECT segment_id AS id, source_type, source_file, speaker_role,
                   start_seconds, end_seconds, text
            FROM source_segments WHERE project_id = ? ORDER BY segment_id
            """,
            (project_id,),
        ).fetchall()
        tasks: list[Task] = []
        task_rows = self.conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY task_rowid", (project_id,)
        ).fetchall()
        for row in task_rows:
            deliverables = self.conn.execute(
                """
                SELECT name, format, description FROM deliverables
                WHERE project_id = ? AND task_code = ? ORDER BY position
                """,
                (project_id, row["task_code"]),
            ).fetchall()
            dependencies = self.conn.execute(
                """
                SELECT depends_on_code FROM task_dependencies
                WHERE project_id = ? AND task_code = ? ORDER BY depends_on_code
                """,
                (project_id, row["task_code"]),
            ).fetchall()
            evidence_rows = self.conn.execute(
                """
                SELECT field, source_segment_id, source_quote, confidence
                FROM task_evidence
                WHERE project_id = ? AND task_code = ? ORDER BY evidence_id
                """,
                (project_id, row["task_code"]),
            ).fetchall()
            tasks.append(
                Task(
                    id=row["task_code"],
                    title=row["title"],
                    description=row["description"],
                    category=row["category"],
                    priority=row["priority"],
                    assignee=row["assignee"],
                    deadline=row["deadline"],
                    deliverables=[Deliverable(**dict(item)) for item in deliverables],
                    status=row["status"],
                    dependencies=[item["depends_on_code"] for item in dependencies],
                    notes=row["notes"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    progress=row["progress"],
                    evidence=[EvidenceItem(**dict(item)) for item in evidence_rows],
                )
            )
        return (
            StructuredInstruction(
                overview=overview,
                tasks=tasks,
                raw_input=project["raw_input"],
                parsed_at=project["parsed_at"],
                source_segments=[SourceSegment(**dict(item)) for item in source_rows],
            ),
            project_id,
        )

    def load_history(self, project_id: str | None = None) -> list[TaskProgressEntry]:
        project_id = project_id or self.get_active_project_id()
        if not project_id:
            return []
        rows = self.conn.execute(
            """
            SELECT task_code, timestamp, old_status, new_status,
                   old_progress, new_progress, note
            FROM task_events WHERE project_id = ? ORDER BY event_id
            """,
            (project_id,),
        ).fetchall()
        return [
            TaskProgressEntry(
                task_id=row["task_code"],
                timestamp=row["timestamp"],
                old_status=row["old_status"],
                new_status=row["new_status"],
                old_progress=row["old_progress"],
                new_progress=row["new_progress"],
                note=row["note"],
            )
            for row in rows
        ]

    def migrate_legacy(
        self,
        tasks_path: Path,
        history_path: Path | None = None,
    ) -> bool:
        """将旧 JSON 导入空数据库；成功后保留原文件作为备份。"""
        if self._project_count() > 0 or not tasks_path.exists():
            return False

        try:
            instruction = StructuredInstruction(
                **json.loads(tasks_path.read_text(encoding="utf-8"))
            )
            history_data = []
            if history_path and history_path.exists():
                history_data = json.loads(history_path.read_text(encoding="utf-8"))
            history = [TaskProgressEntry(**item) for item in history_data]
        except Exception as exc:
            raise RuntimeError(f"旧 JSON 迁移失败，原文件未修改：{exc}") from exc

        project_id = uuid.uuid4().hex
        with self.conn:
            self.conn.execute("UPDATE projects SET is_active = 0")
            self._insert_instruction(instruction, project_id, _now())
            for event in history:
                self._insert_event(project_id, event)
            self.conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('legacy_migrated', ?)",
                (datetime.now().isoformat(timespec="seconds"),),
            )
        return True
