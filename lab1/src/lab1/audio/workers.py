import time

import sounddevice as sd
from PySide6.QtCore import QThread, Signal

from lab1.core.dtmf import SAMPLE_RATE
from lab1.core.protocol import PacketDecoder, encode_packet


class AudioSenderThread(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, image_id: str, volume: int = 80, parent=None):
        super().__init__(parent)
        self.image_id = image_id
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True
        try:
            sd.stop()
        except Exception:
            pass

    def run(self):
        try:
            self.status.emit("Формирование тонального пакета...")
            audio_signal = encode_packet(self.image_id, sample_rate=SAMPLE_RATE, amplitude=0.75)
            duration = len(audio_signal) / SAMPLE_RATE

            self.status.emit(f"Передача DTMF-сигнала ({duration:.1f} сек)...")
            sd.play(audio_signal, samplerate=SAMPLE_RATE)

            start_time = time.time()
            while not self._is_aborted:
                elapsed = time.time() - start_time
                percent = min(99, int((elapsed / duration) * 100))
                self.progress.emit(percent)

                if elapsed >= duration:
                    break
                time.sleep(0.03)

            if self._is_aborted:
                self.status.emit("Отправка отменена.")
                return

            sd.wait()
            self.progress.emit(100)
            self.status.emit("Сигнал успешно отправлен!")
            self.finished.emit()

        except Exception as exc:
            self.error.emit(f"Ошибка воспроизведения звука: {exc}")


class AudioReceiverThread(QThread):
    status = Signal(str)
    received = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_running = True
        self.decoder = PacketDecoder(sample_rate=SAMPLE_RATE)

    def stop(self):
        self._is_running = False

    def run(self):
        stream = None
        try:
            self.decoder.reset()
            self.status.emit("Слушаем эфир через микрофон...")
            block_size = 1024
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=block_size,
            )
            stream.start()

            while self._is_running:
                data, overflowed = stream.read(block_size)
                if not self._is_running:
                    break

                chunk = data[:, 0]
                result = self.decoder.process_chunk(chunk)
                if result:
                    self.status.emit(f"Принят сигнал: {result}!")
                    self.received.emit(result)
                    self.finished.emit()
                    return

        except Exception as exc:
            if self._is_running:
                self.error.emit(f"Ошибка микрофона: {exc}")
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
