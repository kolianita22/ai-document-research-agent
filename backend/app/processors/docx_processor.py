from pathlib import Path
from docx import Document as DocxDocument


def extract_docx(file_path: str) -> list[dict]:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError("DOCX file not found")

    try:
        document = DocxDocument(path)

        paragraphs = []

        for paragraph in document.paragraphs:
            text = paragraph.text.strip()

            if text:
                paragraphs.append(text)

        extracted_text = "\n\n".join(paragraphs)

        if not extracted_text.strip():
            raise ValueError("No readable text found in DOCX")

        return [{
            "page_number": None,
            "text": extracted_text,
        }]

    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Unable to read DOCX file") from exc