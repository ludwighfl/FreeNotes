import os
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QPropertyAnimation, Property, QRectF
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
            self.logical_width = 0
            self.logical_height = 0
        else:
            screen = QGuiApplication.primaryScreen()
            screen_geometry = screen.geometry()
            target_logical_width = screen_geometry.width() * 0.20
            self.dpr = screen.devicePixelRatio()
            
            # Create a purely physical high-res pixmap without setting internal dpr trickery
            physical_width = int(target_logical_width * self.dpr)
            self.pixmap = original_pixmap.scaledToWidth(
                physical_width, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.logical_width = self.pixmap.width() / self.dpr
            self.logical_height = self.pixmap.height() / self.dpr

        self._gleam_pos = 0.0
        self._frame_cache: dict[int, QPixmap] = {}

        self.animation = QPropertyAnimation(self, b"gleam_pos")
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(2500)
        self.animation.setLoopCount(-1)
        self.animation.start()

    def start_animation(self) -> None:
        """Starts or resumes the gleam animation."""
        if self.animation.state() != QPropertyAnimation.State.Running:
            self.animation.start()

    def stop_animation(self) -> None:
        """Stops the gleam animation completely to conserve CPU when hidden."""
        if self.animation.state() == QPropertyAnimation.State.Running:
            self.animation.stop()

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
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Fill background with the theme color
        painter.fillRect(self.rect(), self.bg_color)

        if getattr(self, "logical_width", 0) == 0:
            return

        # 2. Calculate logical coordinates to center
        x_offset = (self.width() - self.logical_width) / 2.0
        y_offset = (self.height() - self.logical_height) / 2.0
        target_rect = QRectF(x_offset, y_offset, self.logical_width, self.logical_height)

        # 3. Draw base logo dimmed (as background)
        painter.setOpacity(0.3)
        painter.drawPixmap(target_rect, self.pixmap, QRectF(self.pixmap.rect()))

        # 4. Prepare the gleam effect purely in physical coordinates to prevent bleeding
        painter.setOpacity(1.0)
        
        pw = self.pixmap.width()
        ph = self.pixmap.height()
        
        # Discretize gleam_pos into exactly 120 frames
        step = int(self._gleam_pos * 120)

        # Draw highly expensive composited frame if cached
        if step in self._frame_cache:
            cached_frame = self._frame_cache[step]
            painter.drawPixmap(target_rect, cached_frame, QRectF(cached_frame.rect()))
            painter.end()
            return

        frame_buffer = QPixmap(pw, ph)
        frame_buffer.fill(Qt.GlobalColor.transparent)
        
        buffer_painter = QPainter(frame_buffer)
        buffer_painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gleam_width = pw * 0.4 
        start_x = -gleam_width
        end_x = pw + gleam_width
        center = start_x + (step / 120.0) * (end_x - start_x)

        # Draw the light gradient
        gradient = QLinearGradient(center - gleam_width/2, 0, center + gleam_width/2, 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 255))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))

        buffer_painter.fillRect(0, 0, pw, ph, QBrush(gradient))

        # Use SourceIn to mask the gradient using the logo's alpha and color
        buffer_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        buffer_painter.drawPixmap(0, 0, self.pixmap)
        buffer_painter.end()

        # Cache the resulting frame for sub-1ms lightning fast subsequent calls
        self._frame_cache[step] = frame_buffer

        # Draw the final physical buffer mapped precisely onto the logical target area
        painter.drawPixmap(target_rect, frame_buffer, QRectF(frame_buffer.rect()))
        
        painter.end()

    def keyPressEvent(self, event: QKeyEvent):
        super().keyPressEvent(event)
