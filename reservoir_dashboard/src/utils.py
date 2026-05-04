import re
import unicodedata
from pathlib import Path


def normalize_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def normalize_key(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_text(value).lower())


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def as_csv_bytes(df) -> bytes:
    return df.to_csv(index=False).encode("utf-8")
