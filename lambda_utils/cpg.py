"""Code Property Graph generation via ``lambda_graphs``."""

import os
import tempfile
from pathlib import Path

from lambda_graphs import generate


def generate_cpg_json(code: str, language: str = "cpp") -> str:
    """Generate a JSON CPG from *code* using ``lambda_graphs``.

    Writes to a temporary file and reads back the JSON string because the
    public API only exposes ``.to_json(path)``.  The temp file is cleaned up
    even if an error occurs.
    """
    result = generate(language, code=code, graphs=["cfg", "dfg"])

    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.close()
    try:
        result.to_json(tmp.name)
        return Path(tmp.name).read_text(encoding="utf-8")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
