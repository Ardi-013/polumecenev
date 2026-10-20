import time
import zlib
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QThread, Signal

from lab1.core.protocol import (
    AUDIO_POLL_INTERVAL_SEC,
    BLOCK_SIZE,
    CHUNK_PAYLOAD_SIZE,
    DEFAULT_PROTOCOL_ID,
    DEFAULT_VOLUME,
    HALF_DUPLEX_GUARD_SEC,
    INTER_PACKET_GUARD_SEC,
    MAX_NACK_ATTEMPTS,
    RECEIVER_IDLE_DOTS_INTERVAL_TICKS,
    RECEIVER_IDLE_DOTS_MAX_COUNT,
    RECV_RESPONSE_TIMEOUT_SEC,
    SAMPLE_RATE,
    AudioPacketDecoder,
    compress_data,
    decompress_data,
    encode_to_audio,
    make_data_packet,
    make_done_packet,
    make_end_packet,
    make_nack_packet,
    make_start_packet,
)


class AudioSenderThread(QThread):
    progress = Signal(int)
    status = Signal(str)
    success = Signal()
    error = Signal(str)

    def __init__(
        self,
        file_path: str,
        volume: int = DEFAULT_VOLUME,
        protocol_id: int = DEFAULT_PROTOCOL_ID,
        parent=None,
    ):
        super().__init__(parent)
        self.file_path = file_path
        self.volume = volume
        self.protocol_id = protocol_id
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True
        try:
            sd.stop()
        except Exception:
            pass

    def _play_samples(self, samples: np.ndarray) -> bool:
        """Plays audio samples while allowing graceful cancellation."""
        if self._is_aborted or len(samples) == 0:
            return False
        sd.play(samples, samplerate=SAMPLE_RATE)
        while sd.get_stream() and sd.get_stream().active:
            if self._is_aborted:
                sd.stop()
                return False
            time.sleep(AUDIO_POLL_INTERVAL_SEC)
        sd.wait()
        return not self._is_aborted

    def _listen_for_response(
        self,
        timeout_sec: float = RECV_RESPONSE_TIMEOUT_SEC,
    ) -> Optional[Dict[str, Any]]:
        """Listens for an incoming ACK:DONE or NACK packet from receiver."""
        if self._is_aborted:
            return None

        decoder = AudioPacketDecoder()
        stream = None
        start_time = time.time()
        response_pkt = None

        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
            )
            stream.start()

            while not self._is_aborted and (time.time() - start_time) < timeout_sec:
                data, _ = stream.read(BLOCK_SIZE)
                if self._is_aborted:
                    break

                pkt = decoder.decode_chunk(data[:, 0])
                if pkt and pkt.get("type") in ("ACK_DONE", "NACK"):
                    response_pkt = pkt
                    break

        except Exception as exc:
            if not self._is_aborted:
                print(f"[Sender] Предупреждение микрофона: {exc}")
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            decoder.close()

        return response_pkt

    def run(self):
        try:
            path = Path(self.file_path)
            if not path.is_file():
                self.error.emit(f"Файл не найден: {self.file_path}")
                return

            self.status.emit(f"Чтение и сжатие {path.name}...")
            raw_data = path.read_bytes()
            orig_size = len(raw_data)

            compressed_data, is_comp = compress_data(raw_data)
            comp_size = len(compressed_data)
            file_crc32 = zlib.crc32(raw_data)

            if is_comp:
                ratio = int((1.0 - (comp_size / max(1, orig_size))) * 100)
                comp_summary = f"{orig_size} Б -> {comp_size} Б (-{ratio}%, brotli)"
            else:
                comp_summary = f"{orig_size} Б"

            raw_chunks = [
                compressed_data[i : i + CHUNK_PAYLOAD_SIZE]
                for i in range(0, len(compressed_data), CHUNK_PAYLOAD_SIZE)
            ]
            if not raw_chunks:
                raw_chunks = [b""]

            total_chunks = len(raw_chunks)
            chunk_map = {seq: chunk for seq, chunk in enumerate(raw_chunks, 1)}

            # Подготовка звуковых волн
            start_pkt = make_start_packet(total_chunks, orig_size, is_comp, file_crc32, path.name)
            start_waveform = encode_to_audio(start_pkt, protocol_id=self.protocol_id, volume=self.volume)

            end_pkt = make_end_packet(total_chunks)
            end_waveform = encode_to_audio(end_pkt, protocol_id=self.protocol_id, volume=self.volume)

            # --- Шаг 1: Отправка всех пакетов файла потоком ---
            self.status.emit(f"Передача заголовка ({comp_summary}, {total_chunks} пак.)...")
            self.progress.emit(0)

            if not self._play_samples(start_waveform):
                return
            time.sleep(INTER_PACKET_GUARD_SEC)

            for seq in range(1, total_chunks + 1):
                if self._is_aborted:
                    self.status.emit("Передача отменена.")
                    return

                self.status.emit(f"Передача пакета {seq}/{total_chunks}...")
                chunk_wave = encode_to_audio(
                    make_data_packet(seq, chunk_map[seq]),
                    protocol_id=self.protocol_id,
                    volume=self.volume,
                )
                if not self._play_samples(chunk_wave):
                    return

                percent = min(85, int((seq / total_chunks) * 85))
                self.progress.emit(percent)
                time.sleep(INTER_PACKET_GUARD_SEC)

            # Отправляем один пакет завершения END
            self.status.emit("Завершение передачи (пакет END)...")
            if not self._play_samples(end_waveform):
                return

            # --- Шаг 2: Ожидание ответа приёмника (NACK или ACK:DONE) ---
            for attempt in range(1, MAX_NACK_ATTEMPTS + 1):
                if self._is_aborted:
                    return

                self.status.emit(f"Ожидание ответа приёмника (проверка {attempt}/{MAX_NACK_ATTEMPTS})...")
                self.progress.emit(85 + attempt * 3)

                resp = self._listen_for_response(timeout_sec=RECV_RESPONSE_TIMEOUT_SEC)

                if resp and resp.get("type") == "ACK_DONE":
                    self.status.emit("Файл успешно передан и подтверждён приёмником!")
                    self.progress.emit(100)
                    self.success.emit()
                    return

                elif resp and resp.get("type") == "NACK":
                    missing = resp.get("missing", [])
                    if not missing:
                        self.status.emit("Файл успешно передан и подтверждён приёмником!")
                        self.progress.emit(100)
                        self.success.emit()
                        return

                    self.status.emit(f"Принят NACK: досылаем пакеты {missing}...")
                    time.sleep(HALF_DUPLEX_GUARD_SEC)

                    # Досылаем строго недостающие пакеты
                    for seq in missing:
                        if self._is_aborted:
                            return
                        if seq in chunk_map:
                            retry_wave = encode_to_audio(
                                make_data_packet(seq, chunk_map[seq]),
                                protocol_id=self.protocol_id,
                                volume=self.volume,
                            )
                            if not self._play_samples(retry_wave):
                                return
                            time.sleep(INTER_PACKET_GUARD_SEC)

                    # Завершаем досылку пакетом END
                    if not self._play_samples(end_waveform):
                        return

                else:
                    # Таймаут ожидания ответа
                    if attempt < MAX_NACK_ATTEMPTS:
                        self.status.emit("Повторный запрос статуса (пакет END)...")
                        time.sleep(HALF_DUPLEX_GUARD_SEC)
                        if not self._play_samples(end_waveform):
                            return
                    else:
                        self.status.emit("Все пакеты переданы. Проверьте статус на втором ноутбуке.")
                        self.progress.emit(100)
                        self.success.emit()
                        return

        except Exception as exc:
            self.error.emit(f"Ошибка передачи файла: {exc}")


