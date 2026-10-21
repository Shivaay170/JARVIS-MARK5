import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
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
        self.update()

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
    text_submitted = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        screen = QApplication.primaryScreen()
        w, h = 380, 260
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + geo.width() - w - 24
            y = geo.y() + geo.height() - h - 24
            self.setGeometry(max(50, x), max(50, y), w, h)
        else:
            self.setGeometry(100, 100, w, h)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QWidget(self)
        self.container.setObjectName("OverlayCard")
        root_layout.addWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)

        # Header bar with title and close button
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("J.A.R.V.I.S.")
        title.setObjectName("HeaderTitle")
        close_btn = QPushButton("✕")
        close_btn.setObjectName("CloseBtn")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        # Orb
        self.orb = JarvisOrb()
        layout.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignCenter)

        # Transcript
        self.transcript = QLabel("Ready for your command, sir.")
        self.transcript.setObjectName("Transcript")
        self.transcript.setWordWrap(True)
        layout.addWidget(self.transcript)

        # Response
        self.response = QLabel("")
        self.response.setObjectName("Response")
        self.response.setWordWrap(True)
        layout.addWidget(self.response)

        # Input
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type command or press F9 to talk...")
        self.input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.input)

        self.setStyleSheet("""
            QWidget#OverlayCard {
                background-color: rgba(15, 23, 42, 240);
                border: 1px solid rgba(56, 189, 248, 120);
                border-radius: 16px;
            }
            QLabel {
                color: #E2E8F0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QLabel#HeaderTitle {
                color: #38BDF8;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            QPushButton#CloseBtn {
                background: transparent;
                color: #94A3B8;
                border: none;
                font-size: 13px;
                font-weight: bold;
                border-radius: 11px;
            }
            QPushButton#CloseBtn:hover {
                background: rgba(239, 68, 68, 0.4);
                color: #FFFFFF;
            }
            QLabel#Transcript {
                color: #94A3B8;
                font-style: italic;
            }
            QLabel#Response {
                color: #38BDF8;
                font-weight: 600;
            }
            QLineEdit {
                background-color: rgba(30, 41, 59, 220);
                border: 1px solid rgba(56, 189, 248, 80);
                border-radius: 8px;
                padding: 6px 10px;
                color: #F8FAFC;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #38BDF8;
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def _on_submit(self):
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.transcript.setText(text)
            self.response.setText("")
            self.text_submitted.emit(text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()

    def handle_event(self, event_type: str, data: str):
        if event_type == "state_change":
            self.orb.set_state(data)
        elif event_type == "transcript":
            self.transcript.setText(data)
        elif event_type == "response":
            self.response.setText(data)
        self.show()
        self.raise_()
        self.activateWindow()

overlay = None # Initialized in main
