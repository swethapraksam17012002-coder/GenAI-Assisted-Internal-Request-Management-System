"""Runtime detection helpers for optional AI framework integrations."""

from __future__ import annotations

import importlib
import logging

from app.core.config import settings

logger = logging.getLogger("nexus.ai_frameworks")

def _module_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        logger.debug("Optional module unavailable: %s", module_name)
        return False


def crewai_available() -> bool:
    return _module_available("crewai")


def litellm_available() -> bool:
    return _module_available("litellm")


def autogen_available() -> bool:
    return _module_available("autogen")


def ollama_available() -> bool:
    return bool(settings.OLLAMA_BASE_URL and settings.OLLAMA_MODEL)


def crewai_ready() -> bool:
    return crewai_available() and litellm_available() and ollama_available()


def autogen_ready() -> bool:
    return autogen_available() and ollama_available()