class AudioReceiverThread(QThread):
    progress = Signal(int)
    status = Signal(str)
    received = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        save_dir: Optional[str] = None,
        volume: int = DEFAULT_VOLUME,
        protocol_id: int = DEFAULT_PROTOCOL_ID,
        parent=None,
    ):
        super().__init__(parent)
        self.save_dir = save_dir
        self.volume = volume
        self.protocol_id = protocol_id
        self._is_running = True

    def stop(self):
        self._is_running = False
        try:
            sd.stop()
        except Exception:
            pass

    def run(self):
        stream = None
        decoder = AudioPacketDecoder()

        target_dir = Path(self.save_dir) if self.save_dir else Path.cwd() / "received_files"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        try:
            self.status.emit("Слушаем эфир через микрофон...")
            self.progress.emit(0)

            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
            )
            stream.start()

            total_chunks: int = 0
            file_meta: dict = {}
            received_chunks: dict[int, bytes] = {}
            idle_ticks: int = 0

            while self._is_running:
                data, _ = stream.read(BLOCK_SIZE)
                if not self._is_running:
                    break

                if not file_meta:
                    idle_ticks += 1
                    if idle_ticks % RECEIVER_IDLE_DOTS_INTERVAL_TICKS == 0:
                        dots = "." * ((idle_ticks // RECEIVER_IDLE_DOTS_INTERVAL_TICKS) % RECEIVER_IDLE_DOTS_MAX_COUNT)
                        self.status.emit(f"Слушаем эфир через микрофон{dots}")

                pkt = decoder.decode_chunk(data[:, 0])
                if not pkt:
                    continue

                ptype = pkt.get("type")

                # START packet
                if ptype == "START":
                    file_meta = pkt
                    total_chunks = pkt["total_chunks"]
                    self.status.emit(f"Входящий: {pkt['filename']} ({pkt['orig_size']} Б, {total_chunks} пак.)...")
                    self.progress.emit(5)

                # DATA packet
                elif ptype == "DATA":
                    seq = pkt["seq"]
                    received_chunks[seq] = pkt["data"]
                    percent = min(85, int((len(received_chunks) / max(1, total_chunks)) * 85))
                    self.progress.emit(percent)
                    self.status.emit(f"Принят пакет {seq}/{total_chunks} (получено: {len(received_chunks)})...")

                # END packet: отправитель закончил раунд и ждёт наш вердикт
                elif ptype == "END":
                    if total_chunks == 0:
                        continue

                    # Пауза тишины (Half-Duplex Guard): ждём, чтобы комната затихла,
                    # а отправитель гарантированно закончил воспроизведение и включил микрофон
                    time.sleep(HALF_DUPLEX_GUARD_SEC)

                    missing = [i for i in range(1, total_chunks + 1) if i not in received_chunks]

                    if not missing:
                        # Все пакеты собраны без потерь
                        raw_payload = b"".join(received_chunks[i] for i in range(1, total_chunks + 1))
                        file_data = decompress_data(raw_payload, file_meta.get("is_comp", False))

                        if zlib.crc32(file_data) == file_meta.get("file_crc32"):
                            clean_name = Path(file_meta.get("filename", "file.bin")).name
                            save_path = target_dir / clean_name

                            if save_path.exists():
                                stem, suffix = save_path.stem, save_path.suffix
                                counter = 1
                                while save_path.exists():
                                    save_path = target_dir / f"{stem}_{counter}{suffix}"
                                    counter += 1

                            save_path.write_bytes(file_data)

                            if self._is_running:
                                self.progress.emit(100)
                                self.status.emit(f"Файл сохранён: {save_path.name}! Отправка подтверждения...")

                            # Останавливаем запись и громко один раз пищим ACK:DONE
                            try:
                                stream.stop()
                            except Exception:
                                pass

                            done_audio = encode_to_audio(make_done_packet(), protocol_id=self.protocol_id, volume=100)
                            sd.play(done_audio, samplerate=SAMPLE_RATE)
                            sd.wait()

                            if self._is_running:
                                self.status.emit(f"Успешно сохранён: {save_path.name}")
                                self.received.emit(str(save_path.resolve()))
                            return
                        else:
                            if self._is_running:
                                self.error.emit("Ошибка CRC32 файла: не совпала контрольная сумма.")
                            return
                    else:
                        # Не хватает одного или нескольких пакетов — отправляем NACK
                        if self._is_running:
                            self.status.emit(f"Пропущено {len(missing)} пак. Запрос досылки: {missing[:5]}...")

                        try:
                            stream.stop()
                        except Exception:
                            pass

                        nack_audio = encode_to_audio(make_nack_packet(missing), protocol_id=self.protocol_id, volume=100)
                        sd.play(nack_audio, samplerate=SAMPLE_RATE)
                        sd.wait()

                        # Возобновляем прослушивание для приёма досылаемых пакетов
                        if self._is_running:
                            time.sleep(0.1)
                            try:
                                stream.start()
                                while stream.read_available > 0:
                                    stream.read(min(stream.read_available, BLOCK_SIZE))
                            except Exception:
                                pass
                            decoder.reset()

        except Exception as exc:
            if self._is_running:
                self.error.emit(f"Ошибка приёма: {exc}")
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            decoder.close()
