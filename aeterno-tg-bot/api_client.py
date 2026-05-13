import asyncio
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "https://your-backend-url.railway.app")
TIMEOUT = 5


def _post(endpoint: str, payload: dict) -> dict:
    url = f"{BACKEND_URL}{endpoint}"
    response = requests.post(url, json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def _network_error(e: requests.RequestException) -> dict:
    if isinstance(e, requests.Timeout):
        msg = "Request timed out. Try again later."
    elif isinstance(e, requests.ConnectionError):
        msg = "Cannot reach the server. Try again later."
    elif isinstance(e, requests.HTTPError):
        msg = f"Server error ({e.response.status_code}). Try again later."
    else:
        msg = "Service unavailable. Try again later."
    return {"success": False, "result": "", "error": msg}


async def encrypt(plaintext: str, key: str) -> dict:
    def _call():
        return _post("/api/encrypt", {"text": plaintext, "key": key})

    try:
        data = await asyncio.to_thread(_call)
        return {
            "success": data.get("success", False),
            "result": data.get("result", ""),
            "error": None if data.get("success") else data.get("message", "Unknown error"),
        }
    except requests.RequestException as e:
        return _network_error(e)


async def decrypt(ciphertext_b64: str, key: str) -> dict:
    def _call():
        return _post("/api/decrypt", {"text": ciphertext_b64, "key": key})

    try:
        data = await asyncio.to_thread(_call)
        return {
            "success": data.get("success", False),
            "result": data.get("result", ""),
            "error": None if data.get("success") else data.get("message", "Unknown error"),
        }
    except requests.RequestException as e:
        return _network_error(e)


async def health_check() -> bool:
    def _call():
        url = f"{BACKEND_URL}/api/health"
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()

    try:
        data = await asyncio.to_thread(_call)
        return data.get("status", "").upper() == "UP"
    except requests.RequestException:
        return False
