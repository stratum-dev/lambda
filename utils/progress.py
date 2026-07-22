"""File-based progress tracking for resumable batch processing."""

import json
from pathlib import Path


class ProgressTracker:
    """Tracks which row indices have been processed, persisted as a JSON file.

    Usage::

        progress = ProgressTracker(Path("./build_kb_progress.json"))
        processed = progress.load()       # set[int]
        processed.add(42)
        progress.save(processed)
    """

    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath

    def load(self) -> set[int]:
        """Return the set of already-processed row indices."""
        if not self.filepath.exists():
            return set()
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
            return set(data.get("processed_indices", []))
        except (json.JSONDecodeError, KeyError):
            return set()

    def save(self, processed: set[int]) -> None:
        """Persist the set of processed indices (sorted) to disk."""
        self.filepath.write_text(
            json.dumps(
                {"processed_indices": sorted(processed)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
