import logging
import os
import warnings

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning, message=".*per_message.*")

import api_client
from handlers import register_handlers

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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")   # https://your-app.onrender.com
BACKEND_URL = os.getenv("BACKEND_URL")   # https://your-backend.railway.app
PORT = int(os.getenv("PORT", 8000))

app = FastAPI(title="Aeterno TG Bot", version="1.0.0")

application: Application | None = None


# ──── Startup / Shutdown ────

@app.on_event("startup")
async def startup() -> None:
    global application

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    logger.info("🚀 Starting bot in WEBHOOK mode...")

    application = Application.builder().token(BOT_TOKEN).build()
    register_handlers(application)

    await application.initialize()
    await application.start()

    # Register webhook with Telegram
    webhook_endpoint = f"{WEBHOOK_URL}/webhook"
    try:
        await application.bot.set_webhook(
            url=webhook_endpoint,
            allowed_updates=Update.ALL_TYPES,
        )
        me = await application.bot.get_me()
        logger.info("🤖 Bot: @%s", me.username)
        logger.info("✅ Webhook mode enabled")
        logger.info("Waiting for updates on /webhook")
    except Exception as e:
        logger.warning("⚠️  Webhook setup error: %s", e)

    # Validate backend connection
    healthy = await api_client.health_check()
    if healthy:
        logger.info("✅ Backend connected")
    else:
        logger.warning("⚠️  Backend is unreachable — encrypt/decrypt will fail")


@app.on_event("shutdown")
async def shutdown() -> None:
    global application

    if application:
        await application.stop()
        await application.shutdown()

    logger.info("🛑 Bot stopped")


# ──── Endpoints ────

@app.post("/webhook")
async def webhook(request: Request) -> JSONResponse:
    """Receive updates from Telegram."""
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error("Webhook error: %s", e)
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/set-webhook")
async def set_webhook(request: Request) -> JSONResponse:
    """Re-register the webhook URL with Telegram."""
    try:
        body = await request.json()
        url = body.get("url") or f"{WEBHOOK_URL}/webhook"
        await application.bot.set_webhook(
            url=url,
            allowed_updates=Update.ALL_TYPES,
        )
        logger.info("Webhook updated: %s", url)
        return JSONResponse({"status": "webhook set", "url": url})
    except Exception as e:
        logger.error("set-webhook error: %s", e)
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


@app.get("/health")
async def health() -> JSONResponse:
    """Health check — used by Render to verify the service is up."""
    return JSONResponse({"status": "ok"})


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse({
        "name": "Aeterno Telegram Bot",
        "mode": "webhook",
        "endpoints": {
            "GET  /health": "health check",
            "POST /webhook": "Telegram update receiver",
            "POST /api/set-webhook": "re-register webhook URL",
        },
    })


# ──── Main ────

if __name__ == "__main__":
    import uvicorn

    print(f"""
    ╔════════════════════════════════════╗
    ║  Aeterno Telegram Bot - Webhook    ║
    ║  Mode: FastAPI + Uvicorn           ║
    ╚════════════════════════════════════╝

    PORT:        {PORT}
    WEBHOOK_URL: {WEBHOOK_URL}
    BACKEND_URL: {BACKEND_URL}
    """)

    uvicorn.run("bot:app", host="0.0.0.0", port=PORT, reload=False)
