import re
import unicodedata

from bs4 import BeautifulSoup


def clean_text(text: str | None) -> str | None:
    if not text:
        return None

    # Strip HTML tags/entities
    soup = BeautifulSoup(text, "html.parser")
    stripped_text = soup.get_text(separator=" ")

    # Normalize unicode (NFKC)
    normalized_text = unicodedata.normalize('NFKC', stripped_text)

    # Collapse multiple spaces and newlines
    # First, collapse multiple newlines and spaces around them into a single newline
    cleaned = re.sub(r'\s*\n\s*', '\n', normalized_text)
    # Then collapse multiple spaces into a single space
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    
    return cleaned.strip()
