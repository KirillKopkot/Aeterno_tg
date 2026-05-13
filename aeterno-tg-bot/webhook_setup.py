import logging

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org"
_TIMEOUT = 10
_ALLOWED_UPDATES = ["message", "callback_query"]


def _url(token: str, method: str) -> str:
    return f"{_API_BASE}/bot{token}/{method}"


async def setup_webhook(bot_token: str, webhook_url: str) -> dict:
    """Register webhook_url with Telegram. Call once on deploy."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                _url(bot_token, "setWebhook"),
                json={"url": webhook_url, "allowed_updates": _ALLOWED_UPDATES},
            )
            data = response.json()
            if data.get("ok"):
                logger.info("Webhook set: %s", webhook_url)
            else:
                logger.warning("setWebhook failed: %s", data.get("description"))
            return data
    except httpx.RequestError as e:
        logger.error("setup_webhook network error: %s", e)
        return {"ok": False, "description": str(e)}


async def get_webhook_info(bot_token: str) -> dict:
    """Return current webhook info from Telegram (useful for debugging)."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(_url(bot_token, "getWebhookInfo"))
            return response.json()
    except httpx.RequestError as e:
        logger.error("get_webhook_info network error: %s", e)
        return {"ok": False, "description": str(e)}


async def delete_webhook(bot_token: str) -> dict:
    """Remove webhook — use when switching back to polling."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(_url(bot_token, "deleteWebhook"))
            data = response.json()
            if data.get("ok"):
                logger.info("Webhook deleted")
            else:
                logger.warning("deleteWebhook failed: %s", data.get("description"))
            return data
    except httpx.RequestError as e:
        logger.error("delete_webhook network error: %s", e)
        return {"ok": False, "description": str(e)}
