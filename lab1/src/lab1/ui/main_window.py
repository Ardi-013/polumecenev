from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Лабораторная 1")
        self.resize(500, 350)

        # Корневой контейнер
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Вертикальная раскладка
        layout = QVBoxLayout(central_widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)
        
        self.send = QPushButton("Отправить")
        self.send.setFixedSize(140, 36)
        self.send.clicked.connect(self._on_click)

        self.recieve = QPushButton("Получить")
        self.recieve.setFixedSize(140, 36)
        self.recieve.clicked.connect(self._on_click)        

        layout.addWidget(self.send, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.recieve, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _on_click(self):
        sender = self.sender()
        if sender == self.send:
            print("Отправка данных...")
        elif sender == self.recieve:
            print("Получение данных...")