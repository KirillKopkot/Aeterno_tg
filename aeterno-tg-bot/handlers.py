import logging
import os
import tempfile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import api_client
from states import State

logger = logging.getLogger(__name__)

_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB

_MAIN_MENU = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🔒 Encrypt", callback_data="encrypt"),
        InlineKeyboardButton("🔓 Decrypt", callback_data="decrypt"),
    ]
])

_RESULT_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📋 Copy", callback_data="copy_last"),
        InlineKeyboardButton("⬇️ Download TXT", callback_data="download_last"),
    ],
    [
        InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu"),
    ],
])


def _uid(update: Update) -> int:
    return update.effective_user.id


async def _show_menu(update: Update, text: str = "Choose an operation:") -> None:
    await update.effective_message.reply_text(text, reply_markup=_MAIN_MENU)


async def _read_document(update: Update, state_on_error: State) -> tuple[str | None, State]:
    """Download and decode a .txt document. Returns (content, next_state) or (None, error_state)."""
    doc = update.message.document

    if not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text(
            "❌ Only .txt files are supported.\n"
            "Upload a .txt file or paste the text directly."
        )
        return None, state_on_error

    if doc.file_size > _MAX_FILE_BYTES:
        size_mb = doc.file_size / 1024 / 1024
        await update.message.reply_text(
            f"❌ File too large ({size_mb:.1f} MB). Maximum allowed size is 20 MB."
        )
        return None, state_on_error

    try:
        file = await doc.get_file()
        data = await file.download_as_bytearray()
        content = data.decode("utf-8").strip()
        if not content:
            await update.message.reply_text("❌ The file is empty. Try again.")
            return None, state_on_error
        return content, state_on_error
    except UnicodeDecodeError:
        await update.message.reply_text(
            "❌ Could not read the file (not valid UTF-8 text). Try again."
        )
        return None, state_on_error
    except Exception as e:
        logger.error("[%s] File download failed: %s", _uid(update), e)
        await update.message.reply_text("❌ Failed to read the file. Try again or paste the text directly.")
        return None, state_on_error


async def _send_as_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    content: str,
    filename: str,
) -> None:
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        with open(path, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=filename,
            )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ── /start ──

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    logger.info("[%s] /start → menu", _uid(update))
    await _show_menu(update, "👋 Welcome! Choose an operation:")
    return ConversationHandler.END


# ── /cancel ──

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    logger.info("[%s] /cancel → END", _uid(update))
    await update.message.reply_text("❌ Operation cancelled.")
    await _show_menu(update)
    return ConversationHandler.END


# ── Timeout ──

async def timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[%s] conversation timed out", _uid(update))
    context.user_data.clear()
    if update.effective_message:
        await update.effective_message.reply_text(
            "⏱ Session expired due to inactivity. Use /start to begin again."
        )
    return ConversationHandler.END


# ── Encrypt flow ──

async def encrypt_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    logger.info("[%s] encrypt button → ENCRYPT_TEXT", _uid(update))
    await query.message.reply_text(
        "📝 Send the text to encrypt (max 60 chars)\n"
        "💡 You can also upload a .txt file instead of typing"
    )
    return State.ENCRYPT_TEXT


async def encrypt_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    if len(text) > 60:
        logger.info("[%s] ENCRYPT_TEXT: text too long (%d chars)", _uid(update), len(text))
        await update.message.reply_text(
            f"❌ Text is too long ({len(text)}/60 chars). Please send a shorter text:"
        )
        return State.ENCRYPT_TEXT
    context.user_data["encrypt_text"] = text
    logger.info("[%s] ENCRYPT_TEXT → ENCRYPT_KEY", _uid(update))
    await update.message.reply_text("🔑 Send the secret key")
    return State.ENCRYPT_KEY


async def encrypt_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[%s] ENCRYPT_TEXT: file uploaded", _uid(update))
    content, _ = await _read_document(update, State.ENCRYPT_TEXT)
    if content is None:
        return State.ENCRYPT_TEXT
    context.user_data["encrypt_text"] = content
    logger.info("[%s] file read (%d chars) → ENCRYPT_KEY", _uid(update), len(content))
    await update.message.reply_text(
        f"✅ File read ({len(content)} chars).\n🔑 Send the secret key"
    )
    return State.ENCRYPT_KEY


