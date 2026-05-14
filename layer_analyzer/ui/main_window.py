"""
Главное окно приложения.
Собирает все виджеты в единый layout и управляет потоком анализа.
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QPushButton, QProgressBar, QLabel,
    QStatusBar, QFileDialog, QMessageBox,
    QDoubleSpinBox, QCheckBox, QStackedWidget,
)
from PyQt6.QtCore import Qt

from config import APP_TITLE, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT, OUTPUT_DIR
from models.analysis_report import AnalysisReport
from .file_selector import FileSelector
from .preview_panel import PreviewPanel
from .gallery_panel import GalleryPanel
from .results_panel import ResultsPanel
from .group_analysis_dialog import GroupAnalysisDialog
from .scale_calibration_dialog import ScaleCalibrationDialog
from .worker import AnalysisWorker
from .wrap_button import WrapButton


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self._worker: AnalysisWorker | None = None
        self._reports: dict[Path, AnalysisReport] = {}
        self._manual_crop_regions: dict[Path, tuple[int, int, int, int]] = {}
        self._setup_ui()
        self._connect_signals()

    # ── Построение UI ─────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)
        root.setSpacing(6)

        # ── Основной сплиттер ─────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая панель: выбор файлов
        self._file_selector = FileSelector()
        selector_width = self._file_selector.recommended_panel_width()
        self._file_selector.setFixedWidth(selector_width)
        splitter.addWidget(self._file_selector)

        # Центр: предпросмотр
        self._center_stack = QStackedWidget()
        self._preview = PreviewPanel()
        self._gallery = GalleryPanel()
        self._center_stack.addWidget(self._preview)
        self._center_stack.addWidget(self._gallery)
        splitter.addWidget(self._center_stack)

        # Правая панель: результаты
        self._results = ResultsPanel()
        self._results.setMinimumWidth(620)
        splitter.addWidget(self._results)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)

        root.addWidget(splitter, stretch=1)

        # ── Нижняя панель: прогресс + кнопки ─────────────────────────────────
        bottom = QHBoxLayout()

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        bottom.addWidget(self._progress_bar, stretch=1)

        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet("color: gray; font-size: 11px;")
        bottom.addWidget(self._progress_label)

        bottom.addStretch()

        # Поле ввода масштаба
        scale_label = QLabel("Масштаб (мкм/пкс):")
        scale_label.setStyleSheet("font-size: 12px;")
        bottom.addWidget(scale_label)

        self._scale_input = QDoubleSpinBox()
        self._scale_input.setRange(0.0001, 100.0)
        self._scale_input.setDecimals(4)
        self._scale_input.setValue(0.1)
        self._scale_input.setSingleStep(0.01)
        self._scale_input.setFixedWidth(100)
        self._scale_input.setToolTip(
            "Масштаб: сколько микрометров в одном пикселе.\n"
            "Например: если линейка = 10 мкм и занимает 100 пкс, введите 0.1.\n"
            "Можно вычислить кнопкой «📐 Калибровка»."
        )
        bottom.addWidget(self._scale_input)

        self._btn_calibrate = WrapButton("📐 Калибровка")
        self._btn_calibrate.setToolTip(
            "Вычислить масштаб по двум точкам на масштабной линейке метаданных.\n"
            "Применяется ко всей серии загруженных изображений."
        )
        self._btn_calibrate.setMinimumHeight(40)
        self._btn_calibrate.setStyleSheet("font-size: 12px; padding: 2px 8px;")
        self._btn_calibrate.setEnabled(False)
        bottom.addWidget(self._btn_calibrate)

        self._auto_crop_checkbox = QCheckBox("Автоматическая обрезка")
        self._auto_crop_checkbox.setChecked(True)
        self._auto_crop_checkbox.setToolTip(
            "Если выключено, перед запуском анализа нужно вручную выбрать область "
            "для каждого изображения."
        )
        bottom.addWidget(self._auto_crop_checkbox)

        self._btn_save = WrapButton("💾 Сохранить результаты")
        self._btn_save.setEnabled(False)
        self._btn_save.setMinimumHeight(40)
        self._btn_save.setStyleSheet("font-size: 12px; padding: 2px 2px;")
        bottom.addWidget(self._btn_save)

        self._btn_cancel = WrapButton("✕ Отмена")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.setMinimumHeight(40)
        self._btn_cancel.setStyleSheet("font-size: 12px; padding: 2px 2px;")
        bottom.addWidget(self._btn_cancel)

        self._btn_run = WrapButton("▶ Запустить анализ")
        self._btn_run.setEnabled(False)
        self._btn_run.setMinimumHeight(42)
        self._btn_run.setStyleSheet(
            "QPushButton { background: #2a6cba; color: white; font-size: 14px; min-height: 32px; padding: 6px 18px; "
            "border-radius: 4px; font-weight: bold; } "
            "QPushButton:hover { background: #3480d4; } "
            "QPushButton:disabled { background: #d8dce4; color: #7a828e; }"
        )
        bottom.addWidget(self._btn_run)

        root.addLayout(bottom)

        # ── Статусная строка ──────────────────────────────────────────────────
        self.setStatusBar(QStatusBar())

    # ── Сигналы ───────────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._file_selector.files_changed.connect(self._on_files_changed)
        self._file_selector._list.currentRowChanged.connect(self._on_list_selection)
        self._file_selector.group_analysis_requested.connect(self._on_group_analysis_requested)
        self._auto_crop_checkbox.toggled.connect(self._on_auto_crop_toggled)
        self._preview.crop_changed.connect(self._on_preview_crop_changed)
        self._btn_run.clicked.connect(self._start_analysis)
        self._btn_cancel.clicked.connect(self._cancel_analysis)
        self._btn_save.clicked.connect(self._save_results)
        self._btn_calibrate.clicked.connect(self._open_calibration_dialog)

    # ── Слоты ─────────────────────────────────────────────────────────────────

    def _on_files_changed(self, files: list[Path]) -> None:
        self._btn_run.setEnabled(len(files) > 0)
        self._btn_calibrate.setEnabled(len(files) > 0)
        if not files:
            self._manual_crop_regions.clear()
            self._preview.clear()
            self._gallery.clear()
            self._center_stack.setCurrentWidget(self._preview)
            self._results.clear()
            return

        # Поддерживаем актуальность map ручной обрезки только для выбранных файлов.
        self._manual_crop_regions = {
            p: box for p, box in self._manual_crop_regions.items() if p in files
        }

        if self._file_selector.selected_file is None:
            self._file_selector._list.setCurrentRow(0)
            return

        self._on_list_selection(self._file_selector._list.currentRow())

    def _on_list_selection(self, row: int) -> None:
        path = self._file_selector.selected_file
        if path is None:
            return
        report = self._reports.get(path)
        if report:
            if report.success:
                self._gallery.show_images(path, report)
                self._center_stack.setCurrentWidget(self._gallery)
                self._results.show_report(report)
            else:
                self._preview.show_file(
                    path,
                    report,
                    manual_crop_box=self._manual_crop_regions.get(path),
                )
                self._center_stack.setCurrentWidget(self._preview)
                self._results.show_error(report.error or "Неизвестная ошибка")
        else:
            self._preview.show_file(
                path,
                report,
                manual_crop_box=self._manual_crop_regions.get(path),
            )
            self._center_stack.setCurrentWidget(self._preview)

    def _on_auto_crop_toggled(self, checked: bool) -> None:
        self._preview.set_manual_crop_enabled(not checked)
        self._on_list_selection(self._file_selector._list.currentRow())

    def _open_calibration_dialog(self) -> None:
        """Калибровка масштаба по линейке метаданных одного изображения.
        Вычисленное значение применяется ко всей серии (общее поле масштаба)."""
        files = self._file_selector.files
        if not files:
            return

        target = self._file_selector.selected_file or files[0]
        dlg = ScaleCalibrationDialog(
            target,
            current_scale=self._scale_input.value(),
            parent=self,
        )
        if dlg.exec() != ScaleCalibrationDialog.DialogCode.Accepted:
            return

        new_scale = dlg.computed_scale
        if new_scale is None or new_scale <= 0:
            return

        self._scale_input.setValue(float(new_scale))
        self.statusBar().showMessage(
            f"Масштаб откалиброван по {target.name}: {new_scale:.5f} мкм/пкс "
            f"(применяется ко всем {len(files)} изображениям)"
        )

    def _on_group_analysis_requested(self, files: list[Path]) -> None:
        """Сводный анализ по выбранным чекбоксами файлам."""
        if not files:
            return

        # Собираем уже посчитанные отчёты и фиксируем недостающие.
        ready: list[AnalysisReport] = []
        missing: list[Path] = []
        for path in files:
            r = self._reports.get(path)
            if r is None or not r.success:
                missing.append(path)
            else:
                ready.append(r)

        if missing:
            names = "\n".join(f"- {p.name}" for p in missing)
            QMessageBox.warning(
                self,
                "Не все файлы проанализированы",
                "Сначала выполните анализ для всех файлов в группе. "
                "Не хватает результатов по:\n"
                f"{names}",
            )
            return

        dlg = GroupAnalysisDialog(ready, parent=self)
        dlg.exec()

    def _on_preview_crop_changed(self, crop_box: tuple[int, int, int, int] | None) -> None:
        if self._auto_crop_checkbox.isChecked():
            return
        path = self._file_selector.selected_file
        if path is None or crop_box is None:
            return
        self._manual_crop_regions[path] = crop_box

    def _start_analysis(self) -> None:
        files = self._file_selector.files
        if not files:
            return

        auto_crop_enabled = self._auto_crop_checkbox.isChecked()
        manual_regions: dict[Path, tuple[int, int, int, int]] = {}
        if not auto_crop_enabled:
            manual_regions = {
                path: box
                for path, box in self._manual_crop_regions.items()
                if path in files
            }
            missing = [p for p in files if p not in manual_regions]
            if missing:
                names = "\n".join(f"- {p.name}" for p in missing)
                QMessageBox.warning(
                    self,
                    "Ручная обрезка не задана",
                    "Для запуска анализа задайте область обрезки в окне предпросмотра "
                    "для файлов:\n"
                    f"{names}",
                )
                self.statusBar().showMessage("Анализ отменён: не для всех файлов задана ручная обрезка")
                return
            self._manual_crop_regions = manual_regions
        else:
            self._manual_crop_regions.clear()

        self._reports.clear()
        self._center_stack.setCurrentWidget(self._preview)
        self._gallery.clear()
        self._btn_run.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._btn_save.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)

        self._worker = AnalysisWorker(
            files,
            self._scale_input.value(),
            auto_crop=auto_crop_enabled,
            manual_crop_regions=self._manual_crop_regions,
        )
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.result.connect(self._on_worker_result)
        self._worker.finished_all.connect(self._on_analysis_done)
        self._worker.start()

    def _cancel_analysis(self) -> None:
        if self._worker:
            self._worker.cancel()
        self._btn_cancel.setEnabled(False)
        self._progress_label.setText("Отмена...")

    def _on_worker_progress(self, file_idx: int, total: int, msg: str, pct: int) -> None:
        overall = int((file_idx / total) * 100 + pct / total)
        self._progress_bar.setValue(overall)
        path = self._file_selector.files[file_idx]
        self._progress_label.setText(f"[{file_idx + 1}/{total}] {path.name} — {msg}")
        self.statusBar().showMessage(f"{path.name}: {msg}")

    def _on_worker_result(self, report: AnalysisReport) -> None:
        self._reports[report.image_path] = report
        # Обновить предпросмотр если этот файл сейчас выделен
        if self._file_selector.selected_file == report.image_path:
            if report.success:
                self._gallery.show_images(report.image_path, report)
                self._center_stack.setCurrentWidget(self._gallery)
                self._results.show_report(report)
            else:
                self._preview.show_file(report.image_path, report)
                self._center_stack.setCurrentWidget(self._preview)
                self._results.show_error(report.error or "")

    def _on_analysis_done(self) -> None:
        # После анализа возвращаемся к автообрезке и скрываем рамку ручной обрезки.
        self._manual_crop_regions.clear()
        self._auto_crop_checkbox.setChecked(True)
        self._preview.set_manual_crop_enabled(False)
        self._on_list_selection(self._file_selector._list.currentRow())

        self._btn_run.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._btn_save.setEnabled(bool(self._reports))
        self._progress_bar.setValue(100)
        self._progress_label.setText(
            f"Готово. Обработано файлов: {len(self._reports)}"
        )
        ok = sum(1 for r in self._reports.values() if r.success)
        err = len(self._reports) - ok
        self.statusBar().showMessage(
            f"Анализ завершён: {ok} успешно, {err} с ошибками"
        )

    def _save_results(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Выбрать папку для сохранения")
        if not folder:
            return
        out = Path(folder)
        ts = datetime.now().strftime("%Y-%m-%d %H-%M")
        run_dir = out / ts
        run_dir.mkdir(parents=True, exist_ok=True)

        self._save_logs(run_dir)
        self._save_plots(run_dir)

        QMessageBox.information(
            self, "Сохранено", f"Результаты сохранены в:\n{run_dir}"
        )

    def _save_logs(self, run_dir: Path) -> None:
        log_path = run_dir / "logs.txt"
        with log_path.open("w", encoding="utf-8") as f:
            for report in self._reports.values():
                f.write(report.to_log_text())

    def _save_plots(self, run_dir: Path) -> None:
        """Сохраняет все карточки галереи для каждого изображения."""

        for report in self._reports.values():
            if not report.success:
                continue
            img_dir = run_dir / report.image_name
            img_dir.mkdir(exist_ok=True)

            pixmaps = self._gallery.build_export_pixmaps(report.image_path, report)
            for key, pixmap in pixmaps.items():
                pixmap.save(str(img_dir / f"{key}.png"), "PNG")