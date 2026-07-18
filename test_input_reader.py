import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import openpyxl

from boss_task_agent import AudioTranscriber, InputReader


class InputReaderTests(unittest.TestCase):
    def test_reads_xlsx_with_existing_excel_reader(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meeting.xlsx"
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(["老板说", "明天提交方案"])
            workbook.save(path)

            reader = InputReader(path, speaker_role="总经理")
            self.assertEqual(
                reader.read(),
                "[S0001][职位:总经理][来源:meeting.xlsx] 老板说\n"
                "[S0002][职位:总经理][来源:meeting.xlsx] 明天提交方案",
            )
            self.assertEqual(len(reader.segments), 2)
            self.assertEqual(reader.segments[0].speaker_role, "总经理")

    def test_dispatches_supported_audio_to_transcriber(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meeting.m4a"
            path.touch()

            with patch.object(AudioTranscriber, "read", return_value="转写后的会议内容") as read:
                self.assertEqual(InputReader(path).read(), "转写后的会议内容")
                read.assert_called_once_with()

    def test_audio_transcriber_joins_whisper_segments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meeting.wav"
            path.touch()
            segments = [
                SimpleNamespace(text=" 老板说，明天提交方案。 ", start=1.2, end=4.5),
                SimpleNamespace(text=" 小李负责。 ", start=4.5, end=6.0),
            ]
            info = SimpleNamespace(language="zh")

            with patch("faster_whisper.WhisperModel") as model_class:
                model_class.return_value.transcribe.return_value = (iter(segments), info)

                transcriber = AudioTranscriber(path, speaker_role="项目总监")
                transcript = transcriber.read()

            self.assertEqual(
                transcript,
                "[S0001][职位:项目总监][时间:00:01.200-00:04.500][来源:meeting.wav] "
                "老板说，明天提交方案。\n"
                "[S0002][职位:项目总监][时间:00:04.500-00:06.000][来源:meeting.wav] "
                "小李负责。",
            )
            self.assertEqual(transcriber.segments[0].start_seconds, 1.2)
            model_class.return_value.transcribe.assert_called_once()

    def test_rejects_unsupported_input_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "meeting.txt"
            path.write_text("text", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "不支持的输入格式"):
                InputReader(path).read()

    def test_reports_missing_input_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.wav"

            with self.assertRaisesRegex(FileNotFoundError, "输入文件不存在"):
                InputReader(path).read()


if __name__ == "__main__":
    unittest.main()
