import re


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def split_into_chunks(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[str]:

    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("Overlap must be smaller than chunk size")

    text = clean_text(text)

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Prefer splitting at a paragraph or sentence boundary.
        if end < len(text):
            boundary = max(
                text.rfind("\n", start, end),
                text.rfind(". ", start, end),
            )

            if boundary > start + int(chunk_size * 0.5):
                end = boundary + 1

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        next_start = end - overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start

    return chunks


def create_document_chunks(
    extracted_pages: list[dict],
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[dict]:

    results = []

    for page in extracted_pages:
        text = page["text"]
        page_number = page.get("page_number")

        chunks = split_into_chunks(text, chunk_size=chunk_size, overlap=overlap)

        for chunk in chunks:
            results.append({
                "content": chunk,
                "page_number": page_number,
                "token_count": estimate_tokens(chunk),
            })

    return results