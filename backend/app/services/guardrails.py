"""Guardrails for request ingestion, model use, and AI output validation."""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("nexus.guardrails")

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
CODE_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
GENERIC_SECRET_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|authorization)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-./+=]{8,}[\"']?"
)
BEARER_TOKEN_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+=/]{12,}\b")
PROMPT_LEAK_RE = re.compile(
    r"(system prompt|developer message|hidden instructions|ignore previous instructions|reveal prompt|jailbreak)",
    re.IGNORECASE,
)

JAILBREAK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bignore (all )?(previous|prior) instructions\b",
        r"\boverride (the )?(system|developer) prompt\b",
        r"\breveal (the )?(system|developer|hidden) prompt\b",
        r"\bdo anything now\b",
        r"\bdeveloper mode\b",
        r"\bjailbreak\b",
        r"\bbypass (safety|guardrails|filters)\b",
        r"\bact as .* without restrictions\b",
        r"\bpretend (you are|to be) unrestricted\b",
    )
]

EXFILTRATION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bshow .*\.env\b",
        r"\bdump (all )?(secrets|tokens|passwords|credentials)\b",
        r"\bexport (the )?(database|db)\b",
        r"\breveal (all )?(keys|credentials|tokens)\b",
        r"\bcat\s+~?/?\.ssh\b",
        r"\bprintenv\b",
        r"\benv\b",
        r"\bcopy .*secret",
    )
]

TOOL_MISUSE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\brm\s+-rf\b",
        r"\bdel\s+/f\b",
        r"\bshutdown\b",
        r"\bformat\s+[a-z]:\b",
        r"\binvoke-webrequest\b",
        r"\bcurl\s+https?://",
        r"\bwget\s+https?://",
        r"\bos\.system\(",
        r"\bsubprocess\.(run|Popen)\(",
        r"\beval\(",
    )
]

MODEL_MISUSE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bphishing\b",
        r"\bcredential stuffing\b",
        r"\bransomware\b",
        r"\bkeylogger\b",
        r"\bexploit code\b",
        r"\bmalware\b",
        r"\bbypass authentication\b",
        r"\bsteal\b.*\bpassword",
        r"\bsocial engineering\b",
    )
]

CONTENT_FILTER_PATTERNS = {
    "hate": [
        re.compile(r"\bkill (all )?(them|those people)\b", re.IGNORECASE),
        re.compile(r"\bslur\b", re.IGNORECASE),
    ],
    "sexual": [
        re.compile(r"\bexplicit sexual\b", re.IGNORECASE),
        re.compile(r"\bsexual content involving minors\b", re.IGNORECASE),
    ],
    "violence": [
        re.compile(r"\bhow to make a bomb\b", re.IGNORECASE),
        re.compile(r"\bmass shooting\b", re.IGNORECASE),
    ],
    "self_harm": [
        re.compile(r"\bhow to kill myself\b", re.IGNORECASE),
        re.compile(r"\bself[- ]harm instructions\b", re.IGNORECASE),
    ],
}


class InputGuardResult(BaseModel):
    cleaned_text: str
    redacted_text: str
    detected_pii: list[str] = Field(default_factory=list)
    jailbreak_detected: bool = False
    exfiltration_detected: bool = False
    tool_misuse_detected: bool = False
    model_misuse_detected: bool = False
    content_filtered: bool = False
    filtered_categories: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    risk_labels: list[str] = Field(default_factory=list)
    should_use_llm: bool = True


class NotesOutput(BaseModel):
    ai_summary: str = Field(min_length=1, max_length=300)
    ai_details: str = Field(min_length=1, max_length=2500)
    ai_next_action: str = Field(min_length=1, max_length=1000)


class AnalysisOutput(BaseModel):
    sentiment: str = "Neutral"
    ai_tags: list[str] = Field(default_factory=list)
    complexity: str = "Medium"
    confidence_score: float = 0.75
    intent_category: str = "IT Support"
    urgency_level: str = "NORMAL"


