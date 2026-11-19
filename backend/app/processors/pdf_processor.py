import pymupdf
from pathlib import Path


def extract_pdf(file_path: str) -> list[dict]:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError("PDF file not found")

    extracted_pages = []

    try:
        with pymupdf.open(path) as pdf:
            if pdf.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported")

            for page_index, page in enumerate(pdf):
                text = page.get_text("text")

                if text and text.strip():
                    extracted_pages.append({
                        "page_number": page_index + 1,
                        "text": text,
                    })

    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Invalid or corrupted PDF file") from exc

    if not extracted_pages:
        raise ValueError(
            "No readable text found in PDF. It may be a scanned document."
        )

    return extracted_pages