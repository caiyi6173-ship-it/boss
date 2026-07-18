import json
import tempfile
import unittest
from pathlib import Path

from boss_task_agent import ProgressTracker
from database import SQLiteTaskStore
from models import (
    Deliverable,
    EvidenceField,
    EvidenceItem,
    ProjectOverview,
    StructuredInstruction,
    SourceSegment,
    Task,
    TaskCategory,
    TaskPriority,
    TaskProgressEntry,
    TaskStatus,
)


def make_instruction(name: str = "测试项目") -> StructuredInstruction:
    return StructuredInstruction(
        overview=ProjectOverview(
            project_name=name,
            background="测试背景",
            objective="按时完成交付",
            scope="策划与执行",
            overall_deadline="2026-08-01",
            key_stakeholders=["老板", "执行团队"],
        ),
        tasks=[
            Task(
                id="T001",
                title="编写方案",
                description="输出活动方案",
                category=TaskCategory.PLANNING,
                priority=TaskPriority.P0,
                assignee="小李",
                deadline="2026-07-25",
                deliverables=[
                    Deliverable(name="策划方案", format="PDF", description="可评审版本")
                ],
            ),
            Task(
                id="T002",
                title="执行活动",
                description="按方案完成活动",
                category=TaskCategory.EXECUTION,
                priority=TaskPriority.P1,
                assignee="执行团队",
                deadline="2026-08-01",
                deliverables=[Deliverable(name="执行记录", format="Excel")],
                dependencies=["T001"],
            ),
        ],
        raw_input="老板要求先出方案，再执行活动。",
        parsed_at="2026-07-18 10:00:00",
    )


def make_evidenced_instruction() -> StructuredInstruction:
    source_text = "老板要求8月1日前完成，先出方案，再执行活动，小李负责方案并提交PDF。"
    segment = SourceSegment(
        id="S0001",
        source_type="audio",
        source_file="meeting.m4a",
        speaker_role="总经理",
        start_seconds=1.2,
        end_seconds=8.4,
        text=source_text,
    )
    evidence = lambda field, quote, confidence=0.95: EvidenceItem(
        field=field,
        source_segment_id="S0001",
        source_quote=quote,
        confidence=confidence,
    )
    return StructuredInstruction(
        overview=ProjectOverview(
            project_name="有证据项目",
            objective="完成方案与活动执行",
            overall_deadline="2026-08-01",
            evidence=[
                evidence(EvidenceField.PROJECT_OBJECTIVE, "先出方案，再执行活动"),
                evidence(EvidenceField.PROJECT_DEADLINE, "8月1日前完成"),
            ],
        ),
        tasks=[
            Task(
                id="T001",
                title="编写方案",
                description="编写并提交活动方案",
                category=TaskCategory.PLANNING,
                priority=TaskPriority.P0,
                assignee="小李",
                deadline="2026-08-01",
                deliverables=[Deliverable(name="方案", format="PDF")],
                evidence=[
                    evidence(EvidenceField.TASK, "先出方案"),
                    evidence(EvidenceField.ASSIGNEE, "小李负责方案"),
                    evidence(EvidenceField.DEADLINE, "8月1日前完成"),
                    evidence(EvidenceField.DELIVERABLE, "提交PDF"),
                ],
            ),
            Task(
                id="T002",
                title="执行活动",
                description="方案完成后执行活动",
                category=TaskCategory.EXECUTION,
                deadline="2026-08-01",
                deliverables=[Deliverable(name="活动执行结果")],
                dependencies=["T001"],
                evidence=[
                    evidence(EvidenceField.TASK, "再执行活动"),
                    evidence(EvidenceField.DEADLINE, "8月1日前完成"),
                    evidence(EvidenceField.DELIVERABLE, "执行活动"),
                    evidence(EvidenceField.DEPENDENCY, "先出方案，再执行活动"),
                ],
            ),
        ],
        raw_input=(
            "[S0001][职位:总经理][时间:00:01.200-00:08.400]"
            "[来源:meeting.m4a] " + source_text
        ),
        parsed_at="2026-07-18 11:00:00",
        source_segments=[segment],
    )


