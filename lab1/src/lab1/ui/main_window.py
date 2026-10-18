from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lab1.audio.workers import AudioReceiverThread, AudioSenderThread
from lab1.domain.catalog import BODIES, CelestialBody, get_body, get_images_dir, match_body_by_path


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Лабораторная 1")
        self.resize(500, 350)
        self.current_image_path: Optional[str] = None
        self.sender_thread: Optional[AudioSenderThread] = None
        self.receiver_thread: Optional[AudioReceiverThread] = None
        self.main_page()

    def closeEvent(self, event: QCloseEvent):
        self._stop_threads()
        super().closeEvent(event)

    def _stop_threads(self):
        if self.sender_thread and self.sender_thread.isRunning():
            self.sender_thread.abort()
            self.sender_thread.wait(400)
            self.sender_thread = None
        if self.receiver_thread and self.receiver_thread.isRunning():
            self.receiver_thread.stop()
            self.receiver_thread.wait(400)
            self.receiver_thread = None

    def main_page(self):
        self._stop_threads()
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

        if self.current_image_path:
            pixmap = QPixmap(self.current_image_path)
            if not pixmap.isNull():
                image.setPixmap(pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        layout.addWidget(image)

        buttons_layout = self.create_layout()
        self.send_confirm = self.create_button("Отправить", self._on_click)
        self.send_cancel = self.create_button("Назад", self._on_click)
        buttons_layout.addWidget(self.send_confirm)
        buttons_layout.addWidget(self.send_cancel)

        layout.addLayout(buttons_layout)

    def sending_page(self):
        self._stop_threads()
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

        body = match_body_by_path(self.current_image_path or "") or next(iter(BODIES.values()))
        self.sender_thread = AudioSenderThread(image_id=body.id, parent=self)
        self.sender_thread.finished.connect(self.finish_page)
        self.sender_thread.start()

    def receive_page(self):
        self._stop_threads()
        central = self.create_page_central()
        layout = self.create_layout(central)

        label = QLabel("Ожидаем...")
        label.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.receive_cancel = self.create_button("Назад", self._on_click)

        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.receive_cancel, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.receiver_thread = AudioReceiverThread(parent=self)
        self.receiver_thread.received.connect(self._on_received)
        self.receiver_thread.start()

    def _on_received(self, image_id: str):
        body = get_body(image_id) or next(iter(BODIES.values()))
        self.current_image_path = str(body.file_path)
        self.finish_page()

    def receiving_page(self):
        central = self.create_page_central()
        layout = self.create_layout(central)

        h_layout = QHBoxLayout()
        self.receive_spinner = QProgressBar()
        self.receive_spinner.setRange(0, 0)
        self.receive_spinner.setFixedSize(200, 4)
        self.receive_spinner.setTextVisible(False)

        h_layout.addStretch()
        h_layout.addWidget(self.receive_spinner)
        h_layout.addStretch()

        label = QLabel("Получение...")
        label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.receive_abort = self.create_button("Отмена", self._on_click)

        layout.addLayout(h_layout)
        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.receive_abort, alignment=Qt.AlignmentFlag.AlignHCenter)

    def finish_page(self):
        self._stop_threads()
        central = self.create_page_central()
        layout = self.create_layout(central)

        label = QLabel("Готово!")
        label.setStyleSheet("font-size: 18px; font-weight: bold;")

        finish_image = QLabel("Изображение")
        finish_image.setFixedSize(180, 180)
        finish_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        finish_image.setStyleSheet("border: 1px solid gray;")

        if self.current_image_path:
            pixmap = QPixmap(self.current_image_path)
            if not pixmap.isNull():
                finish_image.setPixmap(pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        self.finish_button = self.create_button("В меню", self._on_click)

        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(finish_image, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.finish_button, alignment=Qt.AlignmentFlag.AlignHCenter)

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
            images_dir = str(get_images_dir())
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Выберите файл", images_dir, "Изображения (*.png *.jpg *.jpeg *.bmp);;Все файлы (*)"
            )
            if file_path:
                self.current_image_path = file_path
                self.send_page()
        elif sender == self.receive:
            self.receive_page()
        elif sender == getattr(self, "send_confirm", None):
            self.sending_page()
        elif sender in (
            getattr(self, "send_cancel", None),
            getattr(self, "send_abort", None),
            getattr(self, "receive_cancel", None),
            getattr(self, "receive_abort", None),
            getattr(self, "finish_button", None),
        ):
            self.main_page()