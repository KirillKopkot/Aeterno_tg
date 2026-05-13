import asyncio
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

_AUTO_CLEANUP_DELAY = 300  # 5 minutes


async def read_txt_file(file_path: str) -> str:
    """Read a UTF-8 text file and return its content."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError as e:
        raise ValueError("File is not valid UTF-8 text.") from e
    except OSError as e:
        raise OSError(f"Cannot read file: {e}") from e


async def save_encrypted_to_file(content_b64: str, filename: str = "encrypted.txt") -> str:
    """Write Base64 ciphertext to a temp .txt file and return the path."""
    return await _write_temp(content_b64, filename)


async def save_decrypted_to_file(content: str, filename: str = "decrypted.txt") -> str:
    """Write plaintext to a temp .txt file and return the path."""
    return await _write_temp(content, filename)


def cleanup_temp_file(file_path: str) -> None:
    """Delete a temporary file, silently ignoring errors."""
    try:
        os.unlink(file_path)
        logger.debug("Deleted temp file: %s", file_path)
    except OSError:
        pass


# ── Internals ──

async def _write_temp(content: str, filename: str) -> str:
    base = os.path.splitext(filename)[0]
    fd, path = tempfile.mkstemp(suffix=".txt", prefix=f"{base}_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    asyncio.create_task(_delayed_cleanup(path))
    return path


async def _delayed_cleanup(file_path: str) -> None:
    await asyncio.sleep(_AUTO_CLEANUP_DELAY)
    cleanup_temp_file(file_path)
