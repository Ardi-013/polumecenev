import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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
from lab1.core.protocol import CHUNK_PAYLOAD_SIZE, compress_data

if sys.platform == "win32":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("lab1.audio.FileSoundApp.1")


def get_icon_path() -> str:
    if hasattr(sys, "_MEIPASS"):
        exe_icon = Path(sys._MEIPASS) / "icon.ico"
        if exe_icon.exists():
            return str(exe_icon)

    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        candidate = parent / "icon.ico"
        if candidate.exists():
            return str(candidate)

    return str(Path.cwd() / "icon.ico")


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Лабораторная 1")
        self.resize(540, 420)

        icon_path = get_icon_path()
        if Path(icon_path).exists():
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)
            app = QApplication.instance()
            if app is not None:
                app.setWindowIcon(app_icon)

        self.current_image_path: Optional[str] = None
        self.current_role: Optional[str] = None
        self.is_sending: bool = False
        self.sender_thread: Optional[AudioSenderThread] = None
        self.receiver_thread: Optional[AudioReceiverThread] = None

        self.send_label: Optional[QLabel] = None
        self.receive_label: Optional[QLabel] = None

        self.current_theme = "purple"
        self.apply_theme()
        self.main_page()

    def apply_theme(self):
        if self.current_theme == "purple":
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #161324;
                }
                QLabel {
                    color: #e2dcf0;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }
                QPushButton {
                    background-color: #26203a;
                    color: #dcd3f0;
                    border: 1px solid #453a66;
                    border-radius: 9px;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 4px 10px;
                }
                QPushButton:hover {
                    background-color: #322a4d;
                    border-color: #6c5b9e;
                    color: #f2eefc;
                }
                QPushButton:pressed {
                    background-color: #1d182e;
                }
                QProgressBar {
                    background-color: #241e38;
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #8c7ab8;
                    border-radius: 3px;
                }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #fdf6f8;
                }
                QLabel {
                    color: #5c3a47;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }
                QPushButton {
                    background-color: #f9e8ee;
                    color: #6e4455;
                    border: 1px solid #e6c5d0;
                    border-radius: 9px;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 4px 10px;
                }
                QPushButton:hover {
                    background-color: #f3d8e2;
                    border-color: #d9adb9;
                    color: #52303e;
                }
                QPushButton:pressed {
                    background-color: #e8c6d2;
                }
                QProgressBar {
                    background-color: #f2dce4;
                    border: none;
                    border-radius: 3px;
                }
                QProgressBar::chunk {
                    background-color: #d996a8;
                    border-radius: 3px;
                }
            """)

    def style_accent_button(self, button: QPushButton):
        if self.current_theme == "purple":
            button.setStyleSheet("""
                QPushButton {
                    background-color: #5b4b8a;
                    border: 1px solid #7866ad;
                    color: #f4f0ff;
                }
                QPushButton:hover {
                    background-color: #6c5a9e;
                    border-color: #8e7cc2;
                }
                QPushButton:pressed {
                    background-color: #493b70;
                }
            """)
        else:
            button.setStyleSheet("""
                QPushButton {
                    background-color: #eab8c6;
                    border: 1px solid #dca1b2;
                    color: #522d3b;
                }
                QPushButton:hover {
                    background-color: #e2a5b6;
                    border-color: #cf8e9f;
                }
                QPushButton:pressed {
                    background-color: #d495a7;
                }
            """)

    def style_image_frame(self, label: QLabel):
        if self.current_theme == "purple":
            label.setStyleSheet("""
                border: 2px dashed #4a3e6d;
                border-radius: 12px;
                background-color: #1e1930;
                color: #9689b3;
                font-size: 13px;
            """)
        else:
            label.setStyleSheet("""
                border: 2px dashed #e2bcc8;
                border-radius: 12px;
                background-color: #ffffff;
                color: #9e7584;
                font-size: 13px;
            """)

    def closeEvent(self, event: QCloseEvent):
        self._stop_threads()
        super().closeEvent(event)

    def _stop_threads(self):
        if self.sender_thread:
            try:
                self.sender_thread.success.disconnect()
            except Exception:
                pass
            try:
                self.sender_thread.status.disconnect()
            except Exception:
                pass
            try:
                self.sender_thread.error.disconnect()
            except Exception:
                pass
            try:
                self.sender_thread.progress.disconnect()
            except Exception:
                pass
            if self.sender_thread.isRunning():
                self.sender_thread.abort()
                self.sender_thread.wait(1000)
            self.sender_thread = None

        if self.receiver_thread:
            try:
                self.receiver_thread.received.disconnect()
            except Exception:
                pass
            try:
                self.receiver_thread.status.disconnect()
            except Exception:
                pass
            try:
                self.receiver_thread.error.disconnect()
            except Exception:
                pass
            try:
                self.receiver_thread.progress.disconnect()
            except Exception:
                pass
            if self.receiver_thread.isRunning():
                self.receiver_thread.stop()
                self.receiver_thread.wait(1000)
            self.receiver_thread = None

    def main_page(self):
        self._stop_threads()
        self.current_role = None
        self.is_sending = False
        central = self.create_page_central()
        layout = self.create_layout(central)

        self.send = self.create_button("Отправить", self._on_click)
        self.receive = self.create_button("Получить", self._on_click)
        self.style_accent_button(self.send)

        theme_title = "🌸 Розовая тема" if self.current_theme == "purple" else "🌙 Фиолетовая тема"
        self.theme_btn = self.create_button(theme_title, self._on_click)
        self.theme_btn.setFixedSize(160, 36)

        layout.addWidget(self.send, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.receive, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.theme_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

    def send_page(self):
        central = self.create_page_central()
        layout = self.create_layout(central, horizontal=True)

        image = QLabel("Файл")
        image.setFixedSize(180, 180)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setWordWrap(True)
        self.style_image_frame(image)

        if self.current_image_path:
            p = Path(self.current_image_path)
            raw_bytes = p.read_bytes() if p.is_file() else b""
            comp_bytes, is_comp = compress_data(raw_bytes)
            chunk_cnt = max(1, (len(comp_bytes) + CHUNK_PAYLOAD_SIZE - 1) // CHUNK_PAYLOAD_SIZE)

            pixmap = QPixmap(self.current_image_path)
            if not pixmap.isNull():
                image.setPixmap(
                    pixmap.scaled(
                        180, 180,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            else:
                if is_comp:
                    savings = int((1.0 - (len(comp_bytes) / max(1, len(raw_bytes)))) * 100)
                    image.setText(f"{p.name}\n\n{len(raw_bytes)} Б -> {len(comp_bytes)} Б\n(-{savings}%, brotli)\nПакеты: {chunk_cnt}")
                else:
                    image.setText(f"{p.name}\n\n{len(raw_bytes)} байт\n(без сжатия)\nПакеты: {chunk_cnt}")

        layout.addWidget(image)

        buttons_layout = self.create_layout()
        self.send_confirm = self.create_button("Отправить", self._on_click)
        self.send_cancel = self.create_button("Назад", self._on_click)
        self.style_accent_button(self.send_confirm)

        buttons_layout.addWidget(self.send_confirm)
        buttons_layout.addWidget(self.send_cancel)

        layout.addLayout(buttons_layout)

    def sending_page(self):
        self._stop_threads()
        central = self.create_page_central()
        layout = self.create_layout(central)

        h_layout = QHBoxLayout()
        self.send_spinner = QProgressBar()
        self.send_spinner.setRange(0, 100)
        self.send_spinner.setValue(0)
        self.send_spinner.setFixedSize(220, 6)
        self.send_spinner.setTextVisible(False)

        h_layout.addStretch()
        h_layout.addWidget(self.send_spinner)
        h_layout.addStretch()

        title_color = "#e2dcf0" if self.current_theme == "purple" else "#5c3a47"
        self.send_label = QLabel("Подготовка к отправке...")
        self.send_label.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {title_color};")
        self.send_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.send_label.setWordWrap(True)

        self.send_abort = self.create_button("Отмена", self._on_click)

        layout.addLayout(h_layout)
        layout.addWidget(self.send_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.send_abort, alignment=Qt.AlignmentFlag.AlignHCenter)

        if self.current_image_path:
            self.sender_thread = AudioSenderThread(file_path=self.current_image_path, parent=self)
            self.sender_thread.status.connect(self._on_sender_status)
            self.sender_thread.progress.connect(self.send_spinner.setValue)
            self.sender_thread.success.connect(self._on_send_success)
            self.sender_thread.error.connect(self._on_sender_error)
            self.sender_thread.start()

    def _on_sender_status(self, text: str):
        if self.send_label:
            self.send_label.setText(text)

    def _on_sender_error(self, text: str):
        if self.send_label:
            self.send_label.setText(f"❌ {text}")
        if hasattr(self, "send_abort") and self.send_abort:
            self.send_abort.setText("Назад")

    def _on_send_success(self):
        if self.current_role == "sender":
            self.finish_page()

    def receive_page(self):
        self._stop_threads()
        central = self.create_page_central()
        layout = self.create_layout(central)

        h_layout = QHBoxLayout()
        self.receive_spinner = QProgressBar()
        self.receive_spinner.setRange(0, 100)
        self.receive_spinner.setValue(0)
        self.receive_spinner.setFixedSize(220, 6)
        self.receive_spinner.setTextVisible(False)

        h_layout.addStretch()
        h_layout.addWidget(self.receive_spinner)
        h_layout.addStretch()

        title_color = "#e2dcf0" if self.current_theme == "purple" else "#5c3a47"
        self.receive_label = QLabel("Ожидаем сигнал...")
        self.receive_label.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {title_color};")
        self.receive_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.receive_label.setWordWrap(True)

        self.receive_cancel = self.create_button("Назад", self._on_click)

        layout.addLayout(h_layout)
        layout.addWidget(self.receive_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.receive_cancel, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.receiver_thread = AudioReceiverThread(parent=self)
        self.receiver_thread.status.connect(self._on_receiver_status)
        self.receiver_thread.progress.connect(self.receive_spinner.setValue)
        self.receiver_thread.received.connect(self._on_received)
        self.receiver_thread.error.connect(self._on_receiver_error)
        self.receiver_thread.start()

    def _on_receiver_status(self, text: str):
        if self.receive_label:
            self.receive_label.setText(text)

    def _on_receiver_error(self, text: str):
        if self.receive_label:
            self.receive_label.setText(f"❌ {text}")

    def _on_received(self, file_path: str):
        if self.current_role == "receiver":
            self.current_image_path = file_path
            self.finish_page()

    def finish_page(self):
        self._stop_threads()
        central = self.create_page_central()
        layout = self.create_layout(central)

        title_color = "#b8a8e0" if self.current_theme == "purple" else "#a85c74"
        if self.current_role == "sender":
            title_text = "Файл успешно отправлен!"
            action_verb = "Отправлен"
        elif self.current_role == "receiver":
            title_text = "Файл успешно получен!"
            action_verb = "Получен"
        else:
            title_text = "Готово!"
            action_verb = "Файл"

        label = QLabel(title_text)
        label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {title_color};")

        finish_image = QLabel("Файл")
        finish_image.setFixedSize(180, 180)
        finish_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        finish_image.setWordWrap(True)
        self.style_image_frame(finish_image)

        info_label = None
        if self.current_image_path:
            p = Path(self.current_image_path)
            size_bytes = p.stat().st_size if p.is_file() else 0
            pixmap = QPixmap(self.current_image_path)
            if not pixmap.isNull():
                finish_image.setPixmap(
                    pixmap.scaled(
                        180, 180,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                info_color = "#e2dcf0" if self.current_theme == "purple" else "#5c3a47"
                info_label = QLabel(f"{p.name} ({size_bytes} байт)")
                info_label.setStyleSheet(f"font-size: 13px; color: {info_color};")
                info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                finish_image.setText(f"{action_verb}:\n{p.name}\n\n{size_bytes} байт")

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if self.current_role == "receiver":
            self.open_file_btn = self.create_button("Открыть файл", self._on_click)
            self.style_accent_button(self.open_file_btn)
            self.show_folder_btn = self.create_button("Показать в папке", self._on_click)
            self.finish_button = self.create_button("В меню", self._on_click)

            buttons_layout.addWidget(self.open_file_btn)
            buttons_layout.addWidget(self.show_folder_btn)
            buttons_layout.addWidget(self.finish_button)
        else:
            self.show_folder_btn = self.create_button("Показать в папке", self._on_click)
            self.finish_button = self.create_button("В меню", self._on_click)
            self.style_accent_button(self.finish_button)

            buttons_layout.addWidget(self.show_folder_btn)
            buttons_layout.addWidget(self.finish_button)

        layout.addWidget(label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(finish_image, alignment=Qt.AlignmentFlag.AlignHCenter)
        if info_label:
            layout.addWidget(info_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(buttons_layout)

    def _open_current_file(self):
        if not self.current_image_path:
            return
        p = Path(self.current_image_path).resolve()
        if not p.is_file():
            return
        try:
            os.startfile(str(p))
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _show_in_folder(self):
        if not self.current_image_path:
            return
        p = Path(self.current_image_path).resolve()
        if not p.exists():
            return
        try:
            subprocess.Popen(["explorer", f"/select,{p}"])
        except Exception:
            try:
                os.startfile(str(p.parent))
            except Exception:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

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
        if sender == getattr(self, "send", None):
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Выберите файл для передачи",
                "",
                "Все файлы (*.*);;Изображения (*.png *.jpg *.jpeg *.bmp)",
            )
            if file_path:
                self.current_role = "sender"
                self.is_sending = True
                self.current_image_path = file_path
                self.send_page()
        elif sender == getattr(self, "receive", None):
            self.current_role = "receiver"
            self.is_sending = False
            self.receive_page()
        elif sender == getattr(self, "theme_btn", None):
            self.current_theme = "pink" if self.current_theme == "purple" else "purple"
            self.apply_theme()
            self.main_page()
        elif sender == getattr(self, "send_confirm", None):
            self.sending_page()
        elif sender == getattr(self, "open_file_btn", None):
            self._open_current_file()
        elif sender == getattr(self, "show_folder_btn", None):
            self._show_in_folder()
        elif sender in (
            getattr(self, "send_cancel", None),
            getattr(self, "send_abort", None),
            getattr(self, "receive_cancel", None),
            getattr(self, "finish_button", None),
        ):
            self.main_page()