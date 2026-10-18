import time
import zlib
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QThread, Signal

from lab1.core.protocol import (
    BLOCK_SIZE,
    CHUNK_PAYLOAD_SIZE,
    DEFAULT_PROTOCOL_ID,
    SAMPLE_RATE,
    AudioPacketDecoder,
    compress_data,
    decompress_data,
    encode_to_audio,
    make_ack_packet,
    make_data_packet,
    make_end_packet,
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
        volume: int = 70,
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
            time.sleep(0.04)
        sd.wait()
        return not self._is_aborted

    def _wait_for_ack(self, expected_seq: int, timeout_sec: float = 2.8) -> bool:
        """Listens for an ACK packet matching expected_seq within timeout."""
        if self._is_aborted:
            return False

        decoder = AudioPacketDecoder()
        stream = None
        start_time = time.time()
        ack_found = False

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
                if pkt and pkt.get("type") == "ACK" and pkt.get("seq") == expected_seq:
                    ack_found = True
                    break

        except Exception as exc:
            if not self._is_aborted:
                self.error.emit(f"Ошибка микрофона при ожидании ACK: {exc}")
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            decoder.close()

        return ack_found

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

            chunks = [
                compressed_data[i : i + CHUNK_PAYLOAD_SIZE]
                for i in range(0, len(compressed_data), CHUNK_PAYLOAD_SIZE)
            ]
            if not chunks:
                chunks = [b""]

            total_chunks = len(chunks)

            # Build sequence: START (seq 0), DATA (seq 1..N), END (seq N+1)
            packets = []
            packets.append(
                (0, make_start_packet(total_chunks, orig_size, is_comp, file_crc32, path.name), "заголовка")
            )
            for seq, chunk in enumerate(chunks, 1):
                packets.append((seq, make_data_packet(seq, chunk), f"пакета {seq}/{total_chunks}"))
            packets.append((total_chunks + 1, make_end_packet(total_chunks), "завершения"))

            total_packets = len(packets)
            max_retries = 6

            for pkt_idx, (seq, pkt_bytes, label) in enumerate(packets):
                if self._is_aborted:
                    self.status.emit("Передача отменена.")
                    return

                waveform = encode_to_audio(pkt_bytes, protocol_id=self.protocol_id, volume=self.volume)
                delivered = False

                for attempt in range(1, max_retries + 1):
                    if self._is_aborted:
                        return

                    if attempt == 1:
                        if seq == 0:
                            self.status.emit(f"Передача заголовка ({comp_summary}, {total_chunks} пак.)...")
                        else:
                            self.status.emit(f"Передача {label}...")
                    else:
                        self.status.emit(f"Шум: повтор {label} (попытка {attempt}/{max_retries})...")

                    if not self._play_samples(waveform):
                        return

                    # Guard interval against room reverberation
                    time.sleep(0.15)

                    if self._wait_for_ack(seq, timeout_sec=2.8):
                        delivered = True
                        break

                if not delivered:
                    self.error.emit(f"Не удалось получить подтверждение для {label}. Проверьте микрофон.")
                    return

                self.progress.emit(min(100, int(((pkt_idx + 1) / total_packets) * 100)))

            if not self._is_aborted:
                self.status.emit("Файл успешно передан!")
                self.progress.emit(100)
                self.success.emit()

        except Exception as exc:
            self.error.emit(f"Ошибка передачи файла: {exc}")


class AudioReceiverThread(QThread):
    progress = Signal(int)
    status = Signal(str)
    received = Signal(str)
    error = Signal(str)

    def __init__(self, save_dir: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.save_dir = save_dir
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
                    if idle_ticks % 30 == 0:
                        dots = "." * ((idle_ticks // 30) % 4)
                        self.status.emit(f"Слушаем эфир через микрофон{dots}")

                pkt = decoder.decode_chunk(data[:, 0])
                if not pkt:
                    continue

                ptype = pkt.get("type")

                # START packet
                if ptype == "START":
                    file_meta = pkt
                    total_chunks = pkt["total_chunks"]
                    received_chunks.clear()

                    self.status.emit(f"Входящий: {pkt['filename']} ({pkt['orig_size']} Б, {total_chunks} пак.)...")
                    self.progress.emit(0)

                    # Send ACK(0)
                    ack_audio = encode_to_audio(make_ack_packet(0), volume=70)
                    sd.play(ack_audio, samplerate=SAMPLE_RATE)
                    sd.wait()
                    time.sleep(0.15)
                    decoder.reset()

                # DATA packet
                elif ptype == "DATA":
                    seq = pkt["seq"]
                    if seq not in received_chunks:
                        received_chunks[seq] = pkt["data"]
                        percent = int((len(received_chunks) / max(1, total_chunks + 1)) * 100)
                        self.progress.emit(percent)
                        self.status.emit(f"Принят пакет {seq}/{total_chunks}...")

                    # Send ACK(seq)
                    ack_audio = encode_to_audio(make_ack_packet(seq), volume=70)
                    sd.play(ack_audio, samplerate=SAMPLE_RATE)
                    sd.wait()
                    time.sleep(0.15)
                    decoder.reset()

                # END packet
                elif ptype == "END":
                    # Send ACK(total_chunks + 1)
                    ack_audio = encode_to_audio(make_ack_packet(total_chunks + 1), volume=70)
                    sd.play(ack_audio, samplerate=SAMPLE_RATE)
                    sd.wait()

                    if len(received_chunks) >= total_chunks:
                        raw_payload = b"".join(received_chunks[i] for i in range(1, total_chunks + 1))
                        file_data = decompress_data(raw_payload, file_meta.get("is_comp", False))

                        # Verify CRC32
                        if zlib.crc32(file_data) == file_meta.get("file_crc32"):
                            clean_name = Path(file_meta.get("filename", "file.bin")).name
                            save_path = target_dir / clean_name

                            # Avoid overwriting
                            if save_path.exists():
                                stem, suffix = save_path.stem, save_path.suffix
                                counter = 1
                                while save_path.exists():
                                    save_path = target_dir / f"{stem}_{counter}{suffix}"
                                    counter += 1

                            save_path.write_bytes(file_data)
                            if self._is_running:
                                self.progress.emit(100)
                                self.status.emit(f"Файл сохранён: {save_path.name}")
                                self.received.emit(str(save_path.resolve()))
                            return
                        else:
                            if self._is_running:
                                self.error.emit("Ошибка CRC32 файла: не совпала контрольная сумма.")
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
            decoder.close()
