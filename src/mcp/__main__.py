from pathlib import Path
from fastmcp import FastMCP
from typing import Any
from utils import _safe_path

NOTES_DIR = Path(__file__).parent / "notes"
mcp = FastMCP("blog-helper")


@mcp.tool()
def list_notes() -> list[str]:
    """Liste les notes Markdown disponibles."""
    return sorted(p.name for p in NOTES_DIR.glob("*.md"))


@mcp.tool()
def read_note(name: str) -> Any:
    """Lit le contenu d'une note Markdown par son nom de fichier."""
    path = _safe_path(name)
    if not path.is_file():
        raise FileNotFoundError(f"Note introuvable : {name}")
    return path.read_text(encoding="utf-8")


@mcp.tool()
def search_notes(query: str) -> list[str]:
    """Renvoie les notes dont le contenu contient le terme recherché."""
    return sorted(
        p.name for p in NOTES_DIR.glob("*.md")
        if query.lower() in p.read_text(encoding="utf-8").lower()
    )


@mcp.resource("note://{name}")
def note_resource(name: str) -> Any:
    """Expose une note comme resource lisible par l'hôte."""
    return read_note(name)


if __name__ == "__main__":
    mcp.run()
