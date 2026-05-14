"""
Диалог калибровки масштаба по линейке метаданных.

Показывает нижнюю информационную полосу изображения (там, где SEM/BSE микроскопы
печатают служебную информацию и масштабную линейку) в нативном разрешении.
Пользователь кликает по двум концам линейки, вводит её длину в мкм — программа
вычисляет масштаб (мкм/пиксель). Удержание Shift привязывает линию к осям.
"""

from __future__ import annotations
from pathlib import Path

import math
import numpy as np
import skimage as ski
from PyQt6.QtCore import Qt, QPointF, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


# Минимальная высота полосы метаданных (если автодетект не нашёл)
_FALLBACK_BAR_HEIGHT = 100


class _MeasureLabel(QLabel):
    """QLabel в нативном масштабе, ловит две точки и рисует измерительную линию."""

    points_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._pt1: QPointF | None = None
        self._pt2: QPointF | None = None
        self._cursor_pos: QPointF | None = None
        self._shift_held = False
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setStyleSheet("background: #2c2f36;")

    # ── публичный API ────────────────────────────────────────────────────

    def set_image(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self._pt1 = None
        self._pt2 = None
        self._cursor_pos = None
        if pixmap is not None:
            self.setFixedSize(pixmap.size())
        self.update()
        self.points_changed.emit()

    def reset_points(self) -> None:
        self._pt1 = None
        self._pt2 = None
        self.update()
        self.points_changed.emit()

    def pixel_distance(self) -> float | None:
        if self._pt1 is None or self._pt2 is None:
            return None
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        return math.hypot(dx, dy)

    # ── события ────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._pixmap is None or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        if self._pt1 is None or self._pt2 is not None:
            self._pt1 = QPointF(pos)
            self._pt2 = None
        else:
            self._pt2 = self._snap(pos)
        self.update()
        self.points_changed.emit()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._cursor_pos = event.position()
        self._shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._pt1 is not None and self._pt2 is None:
            self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Escape,):
            self.reset_points()
        super().keyPressEvent(event)

    # ── рисование ──────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(44, 47, 54))
        if self._pixmap is not None:
            painter.drawPixmap(0, 0, self._pixmap)

        pen_pt = QPen(QColor(255, 196, 0), 2)
        pen_line = QPen(QColor(255, 196, 0), 2, Qt.PenStyle.SolidLine)
        pen_preview = QPen(QColor(255, 196, 0, 160), 2, Qt.PenStyle.DashLine)

        if self._pt1 is not None:
            painter.setPen(pen_pt)
            painter.setBrush(QColor(255, 220, 100))
            self._draw_handle(painter, self._pt1)

        end = self._pt2
        if end is None and self._pt1 is not None and self._cursor_pos is not None:
            end_preview = self._snap(self._cursor_pos)
            painter.setPen(pen_preview)
            painter.drawLine(self._pt1, end_preview)
        elif end is not None and self._pt1 is not None:
            painter.setPen(pen_line)
            painter.drawLine(self._pt1, end)
            painter.setPen(pen_pt)
            painter.setBrush(QColor(255, 220, 100))
            self._draw_handle(painter, end)

            mid = QPointF((self._pt1.x() + end.x()) / 2.0, (self._pt1.y() + end.y()) / 2.0)
            font = QFont()
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)
            d = math.hypot(end.x() - self._pt1.x(), end.y() - self._pt1.y())
            text = f"{d:.1f} px"
            txt_pt = QPointF(mid.x() + 8, mid.y() - 8)
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(txt_pt + QPointF(1, 1), text)
            painter.setPen(QColor(255, 220, 100))
            painter.drawText(txt_pt, text)

    @staticmethod
    def _draw_handle(painter: QPainter, p: QPointF) -> None:
        r = 5.0
        rect = QRect(int(p.x() - r), int(p.y() - r), int(r * 2), int(r * 2))
        painter.drawRect(rect)
        painter.drawLine(int(p.x() - r * 2), int(p.y()), int(p.x() + r * 2), int(p.y()))
        painter.drawLine(int(p.x()), int(p.y() - r * 2), int(p.x()), int(p.y() + r * 2))

    def _snap(self, pos: QPointF) -> QPointF:
        """С зажатым Shift привязывает к ближайшей оси относительно pt1."""
        if self._pt1 is None or not self._shift_held:
            return QPointF(pos)
        dx = abs(pos.x() - self._pt1.x())
        dy = abs(pos.y() - self._pt1.y())
        if dx >= dy:
            return QPointF(pos.x(), self._pt1.y())
        return QPointF(self._pt1.x(), pos.y())