class QualityOutput(BaseModel):
    quality_score: float = 0.0
    approved: bool = False
    improvement_suggestions: list[str] = Field(default_factory=list)


class CodeQualityLLMOutput(BaseModel):
    recommendation: str = Field(min_length=1, max_length=120)
    autogen_summary: str = Field(min_length=1, max_length=1200)


def sanitize_user_text(text: str, *, max_length: int = 10_000) -> str:
    normalized = CONTROL_CHARS_RE.sub(" ", text or "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()[:max_length]


def sanitize_code_text(text: str, *, max_length: int = 20_000) -> str:
    normalized = CODE_CONTROL_CHARS_RE.sub("", text or "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized[:max_length].strip()


def redact_pii(text: str) -> tuple[str, list[str]]:
    redacted = text
    detected: list[str] = []

    replacements = [
        (EMAIL_RE, "[REDACTED_EMAIL]", "email"),
        (PHONE_RE, "[REDACTED_PHONE]", "phone"),
        (SSN_RE, "[REDACTED_SSN]", "ssn"),
        (CARD_RE, "[REDACTED_CARD]", "payment_card"),
        (AWS_KEY_RE, "[REDACTED_AWS_KEY]", "aws_key"),
        (GENERIC_SECRET_RE, "[REDACTED_SECRET]", "secret"),
        (BEARER_TOKEN_RE, "[REDACTED_BEARER_TOKEN]", "bearer_token"),
    ]
    for pattern, token, label in replacements:
        if pattern.search(redacted):
            detected.append(label)
            redacted = pattern.sub(token, redacted)

    return redacted, detected


def detect_jailbreak(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in JAILBREAK_PATTERNS)


def detect_data_exfiltration(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in EXFILTRATION_PATTERNS)


def detect_tool_misuse(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in TOOL_MISUSE_PATTERNS)


def detect_model_misuse(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in MODEL_MISUSE_PATTERNS)


def detect_filtered_content(text: str) -> list[str]:
    categories: list[str] = []
    for category, patterns in CONTENT_FILTER_PATTERNS.items():
        if any(pattern.search(text or "") for pattern in patterns):
            categories.append(category)
    return categories


def _guard_text(
    text: str,
    *,
    sanitizer,
    min_length: int,
    max_length: int,
    readable_required: bool,
    block_on_risks: bool,
) -> InputGuardResult:
    cleaned = sanitizer(text, max_length=max_length)
    validation_errors: list[str] = []

    if len(cleaned) < min_length:
        validation_errors.append(f"Input must be at least {min_length} characters after normalization.")
    if readable_required and not re.search(r"[A-Za-z]", cleaned):
        validation_errors.append("Input must contain readable alphabetic content.")

    redacted, detected_pii = redact_pii(cleaned)
    jailbreak_detected = detect_jailbreak(cleaned)
    exfiltration_detected = detect_data_exfiltration(cleaned)
    tool_misuse_detected = detect_tool_misuse(cleaned)
    model_misuse_detected = detect_model_misuse(cleaned)
    filtered_categories = detect_filtered_content(cleaned)
    content_filtered = bool(filtered_categories)

    risk_labels: list[str] = []
    if detected_pii:
        risk_labels.append("pii_detected")
    if jailbreak_detected:
        risk_labels.append("prompt_injection")
    if exfiltration_detected:
        risk_labels.append("data_exfiltration")
    if tool_misuse_detected:
        risk_labels.append("tool_misuse")
    if model_misuse_detected:
        risk_labels.append("model_misuse")
    if content_filtered:
        risk_labels.extend(f"content_filter:{category}" for category in filtered_categories)
    if validation_errors:
        risk_labels.append("input_validation")

    should_use_llm = True
    if block_on_risks:
        should_use_llm = not any(
            [
                validation_errors,
                jailbreak_detected,
                exfiltration_detected,
                tool_misuse_detected,
                model_misuse_detected,
                content_filtered,
                detected_pii,
            ]
        )

    if risk_labels:
        logger.info("Guardrails triggered risk_labels=%s validation_errors=%s", risk_labels, validation_errors)

    return InputGuardResult(
        cleaned_text=cleaned,
        redacted_text=redacted,
        detected_pii=detected_pii,
        jailbreak_detected=jailbreak_detected,
        exfiltration_detected=exfiltration_detected,
        tool_misuse_detected=tool_misuse_detected,
        model_misuse_detected=model_misuse_detected,
        content_filtered=content_filtered,
        filtered_categories=filtered_categories,
        validation_errors=validation_errors,
        risk_labels=risk_labels,
        should_use_llm=should_use_llm,
    )


def guard_request_text(text: str) -> InputGuardResult:
    return _guard_text(
        text,
        sanitizer=sanitize_user_text,
        min_length=10,
        max_length=10_000,
        readable_required=True,
        block_on_risks=True,
    )


def guard_code_quality_input(text: str) -> InputGuardResult:
    return _guard_text(
        text,
        sanitizer=sanitize_code_text,
        min_length=3,
        max_length=20_000,
        readable_required=False,
        block_on_risks=True,
    )


def sanitize_free_text_output(text: str, *, max_length: int) -> str:
    cleaned = sanitize_user_text(text, max_length=max_length)
    cleaned, _ = redact_pii(cleaned)
    cleaned = PROMPT_LEAK_RE.sub("[FILTERED_PROMPT_LEAK]", cleaned)
    for category, patterns in CONTENT_FILTER_PATTERNS.items():
        for pattern in patterns:
            cleaned = pattern.sub(f"[FILTERED_{category.upper()}]", cleaned)
    return cleaned


def validate_notes_output(data: dict[str, Any]) -> dict[str, str]:
    payload = {
        "ai_summary": sanitize_free_text_output(str(data.get("ai_summary", "")), max_length=300),
        "ai_details": sanitize_free_text_output(str(data.get("ai_details", "")), max_length=2500),
        "ai_next_action": sanitize_free_text_output(str(data.get("ai_next_action", "")), max_length=1000),
    }
    try:
        return NotesOutput(**payload).model_dump()
    except ValidationError as exc:
        raise ValueError(f"Invalid AI notes output: {exc}") from exc


def validate_analysis_output(data: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "sentiment": sanitize_free_text_output(str(data.get("sentiment", "Neutral")), max_length=32) or "Neutral",
        "ai_tags": [sanitize_free_text_output(str(tag), max_length=50) for tag in (data.get("ai_tags") or [])][:10],
        "complexity": sanitize_free_text_output(str(data.get("complexity", "Medium")), max_length=16) or "Medium",
        "confidence_score": max(0.0, min(1.0, float(data.get("confidence_score", 0.75)))),
        "intent_category": sanitize_free_text_output(str(data.get("intent_category", "IT Support")), max_length=80)
        or "IT Support",
        "urgency_level": sanitize_free_text_output(str(data.get("urgency_level", "NORMAL")), max_length=16) or "NORMAL",
    }
    return AnalysisOutput(**payload).model_dump()


def validate_quality_output(data: dict[str, Any]) -> dict[str, Any]:
    suggestions = [sanitize_free_text_output(str(item), max_length=200) for item in (data.get("improvement_suggestions") or [])]
    payload = {
        "quality_score": max(0.0, min(100.0, float(data.get("quality_score", 0.0)))),
        "approved": bool(data.get("approved", False)),
        "improvement_suggestions": [item for item in suggestions if item][:5],
    }
    return QualityOutput(**payload).model_dump()


def validate_code_quality_llm_output(data: dict[str, Any]) -> dict[str, str]:
    payload = {
        "recommendation": sanitize_free_text_output(str(data.get("recommendation", "")), max_length=120),
        "autogen_summary": sanitize_free_text_output(str(data.get("autogen_summary", "")), max_length=1200),
    }
    try:
        return CodeQualityLLMOutput(**payload).model_dump()
    except ValidationError as exc:
        raise ValueError(f"Invalid code quality LLM output: {exc}") from exc
