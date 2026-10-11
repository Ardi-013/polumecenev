from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Лабораторная 1")
        self.resize(500, 350)
        self.main_page()

    def main_page(self):
        central = self.create_page_central()
        layout = self.create_layout(central)

        self.send = self.create_button("Отправить", self._on_click)
        self.receive = self.create_button("Получить", self._on_click)

        layout.addWidget(self.send, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.receive, alignment=Qt.AlignmentFlag.AlignHCenter)

    def send_page(self):
        central = self.create_page_central()
        layout = self.create_layout(central, horizontal=True)

        image = QLabel("Изображение")
        image.setFixedSize(180, 180)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setStyleSheet("border: 1px solid gray;")
        layout.addWidget(image)

        buttons_layout = self.create_layout()
        self.send_confirm = self.create_button("Отправить", self._on_click)
        self.send_cancel = self.create_button("Назад", self._on_click)
        buttons_layout.addWidget(self.send_confirm)
        buttons_layout.addWidget(self.send_cancel)

        layout.addLayout(buttons_layout)

    def sending_page(self):
        central = self.create_page_central()
        layout = self.create_layout(central)

        h_layout = QHBoxLayout()
        self.send_spinner = QProgressBar()
        self.send_spinner.setRange(0, 0)
        self.send_spinner.setFixedSize(200, 4)
        self.send_spinner.setTextVisible(False)
        
        h_layout.addStretch()
        h_layout.addWidget(self.send_spinner)
        h_layout.addStretch()

        label = QLabel("Отправка...")
        label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.send_abort = self.create_button("Отмена", self._on_click)

        layout.addLayout(h_layout)
        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.send_abort, alignment=Qt.AlignmentFlag.AlignHCenter)

    def receive_page(self):
        central = self.create_page_central()
        layout = self.create_layout(central)

        label = QLabel("Страница получения данных")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

    def create_page_central(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        return central_widget
    
    def create_button(self, text, callback):
        button = QPushButton(text)
        button.setFixedSize(140, 36)
        button.clicked.connect(callback)
        return button

    def create_layout(self, central_widget=None, horizontal=False):
        if horizontal:
            layout = QHBoxLayout(central_widget) if central_widget else QHBoxLayout()
        else:
            layout = QVBoxLayout(central_widget) if central_widget else QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)
        return layout

    def _on_click(self):
        sender = self.sender()
        if sender == self.send:
            self.send_page()
        elif sender == self.receive:
            self.receive_page()
        elif sender == self.send_confirm:
            self.sending_page()
        elif sender == self.send_cancel or sender == getattr(self, "send_abort", None):
            self.main_page()