class ScaleCalibrationDialog(QDialog):
    """Окно калибровки масштаба по двум точкам на линейке метаданных."""

    def __init__(
        self,
        image_path: Path,
        current_scale: float = 0.1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._image_path = image_path
        self._scale_um_per_px: float | None = None
        self._initial_scale = current_scale
        self._setup_ui()
        self._load_image()

    # ── публичный API ────────────────────────────────────────────────────

    @property
    def computed_scale(self) -> float | None:
        return self._scale_um_per_px

    # ── UI ───────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle("Калибровка масштаба")
        self.resize(1100, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel(f"Калибровка масштаба — {self._image_path.name}")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        root.addWidget(title)

        hint = QLabel(
            "1. Кликните начало масштабной линейки.   2. Кликните её конец "
            "(удерживайте Shift для привязки к осям).   3. Введите расстояние в мкм."
        )
        hint.setStyleSheet("color: #4a525e; font-size: 11px;")
        root.addWidget(hint)

        # Скролл с нативным изображением полосы метаданных
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setStyleSheet("QScrollArea { background: #2c2f36; border: 1px solid #3a3e47; }")
        self._scroll.setMinimumHeight(220)

        self._measure = _MeasureLabel()
        self._measure.points_changed.connect(self._update_state)
        self._scroll.setWidget(self._measure)
        root.addWidget(self._scroll, stretch=1)

        # Нижняя строка: расстояние и ввод
        row = QHBoxLayout()
        row.setSpacing(12)

        self._dist_label = QLabel("Расстояние: — px")
        self._dist_label.setStyleSheet("font-size: 12px; min-width: 200px;")
        row.addWidget(self._dist_label)

        row.addWidget(QLabel("Длина в мкм:"))

        self._um_input = QDoubleSpinBox()
        self._um_input.setRange(0.0001, 1_000_000.0)
        self._um_input.setDecimals(3)
        self._um_input.setSingleStep(1.0)
        self._um_input.setValue(10.0)
        self._um_input.setFixedWidth(110)
        self._um_input.valueChanged.connect(self._update_state)
        row.addWidget(self._um_input)

        self._scale_label = QLabel("→ масштаб: — мкм/пкс")
        self._scale_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #2a6cba;"
        )
        row.addWidget(self._scale_label)

        row.addStretch()

        self._btn_reset = QPushButton("Сбросить точки")
        self._btn_reset.clicked.connect(self._measure.reset_points)
        row.addWidget(self._btn_reset)

        self._btn_full = QPushButton("Показать всё изображение")
        self._btn_full.setCheckable(True)
        self._btn_full.toggled.connect(self._toggle_full_image)
        row.addWidget(self._btn_full)

        root.addLayout(row)

        # Кнопки действия
        actions = QHBoxLayout()
        actions.addStretch()

        self._btn_ok = QPushButton("✓ Применить")
        self._btn_ok.setEnabled(False)
        self._btn_ok.setStyleSheet(
            "QPushButton { background: #2a6cba; color: white; padding: 6px 18px; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #3480d4; }"
            "QPushButton:disabled { background: #d8dce4; color: #7a828e; }"
        )
        self._btn_ok.clicked.connect(self._accept)
        actions.addWidget(self._btn_ok)

        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        actions.addWidget(btn_cancel)

        root.addLayout(actions)

    # ── загрузка и обрезка ──────────────────────────────────────────────

    def _load_image(self) -> None:
        try:
            img = ski.io.imread(str(self._image_path), as_gray=True)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть файл:\n{exc}")
            return

        img = np.asarray(img, dtype=float)
        if img.max() > 1.0:
            img = img / img.max()
        self._full_img = img

        bar = self._extract_bottom_bar(img)
        self._show_pixmap_from_array(bar)

    def _toggle_full_image(self, checked: bool) -> None:
        if checked:
            self._show_pixmap_from_array(self._full_img)
            self._btn_full.setText("Показать только полосу")
        else:
            bar = self._extract_bottom_bar(self._full_img)
            self._show_pixmap_from_array(bar)
            self._btn_full.setText("Показать всё изображение")

    @staticmethod
    def _extract_bottom_bar(image: np.ndarray) -> np.ndarray:
        """Повторяет логику Preprocessor._auto_crop, но возвращает САМУ полосу."""
        height, width = image.shape
        binary = image > 0.5
        crop_row = 0
        hits = 0
        for h in range(height - 2, 0, -1):
            if binary[h, width - 2]:
                crop_row = h
                hits += 1
            if hits == 2:
                break

        if crop_row > height // 2:
            return image[crop_row:, :]
        # Фолбэк: нижние ~100 строк
        start = max(0, height - _FALLBACK_BAR_HEIGHT)
        return image[start:, :]

    def _show_pixmap_from_array(self, arr: np.ndarray) -> None:
        u8 = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
        h, w = u8.shape
        qimg = QImage(u8.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
        self._measure.set_image(QPixmap.fromImage(qimg.copy()))

    # ── логика расчёта ──────────────────────────────────────────────────

    def _update_state(self) -> None:
        d = self._measure.pixel_distance()
        um = self._um_input.value()
        if d is None or d < 1e-6:
            self._dist_label.setText("Расстояние: — px")
            self._scale_label.setText("→ масштаб: — мкм/пкс")
            self._btn_ok.setEnabled(False)
            self._scale_um_per_px = None
            return

        scale = um / d
        self._scale_um_per_px = scale
        self._dist_label.setText(f"Расстояние: {d:.1f} px")
        self._scale_label.setText(f"→ масштаб: {scale:.5f} мкм/пкс")
        self._btn_ok.setEnabled(True)

    def _accept(self) -> None:
        if self._scale_um_per_px is None:
            return
        self.accept()
