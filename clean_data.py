"""Safely clear generated application data from this project."""
from __future__ import annotations

import shutil
from pathlib import Path


ALL_TARGETS = ("audio", "normalized", "quality", "transcripts", "classifications", "reports", "queue.json")
OPTIONS = {
    "1": ("all generated data", ALL_TARGETS),
    "2": ("audio only", ("audio",)),
    "3": ("normalized audio only", ("normalized",)),
    "4": ("quality data only", ("quality",)),
    "5": ("transcripts, classifications, and reports", ("transcripts", "classifications", "reports", "queue.json")),
}


def _remove_entry(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def clear_data(data_dir: Path, target_names: tuple[str, ...]) -> None:
    """Clear selected data targets while preserving the data directory layout."""
    if data_dir.exists() and data_dir.is_symlink():
        raise ValueError("data directory must not be a symlink")

    data_root = data_dir.resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    for target_name in target_names:
        target = data_root / target_name
        resolved_target = target.resolve()
        if resolved_target == data_root or resolved_target.parent != data_root:
            raise ValueError("target must stay inside the data directory")
        if target.is_symlink():
            raise ValueError(f"refusing to clean symlink: {target_name}")
        if target.is_dir():
            for child in target.iterdir():
                _remove_entry(child)
        elif target.exists():
            target.unlink()

        if not target_name.endswith(".json"):
            target.mkdir(parents=True, exist_ok=True)


def main() -> int:
    data_dir = Path(__file__).resolve().parent / "data"
    print(f"Data directory: {data_dir}")
    print("Choose what to clean:")
    for key, (label, _) in OPTIONS.items():
        print(f"  {key}. {label}")
    print("  6. Cancel")

    choice = input("Choice: ").strip()
    if choice == "6":
        print("Cancelled.")
        return 0
    if choice not in OPTIONS:
        print("Invalid choice.")
        return 2

    label, target_names = OPTIONS[choice]
    print(f"Selected: {label}")
    print("This will permanently remove generated files from:")
    for target_name in target_names:
        print(f"  - data/{target_name}")
    confirmation = input("Type CLEAN to continue: ").strip()
    if confirmation != "CLEAN":
        print("Cancelled.")
        return 0

    try:
        clear_data(data_dir, target_names)
    except (OSError, ValueError) as error:
        print(f"Cleanup failed: {error}")
        return 1
    print("Cleanup complete. The data directory structure was preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
