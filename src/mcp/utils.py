from pathlib import Path


def _safe_path(name: str, safe_path: Path) -> Path:
    """Resolves a note name by preventing any exit from the notes folder."""
    path = (safe_path / name).resolve()
    if not path.is_relative_to(safe_path.resolve()):
        raise ValueError(f"Path outside of notes/ : {name}")
    return path
