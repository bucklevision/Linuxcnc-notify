from pathlib import Path


def get_version():
    candidates = (
        Path(__file__).with_name("VERSION"),
        Path(__file__).resolve().parents[2] / "VERSION",
    )
    for path in candidates:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    return "unknown"