async def encrypt_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    key = update.message.text
    plaintext = context.user_data.pop("encrypt_text", "")
    logger.info("[%s] ENCRYPT_KEY: calling api", _uid(update))

    result = await api_client.encrypt(plaintext, key)

    if result["success"]:
        b64 = result["result"]
        context.user_data["last_result"] = b64
        context.user_data["last_result_filename"] = "encrypted.txt"
        logger.info("[%s] encrypt success → END", _uid(update))
        await update.message.reply_text(f"✅ Result:\n\n{b64}", reply_markup=_RESULT_KB)
    else:
        error = result["error"] or "Service unavailable. Try again later."
        logger.warning("[%s] encrypt failed: %s", _uid(update), error)
        await update.message.reply_text(f"❌ Encryption failed: {error}")

    return ConversationHandler.END


# ── Decrypt flow ──

async def decrypt_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    logger.info("[%s] decrypt button → DECRYPT_TEXT", _uid(update))
    await query.message.reply_text(
        "📋 Send the Base64 ciphertext\n"
        "💡 You can also upload a .txt file instead of typing"
    )
    return State.DECRYPT_TEXT


async def decrypt_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["decrypt_ciphertext"] = update.message.text
    logger.info("[%s] DECRYPT_TEXT → DECRYPT_KEY", _uid(update))
    await update.message.reply_text("🔑 Send the secret key")
    return State.DECRYPT_KEY


async def decrypt_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[%s] DECRYPT_TEXT: file uploaded", _uid(update))
    content, _ = await _read_document(update, State.DECRYPT_TEXT)
    if content is None:
        return State.DECRYPT_TEXT
    context.user_data["decrypt_ciphertext"] = content
    logger.info("[%s] file read (%d chars) → DECRYPT_KEY", _uid(update), len(content))
    await update.message.reply_text(
        f"✅ File read ({len(content)} chars).\n🔑 Send the secret key"
    )
    return State.DECRYPT_KEY


async def decrypt_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    key = update.message.text
    ciphertext = context.user_data.pop("decrypt_ciphertext", "")
    logger.info("[%s] DECRYPT_KEY: calling api", _uid(update))

    result = await api_client.decrypt(ciphertext, key)

    if result["success"]:
        plaintext = result["result"]
        context.user_data["last_result"] = plaintext
        context.user_data["last_result_filename"] = "decrypted.txt"
        logger.info("[%s] decrypt success → END", _uid(update))
        await update.message.reply_text(f"✅ Result:\n\n{plaintext}", reply_markup=_RESULT_KB)
    else:
        error = result["error"] or "Service unavailable. Try again later."
        logger.warning("[%s] decrypt failed: %s", _uid(update), error)
        await update.message.reply_text(
            f"❌ Decryption failed: {error}\n\n(Wrong key or invalid ciphertext?)"
        )

    return ConversationHandler.END


# ── Copy button ──

async def copy_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    text = context.user_data.get("last_result", "")
    if text:
        logger.info("[%s] copy_last", _uid(update))
        await query.answer()
        await query.message.reply_text(text)
    else:
        await query.answer("Nothing to copy.", show_alert=True)


# ── Download button ──

async def download_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    text = context.user_data.get("last_result", "")
    filename = context.user_data.get("last_result_filename", "result.txt")
    if not text:
        await query.answer("Nothing to download.", show_alert=True)
        return
    await query.answer()
    logger.info("[%s] download_last: sending %s", _uid(update), filename)
    await _send_as_file(update, context, text, filename)


# ── Back to Menu button ──

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    logger.info("[%s] back_to_menu", _uid(update))
    await _show_menu(update)


# ── Builder ──

def build_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(encrypt_start, pattern="^encrypt$"),
            CallbackQueryHandler(decrypt_start, pattern="^decrypt$"),
        ],
        states={
            State.ENCRYPT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, encrypt_text),
                MessageHandler(filters.Document.ALL, encrypt_file),
            ],
            State.ENCRYPT_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, encrypt_key),
            ],
            State.DECRYPT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, decrypt_text),
                MessageHandler(filters.Document.ALL, decrypt_file),
            ],
            State.DECRYPT_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, decrypt_key),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout),
                CallbackQueryHandler(timeout),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(encrypt_start, pattern="^encrypt$"),
            CallbackQueryHandler(decrypt_start, pattern="^decrypt$"),
        ],
        conversation_timeout=600,
    )


def register_handlers(app: Application) -> None:
    app.add_handler(build_conversation_handler())
    app.add_handler(CallbackQueryHandler(copy_last, pattern="^copy_last$"))
    app.add_handler(CallbackQueryHandler(download_last, pattern="^download_last$"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
