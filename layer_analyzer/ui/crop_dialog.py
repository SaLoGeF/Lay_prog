"""
Диалог ручной обрезки изображения.
Позволяет потянуть за края/углы рамки, как в редакторах документов.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass
class CropRect:
    left: int
    top: int
    right: int
    bottom: int


class CropCanvas(QWidget):
    """Холст с интерактивной рамкой обрезки."""

    _HANDLE_SIZE = 10.0
    _MIN_RECT_SIZE = 20.0

    def __init__(self, image: np.ndarray, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = image
        self._pixmap = self._to_pixmap(image)
        self._img_w = int(image.shape[1])
        self._img_h = int(image.shape[0])

        self._image_rect = QRectF()
        margin_x = self._img_w * 0.05
        margin_y = self._img_h * 0.05
        self._crop_rect_img = QRectF(
            margin_x,
            margin_y,
            self._img_w - margin_x * 2,
            self._img_h - margin_y * 2,
        )

        self._drag_mode = "none"
        self._last_pos = QPointF()
        self.setMouseTracking(True)
        self.setMinimumSize(780, 520)

    def get_crop_rect(self) -> CropRect:
        r = self._crop_rect_img.normalized()
        left = max(0, min(self._img_w - 2, int(round(r.left()))))
        top = max(0, min(self._img_h - 2, int(round(r.top()))))
        right = max(left + 1, min(self._img_w, int(round(r.right())) + 1))
        bottom = max(top + 1, min(self._img_h, int(round(r.bottom())) + 1))
        return CropRect(left=left, top=top, right=right, bottom=bottom)

    def reset_crop(self) -> None:
        margin_x = self._img_w * 0.05
        margin_y = self._img_h * 0.05
        self._crop_rect_img = QRectF(
            margin_x,
            margin_y,
            self._img_w - margin_x * 2,
            self._img_h - margin_y * 2,
        )
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        self._image_rect = self._fit_rect()
        painter.drawPixmap(self._image_rect, self._pixmap)

        crop_widget = self._img_to_widget(self._crop_rect_img)

        # Затемняем область вне рамки
        overlay_color = Qt.GlobalColor.black
        painter.setOpacity(0.45)
        painter.fillRect(self._image_rect.adjusted(0, 0, 0, crop_widget.top() - self._image_rect.top()), overlay_color)
        painter.fillRect(self._image_rect.adjusted(0, crop_widget.bottom() - self._image_rect.top(), 0, 0), overlay_color)
        painter.fillRect(
            QRectF(
                self._image_rect.left(),
                crop_widget.top(),
                crop_widget.left() - self._image_rect.left(),
                crop_widget.height(),
            ),
            overlay_color,
        )
        painter.fillRect(
            QRectF(
                crop_widget.right(),
                crop_widget.top(),
                self._image_rect.right() - crop_widget.right(),
                crop_widget.height(),
            ),
            overlay_color,
        )
        painter.setOpacity(1.0)

        # Рамка обрезки
        pen = QPen(Qt.GlobalColor.white, 2)
        painter.setPen(pen)
        painter.drawRect(crop_widget)

        # Маркеры по углам и центрам сторон
        painter.setBrush(Qt.GlobalColor.white)
        for rect in self._handles(crop_widget).values():
            painter.drawRect(rect)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self._image_rect.contains(event.position()):
            return
        self._last_pos = event.position()
        self._drag_mode = self._hit_test(event.position())
        if self._drag_mode == "none":
            crop_widget = self._img_to_widget(self._crop_rect_img)
            if crop_widget.contains(event.position()):
                self._drag_mode = "move"

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_mode == "none":
            self._update_cursor(event.position())
            return

        dx = event.position().x() - self._last_pos.x()
        dy = event.position().y() - self._last_pos.y()
        self._last_pos = event.position()

        scale_x = self._img_w / max(self._image_rect.width(), 1.0)
        scale_y = self._img_h / max(self._image_rect.height(), 1.0)
        ddx = dx * scale_x
        ddy = dy * scale_y

        r = QRectF(self._crop_rect_img)
        if self._drag_mode == "move":
            r.translate(ddx, ddy)
            if r.left() < 0:
                r.translate(-r.left(), 0)
            if r.top() < 0:
                r.translate(0, -r.top())
            if r.right() > self._img_w:
                r.translate(self._img_w - r.right(), 0)
            if r.bottom() > self._img_h:
                r.translate(0, self._img_h - r.bottom())
        else:
            if "left" in self._drag_mode:
                new_left = min(r.right() - self._MIN_RECT_SIZE, r.left() + ddx)
                r.setLeft(max(0.0, new_left))
            if "right" in self._drag_mode:
                new_right = max(r.left() + self._MIN_RECT_SIZE, r.right() + ddx)
                r.setRight(min(float(self._img_w), new_right))
            if "top" in self._drag_mode:
                new_top = min(r.bottom() - self._MIN_RECT_SIZE, r.top() + ddy)
                r.setTop(max(0.0, new_top))
            if "bottom" in self._drag_mode:
                new_bottom = max(r.top() + self._MIN_RECT_SIZE, r.bottom() + ddy)
                r.setBottom(min(float(self._img_h), new_bottom))

        self._crop_rect_img = r.normalized()
        self.update()

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802
        self._drag_mode = "none"

    def _fit_rect(self) -> QRectF:
        area = self.rect().adjusted(20, 20, -20, -20)
        if area.width() <= 0 or area.height() <= 0:
            return QRectF()
        img_ratio = self._img_w / self._img_h
        area_ratio = area.width() / area.height()

        if img_ratio > area_ratio:
            w = area.width()
            h = w / img_ratio
            x = area.left()
            y = area.top() + (area.height() - h) / 2
        else:
            h = area.height()
            w = h * img_ratio
            x = area.left() + (area.width() - w) / 2
            y = area.top()
        return QRectF(x, y, w, h)

    def _img_to_widget(self, rect_img: QRectF) -> QRectF:
        sx = self._image_rect.width() / max(self._img_w, 1)
        sy = self._image_rect.height() / max(self._img_h, 1)
        return QRectF(
            self._image_rect.left() + rect_img.left() * sx,
            self._image_rect.top() + rect_img.top() * sy,
            rect_img.width() * sx,
            rect_img.height() * sy,
        )

    def _handles(self, crop_widget: QRectF) -> dict[str, QRectF]:
        hs = self._HANDLE_SIZE
        cx = crop_widget.center().x()
        cy = crop_widget.center().y()

        def sq(x: float, y: float) -> QRectF:
            return QRectF(x - hs / 2, y - hs / 2, hs, hs)

        return {
            "top_left": sq(crop_widget.left(), crop_widget.top()),
            "top": sq(cx, crop_widget.top()),
            "top_right": sq(crop_widget.right(), crop_widget.top()),
            "right": sq(crop_widget.right(), cy),
            "bottom_right": sq(crop_widget.right(), crop_widget.bottom()),
            "bottom": sq(cx, crop_widget.bottom()),
            "bottom_left": sq(crop_widget.left(), crop_widget.bottom()),
            "left": sq(crop_widget.left(), cy),
        }

    def _hit_test(self, pos: QPointF) -> str:
        crop_widget = self._img_to_widget(self._crop_rect_img)
        for name, rect in self._handles(crop_widget).items():
            if rect.contains(pos):
                return name
        if crop_widget.contains(pos):
            return "move"
        return "none"

    def _update_cursor(self, pos: QPointF) -> None:
        mode = self._hit_test(pos)
        if mode in {"top_left", "bottom_right"}:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif mode in {"top_right", "bottom_left"}:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif mode in {"left", "right"}:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif mode in {"top", "bottom"}:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif mode == "move":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    @staticmethod
    def _to_pixmap(img: np.ndarray) -> QPixmap:
        img_u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
        h, w = img_u8.shape
        qimg = QImage(img_u8.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
        return QPixmap.fromImage(qimg)


class CropDialog(QDialog):
    """Модальное окно ручной обрезки."""

    def __init__(self, image: np.ndarray, image_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Ручная обрезка: {image_name}")
        self.resize(980, 700)

        root = QVBoxLayout(self)
        info = QLabel(
            "Потяните за края или углы рамки, чтобы выбрать область анализа. "
            "Можно перетаскивать рамку целиком."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        self._canvas = CropCanvas(image)
        root.addWidget(self._canvas, stretch=1)

        buttons = QHBoxLayout()
        btn_reset = QPushButton("Сбросить")
        btn_cancel = QPushButton("Отмена")
        btn_ok = QPushButton("Применить")
        btn_ok.setDefault(True)
        buttons.addWidget(btn_reset)
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        root.addLayout(buttons)

        btn_reset.clicked.connect(self._canvas.reset_crop)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)

    def selected_crop(self) -> CropRect:
        return self._canvas.get_crop_rect()
