from typing import Dict, List, Optional, Tuple

import numpy as np

SAMPLE_RATE = 48000

# DTMF standard frequencies according to ITU-T Q.23
DTMF_LOW: List[int] = [697, 770, 852, 941]
DTMF_HIGH: List[int] = [1209, 1336, 1477, 1633]

DTMF_MAP: Dict[str, Tuple[int, int]] = {
    "1": (697, 1209),
    "2": (697, 1336),
    "3": (697, 1477),
    "A": (697, 1633),
    "4": (770, 1209),
    "5": (770, 1336),
    "6": (770, 1477),
    "B": (770, 1633),
    "7": (852, 1209),
    "8": (852, 1336),
    "9": (852, 1477),
    "C": (852, 1633),
    "*": (941, 1209),  # Frame start
    "0": (941, 1336),
    "#": (941, 1477),  # Frame end
    "D": (941, 1633),
}


def make_dtmf_tone(key: str, duration: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Generates a smooth DTMF dual-tone with a Hann envelope to prevent spectral splatter."""
    if key not in DTMF_MAP:
        raise ValueError(f"Unknown DTMF key: {key}")

    f_low, f_high = DTMF_MAP[key]
    n = int(sample_rate * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    envelope = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    tone = 0.5 * (np.sin(2 * np.pi * f_low * t) + np.sin(2 * np.pi * f_high * t))
    return tone * envelope


def goertzel(samples: np.ndarray, target_freq: float, sample_rate: int = SAMPLE_RATE) -> float:
    """Computes spectral power at target frequency with O(N) complexity."""
    n = len(samples)
    if n == 0:
        return 0.0
    k = int(0.5 + (n * target_freq) / sample_rate)
    omega = (2.0 * np.pi * k) / n
    coeff = 2.0 * np.cos(omega)
    q0 = q1 = q2 = 0.0
    for s in samples:
        q0 = coeff * q1 - q2 + s
        q2 = q1
        q1 = q0
    return float(q1 * q1 + q2 * q2 - q1 * q2 * coeff)


def decode_window_key(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Optional[str]:
    """Detects active DTMF key in an audio slice using dual-group peak dominance."""
    low_energies = {f: goertzel(samples, f, sample_rate) for f in DTMF_LOW}
    high_energies = {f: goertzel(samples, f, sample_rate) for f in DTMF_HIGH}

    best_low = max(low_energies, key=low_energies.get)
    best_high = max(high_energies, key=high_energies.get)

    sorted_low = sorted(low_energies.values(), reverse=True)
    sorted_high = sorted(high_energies.values(), reverse=True)

    # Dominant peak ratio (must be clearly above runner-up to reject broadband room noise)
    if sorted_low[0] < 1.7 * sorted_low[1] or sorted_high[0] < 1.7 * sorted_high[1]:
        return None

    # Sensitive threshold for distance reception
    if sorted_low[0] < 0.0001 or sorted_high[0] < 0.0001:
        return None

    for k, (fl, fh) in DTMF_MAP.items():
        if fl == best_low and fh == best_high:
            return k

    return None
