from pathlib import Path


def extract_txt(file_path: str) -> list[dict]:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError("TXT file not found")

    try:
        text = path.read_text(encoding="utf-8-sig")

        if not text.strip():
            raise ValueError("TXT file is empty")

        return [{
            "page_number": None,
            "text": text,
        }]

    except UnicodeDecodeError as exc:
        raise ValueError(
            "TXT file must use UTF-8 encoding"
        ) from exc