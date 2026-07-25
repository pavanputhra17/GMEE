import logging

import py3langid

logger = logging.getLogger(__name__)

# Very short texts are unreliable for language detection
MIN_LENGTH_FOR_DETECTION = 20

def detect_language(text: str | None) -> str | None:
    if not text:
        return None
        
    if len(text.strip()) < MIN_LENGTH_FOR_DETECTION:
        logger.debug(f"Text too short for language detection ({len(text)} chars)")
        return None
        
    try:
        lang, _ = py3langid.classify(text)
        if isinstance(lang, str):
            return lang
        return str(lang) if lang else None
    except Exception as e:
        logger.warning(f"Language detection failed: {e}")
        return None
