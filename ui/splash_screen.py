import os
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QPropertyAnimation, Property
from PySide6.QtGui import QPixmap, QPainter, QColor, QLinearGradient, QBrush, QKeyEvent, QGuiApplication

class SplashScreen(QWidget):
    """
    A frameless, full-screen splash screen matching the app's dark theme (#1a1a1a).
    The logo is centered, scaled, and features an animated light ray (gleam) effect.
    """
    def __init__(self, image_path: str):
        super().__init__()
        
        # We use the app background color from base.qss
        self.bg_color = QColor("#1a1a1a")

        # 2. Load and scale image
        original_pixmap = QPixmap(image_path)
        if original_pixmap.isNull():
            print(f"Warning: Image '{image_path}' could not be loaded!")
            self.pixmap = QPixmap()
        else:
            screen = QGuiApplication.primaryScreen()
            screen_geometry = screen.geometry()
            target_width = screen_geometry.width() * 0.20
            self.pixmap = original_pixmap.scaledToWidth(
                int(target_width), 
                Qt.TransformationMode.SmoothTransformation
            )

        self._gleam_pos = 0.0

        # 3. Configure animation -> 2.5s per loop, endless
        self.animation = QPropertyAnimation(self, b"gleam_pos")
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(2500)
        self.animation.setLoopCount(-1)
        self.animation.start()

    @Property(float)
    def gleam_pos(self):
        return self._gleam_pos

    @gleam_pos.setter
    def gleam_pos(self, pos):
        self._gleam_pos = pos
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Fill background with the theme color
        painter.fillRect(self.rect(), self.bg_color)

        if self.pixmap.isNull():
            return

        # 2. Calculate coordinates to center scaled logo
        x_offset = int((self.width() - self.pixmap.width()) / 2)
        y_offset = int((self.height() - self.pixmap.height()) / 2)

        # 3. Draw base logo dimmed (as background)
        painter.setOpacity(0.3)
        painter.drawPixmap(x_offset, y_offset, self.pixmap)

        # 4. Prepare the gleam effect
        painter.setOpacity(1.0)
        
        gleam_buffer = QPixmap(self.size())
        gleam_buffer.fill(Qt.GlobalColor.transparent)
        
        buffer_painter = QPainter(gleam_buffer)
        buffer_painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gleam_width = self.pixmap.width() * 0.4 
        start_x = x_offset - gleam_width
        end_x = x_offset + self.pixmap.width() + gleam_width
        center = start_x + self._gleam_pos * (end_x - start_x)

        gradient = QLinearGradient(center - gleam_width/2, 0, center + gleam_width/2, 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 255))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))

        buffer_painter.fillRect(x_offset, y_offset, self.pixmap.width(), self.pixmap.height(), QBrush(gradient))

        buffer_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        buffer_painter.drawPixmap(x_offset, y_offset, self.pixmap)
        buffer_painter.end()

        painter.drawPixmap(0, 0, gleam_buffer)

    def keyPressEvent(self, event: QKeyEvent):
        super().keyPressEvent(event)
