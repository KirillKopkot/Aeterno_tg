import asyncio
import logging
import os
import sys
import warnings

from dotenv import load_dotenv
from telegram.ext import Application, CallbackQueryHandler
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning, message=".*per_message.*")

import api_client
from handlers import back_to_menu, build_conversation_handler, copy_last, download_last

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def _post_init(application: Application) -> None:
    me = await application.bot.get_me()
    print(f"🤖 Bot started: @{me.username}")

    healthy = await api_client.health_check()
    if healthy:
        print("✅ Backend connected")
    else:
        print("⚠️  WARNING: Backend is unreachable")


def main() -> None:
    if not BOT_TOKEN:
        sys.exit(
            "❌ BOT_TOKEN is not set.\n"
            "   1. Copy .env.example to .env\n"
            "   2. Paste your token from @BotFather into BOT_TOKEN"
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    application.add_handler(build_conversation_handler())
    application.add_handler(CallbackQueryHandler(copy_last, pattern="^copy_last$"))
    application.add_handler(CallbackQueryHandler(download_last, pattern="^download_last$"))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))

    logger.info("Starting polling...")
    asyncio.set_event_loop(asyncio.new_event_loop())
    application.run_polling()


if __name__ == "__main__":
    main()
