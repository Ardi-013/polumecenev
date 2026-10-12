from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CelestialBody:
    id: str
    filename: str

    @property
    def file_path(self) -> Path:
        base_dir = Path(__file__).resolve().parent.parent
        return base_dir / "assets" / "images" / self.filename
