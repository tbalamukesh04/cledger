# backend/app/utils/text_processing.py
import re
import unicodedata
import logging

logger = logging.getLogger(__name__)

def normalize_whatsapp_text(raw_text: str | None) -> str | None:
    """
    Cleans and standardizes raw WhatsApp message text for downstream parsing.
    
    Tasks performed:
    1. Unicode normalization (NFKC)
    2. UTF-8 encoding enforcement
    3. Removal of WhatsApp formatting artifacts (*, _, ~, ```)
    4. Line break normalization
    5. Excessive whitespace removal
    """
    if not raw_text:
        return None

    try:
        # 1. Convert unusual Unicode characters (NFKC standardizes width and composition)
        text = unicodedata.normalize('NFKC', raw_text)

        # 2. Ensure UTF-8 compatibility (encode to bytes, ignore invalid, decode back)
        text = text.encode('utf-8', errors='ignore').decode('utf-8')

        # 3. Remove WhatsApp formatting artifacts (*bold*, _italics_, ~strikethrough~, ```code```)
        # Replaces the formatting markers but keeps the text inside them
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        text = re.sub(r'_(.*?)_', r'\1', text)
        text = re.sub(r'~(.*?)~', r'\1', text)
        text = re.sub(r'```(.*?)```', r'\1', text, flags=re.DOTALL)

        # 4. Normalize line breaks (convert Windows CRLF to standard LF)
        text = text.replace('\r\n', '\n')
        
        # Collapse 3+ consecutive newlines into exactly 2 newlines (preserves basic paragraphs)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 5. Remove excessive horizontal whitespace (tabs, multiple spaces)
        text = re.sub(r'[ \t]+', ' ', text)

        # Strip leading/trailing whitespace
        normalized = text.strip()
        
        return normalized if normalized else None

    except Exception as e:
        logger.warning(f"Text normalization failed: {str(e)}. Returning raw text safely.")
        return raw_text