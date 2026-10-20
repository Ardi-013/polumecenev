from typing import Any, Dict, Optional, Tuple

import brotli
import ggwave
import numpy as np

# ==============================================================================
# Акустические и модемные параметры (Physical & Audio Layer)
# ==============================================================================
SAMPLE_RATE: int = 48000
BLOCK_SIZE: int = 1024
SAMPLES_PER_FRAME: int = 512
CHUNK_PAYLOAD_SIZE: int = 52
DEFAULT_PROTOCOL_ID: int = 1  # 1: Fast (быстрый режим: ~6 сек на файл с хорошим запасом)
DEFAULT_VOLUME: int = 95
DEFAULT_MARKER_THRESHOLD: float = 1.0

# ==============================================================================
# Сетевой протокол Stop-and-Wait ARQ и тайминги (Data Link / Transport Layer)
# ==============================================================================
MAX_PACKET_RETRIES: int = 8
ACK_TIMEOUT_SEC: float = 3.5
SENDER_POST_PLAY_GUARD_SEC: float = 0.05
RECEIVER_PRE_ACK_DELAY_SEC: float = 0.35
RECEIVER_POST_ACK_GUARD_SEC: float = 0.08
AUDIO_POLL_INTERVAL_SEC: float = 0.04

# ==============================================================================
# Сжатие и форматирование пакетов (Application / Framing Layer)
# ==============================================================================
BROTLI_COMPRESSION_QUALITY: int = 11
MAX_FILENAME_LENGTH: int = 40
MIN_PACKET_LENGTH: int = 5
START_PACKET_PARTS_COUNT: int = 6

# ==============================================================================
# Сервисные константы интерфейса
# ==============================================================================
RECEIVER_IDLE_DOTS_INTERVAL_TICKS: int = 30
RECEIVER_IDLE_DOTS_MAX_COUNT: int = 4

try:
    ggwave.disableLog()
except Exception:
    pass


def compress_data(data: bytes) -> Tuple[bytes, bool]:
    """Compresses data using Brotli with static dictionary, or returns raw bytes."""
    try:
        compressed = brotli.compress(data, quality=BROTLI_COMPRESSION_QUALITY)
        if len(compressed) < len(data):
            return compressed, True
    except Exception:
        pass
    return data, False


def decompress_data(data: bytes, is_compressed: bool) -> bytes:
    """Decompresses Brotli data or returns raw bytes."""
    if is_compressed:
        try:
            return brotli.decompress(data)
        except Exception:
            pass
    return data


# Clean, reliable packet formatting:
# START:total:orig_sz:is_comp:crc32:filename
# DATA:seq:<binary payload>
# ACK:seq
# END:total

def make_start_packet(total_chunks: int, orig_size: int, is_comp: bool, file_crc32: int, filename: str) -> bytes:
    clean_fn = filename.replace(":", "_")[:MAX_FILENAME_LENGTH]
    return f"START:{total_chunks}:{orig_size}:{1 if is_comp else 0}:{file_crc32}:{clean_fn}".encode("utf-8")


def make_data_packet(seq: int, chunk: bytes) -> bytes:
    return f"DATA:{seq}:".encode("ascii") + chunk


def make_ack_packet(seq: int) -> bytes:
    return f"ACK:{seq}".encode("ascii")


def make_end_packet(total_chunks: int) -> bytes:
    return f"END:{total_chunks}".encode("ascii")


def parse_packet(raw: Optional[bytes]) -> Optional[Dict[str, Any]]:
    """Unpacks any ggwave binary/text packet."""
    if not raw or len(raw) < MIN_PACKET_LENGTH:
        return None
    if raw.startswith(b"DATA:"):
        try:
            parts = raw.split(b":", 2)
            seq = int(parts[1])
            return {"type": "DATA", "seq": seq, "data": parts[2]}
        except Exception:
            return None
    elif raw.startswith(b"ACK:"):
        try:
            parts = raw.split(b":", 1)
            seq = int(parts[1])
            return {"type": "ACK", "seq": seq}
        except Exception:
            return None
    elif raw.startswith(b"END:"):
        try:
            parts = raw.split(b":", 1)
            total = int(parts[1])
            return {"type": "END", "total_chunks": total}
        except Exception:
            return None
    elif raw.startswith(b"START:"):
        try:
            parts = raw.decode("utf-8", errors="replace").split(":", 5)
            if len(parts) == START_PACKET_PARTS_COUNT:
                return {
                    "type": "START",
                    "total_chunks": int(parts[1]),
                    "orig_size": int(parts[2]),
                    "is_comp": parts[3] == "1",
                    "file_crc32": int(parts[4]),
                    "filename": parts[5],
                }
        except Exception:
            return None
    return None


def encode_to_audio(
    payload: bytes,
    protocol_id: int = DEFAULT_PROTOCOL_ID,
    volume: int = DEFAULT_VOLUME,
    samples_per_frame: int = SAMPLES_PER_FRAME,
) -> np.ndarray:
    """Encodes bytes into float32 audio samples using configured ggwave parameters."""
    params = ggwave.getDefaultParameters()
    params["samplesPerFrame"] = samples_per_frame
    inst = ggwave.init(params)
    try:
        raw_wave = ggwave.encode(payload, protocolId=protocol_id, volume=volume, instance=inst)
        if not raw_wave:
            return np.zeros(0, dtype=np.float32)
        return np.frombuffer(raw_wave, dtype=np.float32)
    finally:
        ggwave.free(inst)


class AudioPacketDecoder:
    """Wraps ggwave C decoder for streaming microphone processing."""

    def __init__(
        self,
        marker_threshold: float = DEFAULT_MARKER_THRESHOLD,
        samples_per_frame: int = SAMPLES_PER_FRAME,
    ):
        self.marker_threshold = marker_threshold
        self.samples_per_frame = samples_per_frame
        self._closed = False
        self.instance = None
        self.reset()

    def reset(self):
        if not self._closed and self.instance is not None:
            try:
                ggwave.free(self.instance)
            except Exception:
                pass
        try:
            params = ggwave.getDefaultParameters()
            params["samplesPerFrame"] = self.samples_per_frame
            params["soundMarkerThreshold"] = self.marker_threshold
            self.instance = ggwave.init(params)
        except Exception:
            self.instance = ggwave.init()

    def decode_chunk(self, chunk_samples: np.ndarray) -> Optional[Dict[str, Any]]:
        if self._closed or self.instance is None:
            return None
        raw = chunk_samples.astype(np.float32).tobytes()
        decoded = ggwave.decode(self.instance, raw)
        return parse_packet(decoded) if decoded else None

    def close(self):
        if not self._closed and self.instance is not None:
            try:
                ggwave.free(self.instance)
            except Exception:
                pass
            self.instance = None
            self._closed = True
