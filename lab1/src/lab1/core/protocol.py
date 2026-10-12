from typing import Dict, List, Optional

import numpy as np

from lab1.core.dtmf import SAMPLE_RATE, decode_window_key, make_dtmf_tone

BODY_TO_KEY: Dict[str, str] = {
    "sun": "1",
    "hourglass_twins": "2",
    "timber_hearth": "3",
    "attlerock": "4",
    "brittle_hollow": "5",
    "hollows_lantern": "6",
    "giants_deep": "7",
    "dark_bramble": "8",
    "interloper": "9",
    "quantum_moon": "0",
    "white_hole": "A",
    "the_stranger": "B",
}
KEY_TO_BODY: Dict[str, str] = {v: k for k, v in BODY_TO_KEY.items()}


def encode_packet(
    body_id: str,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.75,
) -> np.ndarray:
    """Encodes celestial body ID into a 3-tone acoustic DTMF frame [* - KEY - #]."""
    key = BODY_TO_KEY.get(body_id, "1")

    t_start = make_dtmf_tone("*", 0.18, sample_rate)
    silence = np.zeros(int(sample_rate * 0.08), dtype=np.float32)
    t_data = make_dtmf_tone(key, 0.24, sample_rate)
    t_end = make_dtmf_tone("#", 0.18, sample_rate)

    sig = np.concatenate([silence, t_start, silence, t_data, silence, t_end, silence])
    return (sig * amplitude).astype(np.float32)


class PacketDecoder:
    """Stateful stream decoder for acoustic DTMF frames with anti-jitter and debouncing."""

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.buffer = np.zeros(0, dtype=np.float32)
        self.confirmed_events: List[str] = []
        self.candidate_key: Optional[str] = None
        self.candidate_count: int = 0
        self.silence_count: int = 0

    def reset(self):
        self.buffer = np.zeros(0, dtype=np.float32)
        self.confirmed_events.clear()
        self.candidate_key = None
        self.candidate_count = 0
        self.silence_count = 0

    def process_chunk(self, chunk: np.ndarray) -> Optional[str]:
        """Processes incoming audio chunk and returns detected body ID if frame completed."""
        self.buffer = np.concatenate([self.buffer, chunk])
        win_size = int(self.sample_rate * 0.06)  # 60ms window
        hop = int(self.sample_rate * 0.02)       # 20ms hop

        while len(self.buffer) >= win_size:
            w = self.buffer[:win_size]
            k = decode_window_key(w, self.sample_rate)

            if k is None:
                self.silence_count += 1
            else:
                self.silence_count = 0

            if k == self.candidate_key:
                self.candidate_count += 1
            else:
                self.candidate_key = k
                self.candidate_count = 1

            # Debouncing: tone must persist for at least 2 consecutive windows (40ms)
            if self.candidate_count == 2 and self.candidate_key is not None:
                if not self.confirmed_events or self.confirmed_events[-1] != self.candidate_key:
                    self.confirmed_events.append(self.candidate_key)

                    # Condition A: Frame completed by '#' marker
                    for idx in range(len(self.confirmed_events) - 1, -1, -1):
                        if self.confirmed_events[idx] == "*":
                            keys_after = [x for x in self.confirmed_events[idx + 1 :] if x != "*"]
                            if "#" in keys_after:
                                data_keys = [x for x in keys_after if x != "#"]
                                if data_keys and data_keys[-1] in KEY_TO_BODY:
                                    body_id = KEY_TO_BODY[data_keys[-1]]
                                    self.reset()
                                    return body_id
                            break

            # Condition B: Fallback if '#' was muffled, but '*' + DATA were confirmed followed by silence
            if self.silence_count >= 8 and len(self.confirmed_events) >= 2:
                for idx in range(len(self.confirmed_events) - 1, -1, -1):
                    if self.confirmed_events[idx] == "*":
                        data_keys = [x for x in self.confirmed_events[idx + 1 :] if x in KEY_TO_BODY]
                        if data_keys:
                            body_id = KEY_TO_BODY[data_keys[-1]]
                            self.reset()
                            return body_id
                        break

            self.buffer = self.buffer[hop:]

        max_buf = self.sample_rate * 2
        if len(self.buffer) > max_buf:
            self.buffer = self.buffer[-max_buf:]

        return None
