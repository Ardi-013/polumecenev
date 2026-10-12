from pathlib import Path
from typing import Dict, Optional

from lab1.domain.models import CelestialBody

BODIES: Dict[str, CelestialBody] = {
    "sun": CelestialBody("sun", "sun.png"),
    "hourglass_twins": CelestialBody("hourglass_twins", "hourglass_twins.png"),
    "timber_hearth": CelestialBody("timber_hearth", "timber_hearth.png"),
    "attlerock": CelestialBody("attlerock", "attlerock.png"),
    "brittle_hollow": CelestialBody("brittle_hollow", "brittle_hollow.png"),
    "hollows_lantern": CelestialBody("hollows_lantern", "hollows_lantern.png"),
    "giants_deep": CelestialBody("giants_deep", "giants_deep.png"),
    "dark_bramble": CelestialBody("dark_bramble", "dark_bramble.png"),
    "interloper": CelestialBody("interloper", "interloper.png"),
    "quantum_moon": CelestialBody("quantum_moon", "quantum_moon.png"),
    "white_hole": CelestialBody("white_hole", "white_hole.png"),
    "the_stranger": CelestialBody("the_stranger", "the_stranger.png"),
}


def get_images_dir() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    images_dir = base_dir / "assets" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    return images_dir


def get_body(body_id: str) -> Optional[CelestialBody]:
    return BODIES.get(body_id)


def match_body_by_path(file_path: str) -> Optional[CelestialBody]:
    path = Path(file_path)
    stem = path.stem.lower()

    if stem in BODIES:
        return BODIES[stem]

    for body_id, item in BODIES.items():
        if body_id in stem:
            return item

    return None
