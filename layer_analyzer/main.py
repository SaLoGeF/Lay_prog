"""
Точка входа приложения.
Только запускает GUI — никакой логики здесь нет.
"""
 
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt 
from ui.main_window import MainWindow
 
 
def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
 
    # Светлая тема
    _apply_light_palette(app)
 
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
 
 
def _apply_light_palette(app: QApplication) -> None:
    from PyQt6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(245, 246, 248))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.Base,            QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(242, 244, 247))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.Text,            QColor(35, 35, 35))
    palette.setColor(QPalette.ColorRole.Button,          QColor(244, 246, 250))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.BrightText,      QColor(220, 20, 60))
    palette.setColor(QPalette.ColorRole.Link,            QColor(34, 93, 176))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(42, 108, 186))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
 
 
if __name__ == "__main__":
    main()
 