import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit
from PyQt6.QtCore import Qt, QTimer, QRect, pyqtProperty, QEasingCurve, QPropertyAnimation
from PyQt6.QtGui import QPainter, QColor, QPen
from jarvis.core.bus import bus

class JarvisOrb(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(60, 60)
        self._state = "idle" # idle, listening, thinking, speaking
        self._anim_val = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_anim)
        self.timer.start(30)

    def set_state(self, state):
        self._state = state

    def update_anim(self):
        import math, time
        self._anim_val = math.sin(time.time() * 5) * 0.2 + 0.8
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = {
            "idle": QColor(0, 150, 255),
            "listening": QColor(255, 50, 50),
            "thinking": QColor(200, 200, 200),
            "speaking": QColor(50, 255, 150)
        }

        color = colors.get(self._state, colors["idle"])
        painter.setPen(QPen(color, 3))
        radius = 20 * self._anim_val if self._state != "idle" else 20
        painter.drawEllipse(30-int(radius), 30-int(radius), int(radius*2), int(radius*2))

class JarvisOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(100, 100, 380, 240) # Positioned bottom-right in main

        self.layout = QVBoxLayout(self)
        self.orb = JarvisOrb()
        self.transcript = QLabel("...")
        self.response = QLabel("")
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type here...")

        self.layout.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.transcript)
        self.layout.addWidget(self.response)
        self.layout.addWidget(self.input)

        self.hide_timer = QTimer()
        self.hide_timer.timeout.connect(self.hide)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()

    async def on_event(self, event_type, data):
        if event_type == "state_change":
            self.orb.set_state(data)
        elif event_type == "transcript":
            self.transcript.setText(data)
        elif event_type == "response":
            self.response.setText(data)
        self.show()
        self.hide_timer.start(10000)

overlay = None # Initialized in main
