"""
Виджет выбора изображений.
Показывает список выбранных файлов с миниатюрами,
кнопки «Добавить» / «Удалить» / «Очистить».
"""

from __future__ import annotations
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem,
    QFileDialog, QLabel,
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, pyqtSignal

import skimage as ski
import numpy as np

from config import SUPPORTED_EXTENSIONS, THUMBNAIL_SIZE
from .wrap_button import WrapButton


class FileSelector(QWidget):
    """Emits `files_changed(list[Path])` whenever the selection changes."""

    files_changed = pyqtSignal(list)
    group_changed = pyqtSignal(list)          # список путей с включённым чекбоксом
    group_analysis_requested = pyqtSignal(list)  # запуск сводки по группе

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: list[Path] = []
        self._panel_width_hint = 320
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Заголовок
        title = QLabel("Изображения для анализа")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        # Список
        self._list = QListWidget()
        self._list.setIconSize(Qt.SizeHint.MinimumExpanding.value
                               if False else __import__('PyQt6.QtCore', fromlist=['QSize']).QSize(*THUMBNAIL_SIZE))
        self._list.setSpacing(2)
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list)

        # Кнопки
        btn_row = QHBoxLayout()
        self._btn_add = WrapButton("＋ Добавить файлы")
        self._btn_add_folder = WrapButton("📁 Папку")
        self._btn_remove = WrapButton("✕ Удалить")
        self._btn_clear = WrapButton("Очистить")
        self._btn_remove.setEnabled(False)

        button_style = "font-size: 12px; min-height: 38px; padding: 2px 2px;"
        self._btn_add.setStyleSheet(button_style)
        self._btn_add_folder.setStyleSheet(button_style)
        self._btn_remove.setStyleSheet(button_style)
        self._btn_clear.setStyleSheet(button_style)
        self._apply_uniform_button_size(btn_row)

        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_add_folder)
        btn_row.addWidget(self._btn_remove)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_clear)
        layout.addLayout(btn_row)

        # Счётчик
        self._count_label = QLabel("Файлов: 0")
        self._count_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._count_label)

        # ── Группа: выбор и кнопка сводного анализа ──────────────────────
        group_row = QHBoxLayout()
        group_row.setContentsMargins(0, 4, 0, 0)

        self._btn_group_all = WrapButton("☑ Все в группу")
        self._btn_group_none = WrapButton("☐ Снять")
        self._btn_group_all.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self._btn_group_none.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        group_row.addWidget(self._btn_group_all)
        group_row.addWidget(self._btn_group_none)
        group_row.addStretch()
        layout.addLayout(group_row)

        self._btn_group_analyze = WrapButton("📊 Сводный анализ группы")
        self._btn_group_analyze.setEnabled(False)
        self._btn_group_analyze.setMinimumHeight(36)
        self._btn_group_analyze.setStyleSheet(
            "QPushButton { background: #5b8def; color: white; font-size: 12px; "
            "padding: 4px 10px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #6f9bf2; }"
            "QPushButton:disabled { background: #d8dce4; color: #7a828e; }"
        )
        layout.addWidget(self._btn_group_analyze)

        self._group_count_label = QLabel("В группе: 0")
        self._group_count_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._group_count_label)

        # Сигналы
        self._btn_add.clicked.connect(self._add_files)
        self._btn_add_folder.clicked.connect(self._add_folder)
        self._btn_remove.clicked.connect(self._remove_selected)
        self._btn_clear.clicked.connect(self._clear)
        self._btn_group_all.clicked.connect(self._check_all)
        self._btn_group_none.clicked.connect(self._uncheck_all)
        self._btn_group_analyze.clicked.connect(self._emit_group_request)
        self._list.currentRowChanged.connect(
            lambda row: self._btn_remove.setEnabled(row >= 0)
        )

    # ── Публичный API ─────────────────────────────────────────────────────────

    @property
    def files(self) -> list[Path]:
        return list(self._files)

    @property
    def selected_file(self) -> Path | None:
        row = self._list.currentRow()
        return self._files[row] if 0 <= row < len(self._files) else None

    @property
    def group_files(self) -> list[Path]:
        """Файлы с включённым чекбоксом."""
        result: list[Path] = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                result.append(self._files[i])
        return result

    def recommended_panel_width(self) -> int:
        return self._panel_width_hint

    # ── Слоты ─────────────────────────────────────────────────────────────────

    def _add_files(self) -> None:
        ext_filter = "Изображения ({})".format(
            " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        )
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать изображения", "", ext_filter
        )
        self._add_paths([Path(p) for p in paths])

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Выбрать папку")
        if folder:
            paths = [
                p for p in Path(folder).iterdir()
                if p.suffix.lower() in SUPPORTED_EXTENSIONS
            ]
            self._add_paths(sorted(paths))

    def _add_paths(self, paths: list[Path]) -> None:
        added = False
        for p in paths:
            if p not in self._files:
                self._files.append(p)
                item = QListWidgetItem(self._make_icon(p), p.name)
                item.setToolTip(str(p))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self._list.addItem(item)
                added = True
        if added:
            self._update_count()
            self._update_group_state()
            self.files_changed.emit(self._files)

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        self._list.takeItem(row)
        self._files.pop(row)
        self._update_count()
        self._update_group_state()
        self.files_changed.emit(self._files)

    def _clear(self) -> None:
        self._list.clear()
        self._files.clear()
        self._update_count()
        self._update_group_state()
        self.files_changed.emit(self._files)

    def _on_selection_changed(self, row: int) -> None:
        self._btn_remove.setEnabled(row >= 0)

    def _on_item_changed(self, _item) -> None:
        self._update_group_state()
        self.group_changed.emit(self.group_files)

    def _check_all(self) -> None:
        self._set_all_checked(True)

    def _uncheck_all(self) -> None:
        self._set_all_checked(False)

    def _set_all_checked(self, checked: bool) -> None:
        self._list.blockSignals(True)
        try:
            state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            for i in range(self._list.count()):
                item = self._list.item(i)
                if item is not None:
                    item.setCheckState(state)
        finally:
            self._list.blockSignals(False)
        self._update_group_state()
        self.group_changed.emit(self.group_files)

    def _emit_group_request(self) -> None:
        files = self.group_files
        if files:
            self.group_analysis_requested.emit(files)

    def _update_group_state(self) -> None:
        n = len(self.group_files)
        self._group_count_label.setText(f"В группе: {n}")
        self._btn_group_analyze.setEnabled(n >= 2)

    def _update_count(self) -> None:
        self._count_label.setText(f"Файлов: {len(self._files)}")

    def _apply_uniform_button_size(self, btn_row: QHBoxLayout) -> None:
        buttons = [self._btn_add, self._btn_add_folder, self._btn_remove, self._btn_clear]
        max_w = max(btn.sizeHint().width() for btn in buttons)
        max_h = max(btn.sizeHint().height() for btn in buttons)

        for btn in buttons:
            btn.setFixedSize(max_w, max_h)

        margins = self.layout().contentsMargins()
        spacing = btn_row.spacing()
        if spacing < 0:
            spacing = 6
        self._panel_width_hint = margins.left() + margins.right() + (max_w * len(buttons)) + (spacing * (len(buttons) - 1))

    # ── Миниатюра ─────────────────────────────────────────────────────────────

    @staticmethod
    def _make_icon(path: Path) -> QIcon:
        try:
            img = ski.io.imread(str(path), as_gray=True)
            # нормализуем
            if img.max() > 0:
                img = img / img.max()
            img_uint8 = (img * 255).astype(np.uint8)
            # масштабируем
            img_small = ski.transform.resize(
                img_uint8,
                THUMBNAIL_SIZE[::-1],  # (height, width)
                anti_aliasing=True,
                preserve_range=True,
            ).astype(np.uint8)
            h, w = img_small.shape
            from PyQt6.QtGui import QImage
            qimg = QImage(img_small.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
            return QIcon(QPixmap.fromImage(qimg))
        except Exception:
            return QIcon()