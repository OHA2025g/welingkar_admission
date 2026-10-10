import asyncio
import logging
import os
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)
# Local-disk fallback: used when STORAGE_MODE=local or no EMERGENT_LLM_KEY is configured.
LOCAL_DIR = (os.environ.get("LOCAL_STORAGE_DIR") or "/tmp/weschool-storage") if (
    os.environ.get("STORAGE_MODE") == "local" or not os.environ.get("EMERGENT_LLM_KEY")) else None
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "weschool"
ATTEMPTS = 5
TRANSIENT = {429, 500, 502, 503, 504}
_key = None


def _backoff(attempt: int) -> None:
    time.sleep(min(0.5 * 2 ** (attempt - 1), 4))


def init_storage(force: bool = False) -> str:
    global _key
    if _key and not force:
        return _key
    for attempt in range(1, ATTEMPTS + 1):
        try:
            resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ["EMERGENT_LLM_KEY"]}, timeout=30)
            if resp.status_code not in TRANSIENT or attempt == ATTEMPTS:
                resp.raise_for_status()
                _key = resp.json()["storage_key"]
                return _key
        except (requests.ConnectionError, requests.Timeout):
            if attempt == ATTEMPTS:
                raise
        logger.warning(f"storage init transient failure, retry {attempt}/{ATTEMPTS}")
        _backoff(attempt)


def _call(method: str, path: str, data: bytes = None, content_type: str = None, timeout: int = 120) -> requests.Response:
    force = False
    for attempt in range(1, ATTEMPTS + 1):
        headers = {"X-Storage-Key": init_storage(force=force)}
        if content_type:
            headers["Content-Type"] = content_type
        try:
            resp = requests.request(method, f"{STORAGE_URL}/objects/{path}", data=data, headers=headers, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt == ATTEMPTS:
                raise
            logger.warning(f"storage {method} network error ({e.__class__.__name__}), retry {attempt}/{ATTEMPTS}")
        else:
            if not force and (resp.status_code in (401, 403) or (method == "PUT" and resp.status_code == 404)):
                force = True
                continue
            if resp.status_code not in TRANSIENT or attempt == ATTEMPTS:
                resp.raise_for_status()
                return resp
            logger.warning(f"storage {method} returned {resp.status_code}, retry {attempt}/{ATTEMPTS}")
        _backoff(attempt)


def _put(path: str, data: bytes, content_type: str) -> dict:
    return _call("PUT", path, data=data, content_type=content_type).json()


def _get(path: str) -> tuple[bytes, str]:
    resp = _call("GET", path, timeout=60)
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


async def put_object(path: str, data: bytes, content_type: str) -> dict:
    if LOCAL_DIR:
        return await asyncio.to_thread(_local_put, path, data, content_type)
    return await asyncio.to_thread(_put, path, data, content_type)


async def get_object(path: str) -> tuple[bytes, str]:
    if LOCAL_DIR:
        return await asyncio.to_thread(_local_get, path)
    return await asyncio.to_thread(_get, path)


def _local_file(path: str) -> Path:
    p = (Path(LOCAL_DIR) / path).resolve()
    if Path(LOCAL_DIR).resolve() not in p.parents:
        raise ValueError("invalid storage path")
    return p


def _local_put(path: str, data: bytes, content_type: str) -> dict:
    p = _local_file(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    p.with_name(p.name + ".type").write_text(content_type)
    return {"path": path, "size": len(data)}


def _local_get(path: str) -> tuple[bytes, str]:
    p = _local_file(path)
    if not p.exists():
        raise FileNotFoundError(path)
    t = p.with_name(p.name + ".type")
    return p.read_bytes(), t.read_text() if t.exists() else "application/octet-stream"
