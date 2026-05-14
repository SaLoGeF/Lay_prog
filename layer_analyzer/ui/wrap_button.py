"""Кнопка с переносом текста на несколько строк при нехватке ширины."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QPushButton, QStyle, QStyleOptionButton


class WrapButton(QPushButton):
    """QPushButton, который рисует текст с переносом строк."""

    def paintEvent(self, _event) -> None:  # noqa: N802
        option = QStyleOptionButton()
        self.initStyleOption(option)

        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButtonBevel, option, painter, self)

        content_rect = self.style().subElementRect(
            QStyle.SubElement.SE_PushButtonContents,
            option,
            self,
        )
        text_rect = QRect(content_rect.adjusted(4, 2, -4, -2))
        painter.setPen(option.palette.buttonText().color())
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self.text(),
        )
