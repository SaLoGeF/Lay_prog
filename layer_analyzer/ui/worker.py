"""
Фоновый поток анализа.
QThread отделяет тяжёлые вычисления от UI-потока —
интерфейс остаётся отзывчивым во время обработки.
"""

from __future__ import annotations
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.analyzer import Analyzer
from models.analysis_report import AnalysisReport


class AnalysisWorker(QThread):
    """
    Сигналы:
        progress(file_index, total, message, percent)  — обновление прогресса
        result(report)                                  — один файл обработан
        finished_all()                                  — все файлы обработаны
    """

    progress = pyqtSignal(int, int, str, int)   # (file_idx, total, msg, pct)
    result = pyqtSignal(object)                  # AnalysisReport
    finished_all = pyqtSignal()

    def __init__(
        self,
        files: list[Path],
        scale_um_per_px: float,
        auto_crop: bool,
        manual_crop_regions: dict[Path, tuple[int, int, int, int]] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._files = files
        self._scale = scale_um_per_px
        self._auto_crop = auto_crop
        self._manual_crop_regions = manual_crop_regions or {}
        self._cancelled = False
        self._analyzer = Analyzer()

    def cancel(self) -> None:
        self._cancelled = True

    # ── QThread.run ───────────────────────────────────────────────────────────

    def run(self) -> None:
        total = len(self._files)
        for idx, path in enumerate(self._files):
            if self._cancelled:
                break

            def on_progress(msg: str, pct: int, _idx=idx, _total=total) -> None:
                self.progress.emit(_idx, _total, msg, pct)

            report: AnalysisReport = self._analyzer.run(
                path,
                self._scale,
                progress_cb=on_progress,
                auto_crop=self._auto_crop,
                manual_crop_box=self._manual_crop_regions.get(path),
            )
            self.result.emit(report)

        self.finished_all.emit()