class SQLiteTaskStoreTests(unittest.TestCase):
    def test_instruction_round_trip_preserves_normalized_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteTaskStore(Path(temp_dir) / "tasks.db", migrate_legacy=False)
            original = make_evidenced_instruction()

            project_id = store.save_instruction(original, new_project=True)
            loaded, loaded_id = store.load_active_instruction()

            self.assertEqual(project_id, loaded_id)
            self.assertEqual(
                loaded.model_dump(mode="json"),
                original.model_dump(mode="json"),
            )
            self.assertEqual(
                store.conn.execute("PRAGMA journal_mode").fetchone()[0].lower(),
                "wal",
            )
            self.assertEqual(
                store.conn.execute("SELECT COUNT(*) FROM source_segments").fetchone()[0],
                1,
            )
            self.assertEqual(
                store.conn.execute("SELECT COUNT(*) FROM task_evidence").fetchone()[0],
                8,
            )
            store.close()

    def test_task_update_and_event_are_saved_together(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteTaskStore(Path(temp_dir) / "tasks.db", migrate_legacy=False)
            tracker = ProgressTracker(store=store, migrate_legacy=False)
            tracker.save_tasks(make_evidenced_instruction(), new_project=True)

            updated = tracker.update_task(
                "T001",
                new_status="进行中",
                new_progress=60,
                note="方案初稿完成",
            )

            self.assertEqual(updated.progress, 60)
            self.assertEqual(tracker.load_tasks().tasks[0].status, TaskStatus.IN_PROGRESS)
            self.assertEqual(len(tracker.load_tasks().tasks[0].evidence), 4)
            self.assertEqual(len(tracker.history), 1)
            self.assertEqual(tracker.history[0].note, "方案初稿完成")
            store.close()

    def test_new_project_becomes_active_without_overwriting_previous_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteTaskStore(Path(temp_dir) / "tasks.db", migrate_legacy=False)
            first_id = store.save_instruction(make_instruction("项目一"), new_project=True)
            second_id = store.save_instruction(make_instruction("项目二"), new_project=True)

            loaded, active_id = store.load_active_instruction()

            self.assertNotEqual(first_id, second_id)
            self.assertEqual(active_id, second_id)
            self.assertEqual(loaded.overview.project_name, "项目二")
            count = store.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            self.assertEqual(count, 2)
            store.close()

    def test_legacy_json_migrates_once_and_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks_path = root / "structured_tasks.json"
            history_path = root / "progress_history.json"
            db_path = root / "tasks.db"
            instruction = make_instruction("旧项目")
            event = TaskProgressEntry(
                task_id="T001",
                old_status=TaskStatus.PENDING,
                new_status=TaskStatus.IN_PROGRESS,
                old_progress=0,
                new_progress=30,
                note="旧历史",
            )
            tasks_path.write_text(
                json.dumps(instruction.model_dump(mode="json"), ensure_ascii=False),
                encoding="utf-8",
            )
            history_path.write_text(
                json.dumps([event.model_dump(mode="json")], ensure_ascii=False),
                encoding="utf-8",
            )

            store = SQLiteTaskStore(db_path, tasks_path, history_path)
            store.close()
            reopened = SQLiteTaskStore(db_path, tasks_path, history_path)

            loaded, _ = reopened.load_active_instruction()
            self.assertEqual(loaded.overview.project_name, "旧项目")
            self.assertEqual(len(reopened.load_history()), 1)
            self.assertEqual(
                reopened.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
                1,
            )
            self.assertTrue(tasks_path.exists())
            self.assertTrue(history_path.exists())
            reopened.close()


if __name__ == "__main__":
    unittest.main()
