"""
NEXUS SDLC - AI Pipeline Service
LangGraph-style stateful pipeline orchestrating request analysis and note generation.
Implements graceful degradation when CrewAI or the model runtime is unavailable.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.services.ai_frameworks import crewai_ready, ollama_available
from app.services.guardrails import (
    guard_request_text,
    sanitize_free_text_output,
    validate_analysis_output,
    validate_notes_output,
    validate_quality_output,
)

logger = logging.getLogger("nexus.pipeline")


class GraphState(dict):
    """Carries all data between pipeline nodes."""


DEFAULT_AI_SUMMARY = "AI analysis in progress."
DEFAULT_AI_DETAILS = "AI analysis is queued or running for this request."
DEFAULT_AI_NEXT_ACTION = "Await AI analysis completion and review the generated notes."


def _langsmith_enabled() -> bool:
    return bool(settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY and settings.LANGSMITH_ENDPOINT)


def _start_langsmith_trace(request_id: str, payload: dict):
    if not _langsmith_enabled():
        return None
    try:
        from langsmith.run_trees import RunTree

        trace = RunTree(
            name="nexus_request_pipeline",
            run_type="chain",
            project_name=settings.LANGSMITH_PROJECT,
            inputs={
                "request_id": request_id,
                "request_type": payload.get("request_type", "Other"),
                "priority": payload.get("priority", "Medium"),
                "source_channel": payload.get("source_channel", "Portal"),
                "requestor_email": payload.get("requestor_email", ""),
                "raw_description": payload.get("raw_description", ""),
            },
            extra={
                "metadata": {
                    "request_id": request_id,
                    "component": "ai_pipeline",
                }
            },
        )
        trace.post()
        return trace
    except Exception as exc:
        logger.warning("LangSmith trace start failed for %s: %s", request_id, exc)
        return None


def _finish_langsmith_trace(trace, outputs: dict | None = None, error: str | None = None) -> str | None:
    if not trace:
        return None
    try:
        if error:
            trace.end(error=error)
        else:
            trace.end(outputs=outputs or {})
        trace.patch()
        trace_id = getattr(trace, "trace_id", None) or getattr(trace, "id", None)
        return str(trace_id) if trace_id else None
    except Exception as exc:
        logger.warning("LangSmith trace finish failed: %s", exc)
        trace_id = getattr(trace, "trace_id", None) or getattr(trace, "id", None)
        return str(trace_id) if trace_id else None


async def _node_ingest(state: GraphState, queue: Optional[asyncio.Queue]) -> GraphState:
    await _emit(queue, "agent_started", {"agent": "Ingest", "node": "ingest"})
    raw = state.get("raw_description", "")
    if settings.AI_GUARDRAILS_ENABLED:
        guardrail_result = guard_request_text(raw[: settings.AI_INPUT_MAX_CHARS])
    else:
        guardrail_result = guard_request_text(raw[: settings.AI_INPUT_MAX_CHARS])
        guardrail_result.jailbreak_detected = False
        guardrail_result.validation_errors = []
        guardrail_result.should_use_llm = True
    cleaned = guardrail_result.cleaned_text
    state["cleaned_text"] = cleaned
    state["redacted_text"] = guardrail_result.redacted_text
    state["guardrails"] = {
        "detected_pii": guardrail_result.detected_pii,
        "jailbreak_detected": guardrail_result.jailbreak_detected,
        "exfiltration_detected": guardrail_result.exfiltration_detected,
        "tool_misuse_detected": guardrail_result.tool_misuse_detected,
        "model_misuse_detected": guardrail_result.model_misuse_detected,
        "content_filtered": guardrail_result.content_filtered,
        "filtered_categories": guardrail_result.filtered_categories,
        "validation_errors": guardrail_result.validation_errors,
        "risk_labels": guardrail_result.risk_labels,
        "llm_allowed": guardrail_result.should_use_llm,
    }
    state["ingestion_ts"] = datetime.now(timezone.utc).isoformat()
    await _emit(queue, "agent_completed", {"agent": "Ingest", "node": "ingest"})
    return state


async def _node_analyse(state: GraphState, queue: Optional[asyncio.Queue]) -> GraphState:
    await _emit(queue, "agent_started", {"agent": "RequestAnalyzer", "node": "analyse"})
    text = state.get("redacted_text") or state.get("cleaned_text", "")
    if not state.get("guardrails", {}).get("llm_allowed", True):
        result = _fallback_analyse(text)
        state["analysis_framework"] = "guarded_fallback"
        state.update(result)
        await _emit(
            queue,
            "agent_completed",
            {"agent": "RequestAnalyzer", "node": "analyse", "confidence": result.get("confidence_score")},
        )
        return state

    if crewai_ready():
        result = await _crewai_request_analyzer(text)
        state["analysis_framework"] = "CrewAI"
    elif ollama_available():
        result = await _ollama_request_analyzer(text)
        state["analysis_framework"] = "Ollama"
    else:
        result = _fallback_analyse(text)
        state["analysis_framework"] = "fallback"

    state.update(result)
    await _emit(
        queue,
        "agent_completed",
        {"agent": "RequestAnalyzer", "node": "analyse", "confidence": result.get("confidence_score")},
    )
    return state


async def _node_generate(
    state: GraphState,
    queue: Optional[asyncio.Queue],
    improvement_hints: list | None = None,
) -> GraphState:
    await _emit(queue, "agent_started", {"agent": "NoteGenerator", "node": "generate"})

    rag_context = state.get("rag_context", "")
    if not state.get("guardrails", {}).get("llm_allowed", True):
        result = _fallback_generate(state)
        state["generation_framework"] = "guarded_fallback"
    elif crewai_ready():
        result = await _crewai_note_generator(state, rag_context, improvement_hints or [])
        state["generation_framework"] = "CrewAI"
    elif ollama_available():
        result = await _ollama_note_generator(state, rag_context, improvement_hints or [])
        state["generation_framework"] = "Ollama"
    else:
        result = _fallback_generate(state)
        state["generation_framework"] = "fallback"

    state.update(result)
    await _emit(queue, "agent_completed", {"agent": "NoteGenerator", "node": "generate"})
    return state


async def _node_sla_calc(state: GraphState, queue: Optional[asyncio.Queue]) -> GraphState:
    await _emit(queue, "agent_started", {"agent": "SLACalculator", "node": "sla_calc"})

    priority = state.get("priority", "Medium")
    req_type = state.get("request_type", "Other")
    hours = settings.SLA_MATRIX.get(priority, {}).get(req_type, 24)
    created = datetime.now(timezone.utc)
    due_date = created + timedelta(hours=hours)
    breach_risk = "HIGH" if hours <= 4 else ("MEDIUM" if hours <= 16 else "LOW")

    state["due_date"] = due_date.isoformat()
    state["sla_hours"] = hours
    state["breach_risk"] = breach_risk
    state["business_priority"] = "P1" if priority in ("Critical", "High") else "P2"

    await _emit(
        queue,
        "agent_completed",
        {"agent": "SLACalculator", "node": "sla_calc", "due_date": state["due_date"]},
    )
    return state


async def _node_quality(state: GraphState, queue: Optional[asyncio.Queue]) -> GraphState:
    await _emit(queue, "agent_started", {"agent": "QualityGuard", "node": "quality"})

    notes = f"{state.get('ai_summary', '')} {state.get('ai_details', '')} {state.get('ai_next_action', '')}"
    if not state.get("guardrails", {}).get("llm_allowed", True):
        result = _fallback_quality(notes)
        state["quality_framework"] = "guarded_fallback"
    elif crewai_ready():
        result = await _crewai_quality_guard(notes, state.get("cleaned_text", ""))
        state["quality_framework"] = "CrewAI"
    elif ollama_available():
        result = await _ollama_quality_guard(notes, state.get("cleaned_text", ""))
        state["quality_framework"] = "Ollama"
    else:
        result = _fallback_quality(notes)
        state["quality_framework"] = "fallback"

    state.update(result)
    await _emit(
        queue,
        "agent_completed",
        {"agent": "QualityGuard", "node": "quality", "score": result.get("quality_score")},
    )
    return state


async def _node_enrich(state: GraphState, queue: Optional[asyncio.Queue]) -> GraphState:
    await _emit(queue, "agent_started", {"agent": "RAGEnrich", "node": "enrich"})
    if not state.get("guardrails", {}).get("llm_allowed", True):
        state["rag_context"] = "[]"
        await _emit(queue, "agent_completed", {"agent": "RAGEnrich", "node": "enrich", "skipped": True})
        return state
    try:
        from app.services.rag_service import retrieve_similar

        query = f"{state.get('ai_summary', '')} {state.get('ai_details', '')}"
        results = await retrieve_similar(query, top_k=settings.RAG_TOP_K)
        state["rag_context"] = json.dumps(results)
    except Exception as exc:
        logger.warning("RAG enrich failed: %s", exc)
        state["rag_context"] = "[]"
    await _emit(queue, "agent_completed", {"agent": "RAGEnrich", "node": "enrich"})
    return state


def _build_safe_description(state: dict) -> str:
    return state.get("redacted_text") or state.get("cleaned_text") or state.get("raw_description", "")


def _ensure_ai_note_fields(state: dict) -> dict:
    needs_fallback = not any(str(state.get(field, "")).strip() for field in ("ai_summary", "ai_details", "ai_next_action"))
    if needs_fallback:
        logger.warning("AI note fields missing; applying deterministic fallback")
        state.update(_fallback_generate(state))

    state["ai_summary"] = str(state.get("ai_summary", "")).strip() or DEFAULT_AI_SUMMARY
    state["ai_details"] = str(state.get("ai_details", "")).strip() or DEFAULT_AI_DETAILS
    state["ai_next_action"] = str(state.get("ai_next_action", "")).strip() or DEFAULT_AI_NEXT_ACTION
    return state


def _ensure_quality_fields(state: dict) -> dict:
    notes = f"{state.get('ai_summary', '')} {state.get('ai_details', '')} {state.get('ai_next_action', '')}".strip()
    score = state.get("quality_score")
    framework = state.get("quality_framework", "fallback")
    if score is None or (framework in {"fallback", "guarded_fallback"} and float(score or 0.0) <= 0.0):
        logger.warning("Quality score missing or defaulted; deriving deterministic score from final notes")
        fallback_quality = _fallback_quality(notes)
        state["quality_score"] = fallback_quality["quality_score"]
        state["approved"] = fallback_quality["approved"]
        state["improvement_suggestions"] = fallback_quality["improvement_suggestions"]
    return state


def _normalize_quality_result(result: dict, notes: str) -> dict:
    fallback_quality = _fallback_quality(notes)
    quality_score = float(result.get("quality_score", 0.0) or 0.0)
    if quality_score <= 0.0:
        result["quality_score"] = fallback_quality["quality_score"]
        result["approved"] = fallback_quality["approved"]
        result["improvement_suggestions"] = fallback_quality["improvement_suggestions"]
        return result

    if not result.get("improvement_suggestions"):
        result["improvement_suggestions"] = fallback_quality["improvement_suggestions"] if quality_score < settings.QUALITY_SCORE_RETRY_THRESHOLD else []
    if "approved" not in result:
        result["approved"] = quality_score >= settings.QUALITY_SCORE_RETRY_THRESHOLD
    return result


async def run_pipeline_async(request_id: str, payload: dict, queue: Optional[asyncio.Queue]) -> dict:
    """Run the primary AI pipeline with quality retries."""
    run_id = str(uuid.uuid4())
    start_ms = time.perf_counter()
    deadline = start_ms + settings.AI_PIPELINE_MAX_SECONDS
    langsmith_trace = _start_langsmith_trace(request_id, payload)

    state = GraphState(
        {
            "request_id": request_id,
            "run_id": run_id,
            "raw_description": payload.get("raw_description", ""),
            "request_type": payload.get("request_type", "Other"),
            "priority": payload.get("priority", "Medium"),
            "source_channel": payload.get("source_channel", "Portal"),
            "requestor_email": payload.get("requestor_email", ""),
            "retries": 0,
        }
    )
    if langsmith_trace:
        trace_id = getattr(langsmith_trace, "trace_id", None) or getattr(langsmith_trace, "id", None)
        if trace_id:
            state["langsmith_trace_id"] = str(trace_id)

    logger.info("Pipeline start: request_id=%s run_id=%s", request_id, run_id)
    try:
        state = await _node_ingest(state, queue)
        state = await _node_analyse(state, queue)
        state = await _node_enrich(state, queue)

        improvement_hints: list[str] = []
        for attempt in range(settings.MAX_QUALITY_RETRIES + 1):
            if time.perf_counter() >= deadline:
                logger.warning("Pipeline time budget exceeded for %s; stopping retries", request_id)
                break
            state["retries"] = attempt
            state = await _node_generate(state, queue, improvement_hints)
            state = await _node_quality(state, queue)

            score = state.get("quality_score", 100)
            if (
                score >= settings.QUALITY_SCORE_RETRY_THRESHOLD
                or attempt >= settings.MAX_QUALITY_RETRIES
                or time.perf_counter() >= deadline
            ):
                break
            improvement_hints = state.get("improvement_suggestions", [])
            logger.info(
                "Quality score %s < threshold, retrying (%s/%s)",
                score,
                attempt + 1,
                settings.MAX_QUALITY_RETRIES,
            )

        state = await _node_sla_calc(state, queue)
        state = _ensure_ai_note_fields(state)
        state = _ensure_quality_fields(state)
        state["frameworks_used"] = {
            "analysis": state.get("analysis_framework", "fallback"),
            "generation": state.get("generation_framework", "fallback"),
            "quality": state.get("quality_framework", "fallback"),
        }
        state["processing_ms"] = int((time.perf_counter() - start_ms) * 1000)
        state["pipeline_run_id"] = run_id
        if langsmith_trace:
            state["langsmith_trace_id"] = _finish_langsmith_trace(
                langsmith_trace,
                outputs={
                    "frameworks_used": state.get("frameworks_used", {}),
                    "processing_ms": state["processing_ms"],
                    "quality_score": state.get("quality_score"),
                    "ai_summary": state.get("ai_summary", ""),
                },
            )
        logger.info(
            "Pipeline complete: %s in %sms, score=%s",
            request_id,
            state["processing_ms"],
            state.get("quality_score"),
        )
        return state
    except Exception as exc:
        if langsmith_trace:
            state["langsmith_trace_id"] = _finish_langsmith_trace(langsmith_trace, error=str(exc))
        raise


async def run_pipeline_fallback(request_id: str, payload: dict, queue: Optional[asyncio.Queue]) -> dict:
    """Deterministic no-LLM fallback pipeline."""
    logger.warning("Running FALLBACK pipeline for %s", request_id)
    langsmith_trace = _start_langsmith_trace(request_id, payload)
    state = GraphState(
        {
            "raw_description": payload.get("raw_description", ""),
            "request_type": payload.get("request_type", "Other"),
            "priority": payload.get("priority", "Medium"),
            "source_channel": payload.get("source_channel", "Portal"),
            "requestor_email": payload.get("requestor_email", ""),
        }
    )
    state = await _node_ingest(state, queue)
    state.update(_fallback_analyse(state.get("cleaned_text", "")))
    state.update(_fallback_generate(state))
    state.update(_fallback_quality(state.get("ai_summary", "")))
    state = _ensure_ai_note_fields(state)
    state = _ensure_quality_fields(state)
    state["is_fallback"] = True
    state["frameworks_used"] = {"analysis": "fallback", "generation": "fallback", "quality": "fallback"}
    state["processing_ms"] = 50
    if langsmith_trace:
        state["langsmith_trace_id"] = _finish_langsmith_trace(
            langsmith_trace,
            outputs={
                "frameworks_used": state["frameworks_used"],
                "processing_ms": state["processing_ms"],
                "quality_score": state.get("quality_score"),
                "ai_summary": state.get("ai_summary", ""),
            },
        )
    return state


async def _crewai_request_analyzer(text: str) -> dict:
    prompt = f"""
Analyze this IT request and return JSON only.

Request text:
{text}

JSON schema:
{{
  "sentiment": "Urgent|Neutral",
  "ai_tags": ["tag1", "tag2"],
  "complexity": "Low|Medium|High",
  "confidence_score": 0.0,
  "intent_category": "string",
  "urgency_level": "LOW|NORMAL|HIGH"
}}
""".strip()
    try:
        response = await _run_crewai_json_task(
            role="RequestAnalyzer",
            goal="Classify incoming IT requests into structured metadata.",
            backstory="You are a service desk triage analyst focused on accurate categorisation.",
            task_description=prompt,
        )
        result = _parse_json_object(response)
        return validate_analysis_output(result)
    except Exception as exc:
        logger.warning("CrewAI analyzer failed, trying direct Ollama: %s", exc)
        if ollama_available():
            return await _ollama_request_analyzer(text)
        return _fallback_analyse(text)


async def _ollama_request_analyzer(text: str) -> dict:
    prompt = f"""
Analyze this IT request and return JSON only.

Request text:
{text}

JSON schema:
{{
  "sentiment": "Urgent|Neutral",
  "ai_tags": ["tag1", "tag2"],
  "complexity": "Low|Medium|High",
  "confidence_score": 0.0,
  "intent_category": "string",
  "urgency_level": "LOW|NORMAL|HIGH"
}}
""".strip()
    try:
        result = await _run_ollama_json_task(prompt)
        return validate_analysis_output(result)
    except Exception as exc:
        logger.warning("Ollama analyzer failed, using fallback: %s", exc)
        return _fallback_analyse(text)


async def _crewai_note_generator(state: dict, rag_context: str, hints: list) -> dict:
    prompt = f"""
Rewrite the request into structured IT service desk notes and return JSON only.

Instructions:
- Correct spelling, grammar, and obvious phrasing errors.
- Preserve the original business meaning and technical context.
- Do not invent facts that are not present in the request.
- Expand abbreviations only when the meaning is obvious from context.
- Do not copy the user's wording verbatim unless a product name or exact error phrase is necessary.
- Remove first-person phrasing such as "I need", "I want", or "please help".
- Make ai_summary a short professional summary suitable for a ticket list view.
- ai_summary must be one sentence, 8-20 words, grammatically correct, and written in professional service-desk language.
- ai_summary must not contain ellipses, repeated punctuation, chat slang, or raw user-style wording.
- Make ai_details a cleaned, analyst-friendly version of the request with the key context preserved.
- Make ai_next_action concrete and operational.

Rewrite example:
- Bad ai_summary: "I want to know the leave policy of the company"
- Good ai_summary: "Request for information on company leave policy and available leave balance."

Request type: {state.get("request_type", "Other")}
Priority: {state.get("priority", "Medium")}
Requester email: {state.get("requestor_email", "")}
Source channel: {state.get("source_channel", "Portal")}
Description:
{_build_safe_description(state)}

RAG context:
{rag_context or "[]"}

Improvement hints:
{json.dumps(hints or [])}

JSON schema:
{{
  "ai_summary": "string",
  "ai_details": "string",
  "ai_next_action": "string"
}}
""".strip()
    try:
        response = await _run_crewai_json_task(
            role="NoteGenerator",
            goal="Write concise, professional service desk notes.",
            backstory="You produce support notes that are actionable and easy for analysts to approve.",
            task_description=prompt,
        )
        result = _parse_json_object(response)
        return validate_notes_output(result)
    except Exception as exc:
        logger.warning("CrewAI note generator failed, trying direct Ollama: %s", exc)
        if ollama_available():
            return await _ollama_note_generator(state, rag_context, hints)
        return _fallback_generate(state)


async def _ollama_note_generator(state: dict, rag_context: str, hints: list) -> dict:
    prompt = f"""
Rewrite the request into structured IT service desk notes and return JSON only.

Instructions:
- Correct spelling, grammar, and phrasing errors.
- Preserve the original business meaning and technical context.
- Do not invent facts that are not present in the request.
- Do not copy the user's wording verbatim unless a product name or exact error phrase is necessary.
- Remove first-person phrasing such as "I need", "I want", or "please help".
- Make ai_summary a short professional summary suitable for a ticket list view.
- ai_summary must be one sentence, 8-20 words, grammatically correct, and written in professional service-desk language.
- ai_summary must not contain ellipses, repeated punctuation, chat slang, or raw user-style wording.
- Make ai_details a cleaned, analyst-friendly version of the request with the key context preserved.
- Make ai_next_action concrete and operational.

Rewrite example:
- Bad ai_summary: "I want to know the leave policy of the company"
- Good ai_summary: "Request for information on company leave policy and available leave balance."

Request type: {state.get("request_type", "Other")}
Priority: {state.get("priority", "Medium")}
Requester email: {state.get("requestor_email", "")}
Source channel: {state.get("source_channel", "Portal")}
Description:
{_build_safe_description(state)}

RAG context:
{rag_context or "[]"}

Improvement hints:
{json.dumps(hints or [])}

JSON schema:
{{
  "ai_summary": "string",
  "ai_details": "string",
  "ai_next_action": "string"
}}
""".strip()
    try:
        result = await _run_ollama_json_task(prompt)
        return validate_notes_output(result)
    except Exception as exc:
        logger.warning("Ollama note generator failed, using fallback: %s", exc)
        return _fallback_generate(state)


async def _crewai_quality_guard(notes: str, original: str) -> dict:
    prompt = f"""
Review the generated support notes against the original request and return JSON only.

Original request:
{original}

Generated notes:
{notes}

JSON schema:
{{
  "quality_score": 0.0,
  "approved": true,
  "improvement_suggestions": ["suggestion 1", "suggestion 2"]
}}
""".strip()
    try:
        response = await _run_crewai_json_task(
            role="QualityGuard",
            goal="Score support notes for quality and approve only when they are actionable.",
            backstory="You are a strict QA reviewer for service desk note quality.",
            task_description=prompt,
        )
        result = _parse_json_object(response)
        validated = validate_quality_output(result)
        return _normalize_quality_result(validated, notes)
    except Exception as exc:
        logger.warning("CrewAI quality guard failed, trying direct Ollama: %s", exc)
        if ollama_available():
            return await _ollama_quality_guard(notes, original)
        return _fallback_quality(notes)


async def _ollama_quality_guard(notes: str, original: str) -> dict:
    prompt = f"""
Review the generated support notes against the original request and return JSON only.

Original request:
{original}

Generated notes:
{notes}

JSON schema:
{{
  "quality_score": 0.0,
  "approved": true,
  "improvement_suggestions": ["suggestion 1", "suggestion 2"]
}}
""".strip()
    try:
        result = await _run_ollama_json_task(prompt)
        validated = validate_quality_output(result)
        return _normalize_quality_result(validated, notes)
    except Exception as exc:
        logger.warning("Ollama quality guard failed, using fallback: %s", exc)
        return _fallback_quality(notes)


async def _run_crewai_json_task(role: str, goal: str, backstory: str, task_description: str) -> str:
    def _invoke() -> str:
        from crewai import Agent, Crew, Process, Task

        llm = _build_crewai_llm()
        agent_kwargs = {
            "role": role,
            "goal": goal,
            "backstory": backstory,
            "verbose": False,
            "allow_delegation": False,
        }
        if llm is not None:
            agent_kwargs["llm"] = llm

        agent = Agent(**agent_kwargs)
        task = Task(
            description=task_description,
            expected_output="Return a single JSON object only.",
            agent=agent,
        )
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )
        result = crew.kickoff()
        return str(result)

    return await asyncio.to_thread(_invoke)


async def _run_ollama_json_task(prompt: str) -> dict:
    base_url = settings.OLLAMA_BASE_URL.rstrip("/")
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": settings.LLM_TEMPERATURE,
            "num_predict": min(settings.LLM_MAX_TOKENS, 400),
        },
    }
    async with httpx.AsyncClient(timeout=float(settings.OLLAMA_REQUEST_TIMEOUT_SECONDS)) as client:
        response = await client.post(f"{base_url}/api/generate", json=payload)
        response.raise_for_status()
        body = response.json()
    return _parse_json_object(body.get("response", ""))


def _build_crewai_llm() -> Any:
    try:
        from crewai import LLM
    except Exception:
        return f"ollama/{settings.OLLAMA_MODEL}"

    attempts = [
        {"model": f"ollama/{settings.OLLAMA_MODEL}", "base_url": settings.OLLAMA_BASE_URL},
        {"model": settings.OLLAMA_MODEL, "base_url": settings.OLLAMA_BASE_URL},
        {"model": f"ollama/{settings.OLLAMA_MODEL}", "api_base": settings.OLLAMA_BASE_URL},
    ]
    for kwargs in attempts:
        try:
            return LLM(**kwargs)
        except Exception:
            continue
    return f"ollama/{settings.OLLAMA_MODEL}"


def _parse_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")
    return json.loads(match.group(0))


def _fallback_analyse(text: str) -> dict:
    words = text.lower().split()
    urgent_keywords = {"urgent", "critical", "asap", "immediately", "emergency", "broken", "down", "cannot"}
    sentiment = "Urgent" if any(word in urgent_keywords for word in words) else "Neutral"
    tags = ["IT-Request"]
    if "access" in words:
        tags.append("Access-Control")
    if "password" in words or "login" in words:
        tags.append("Authentication")
    if "performance" in words or "slow" in words:
        tags.append("Performance")
    return {
        "sentiment": sentiment,
        "ai_tags": tags,
        "complexity": "Medium",
        "confidence_score": 0.75,
        "intent_category": "IT Support",
        "urgency_level": "HIGH" if sentiment == "Urgent" else "NORMAL",
    }


def _fallback_generate(state: dict) -> dict:
    text = _build_safe_description(state)
    req_type = state.get("request_type", "Request")
    normalized = _normalize_request_text(text)
    summary = _build_summary(normalized, req_type)
    return {
        "ai_summary": summary,
        "ai_details": (
            f"Request received via {state.get('source_channel', 'Portal')}. "
            f"Priority: {state.get('priority', 'Medium')}. "
            f"Cleaned request description: {normalized[:700]}"
        ),
        "ai_next_action": (
            "1. Review request details.\n"
            f"2. Verify requestor identity ({state.get('requestor_email', '')}).\n"
            "3. Assign to appropriate team.\n"
            "4. Acknowledge within SLA window."
        ),
    }


def _fallback_quality(notes: str) -> dict:
    word_count = len(notes.split())
    score = min(100.0, max(0.0, 40.0 + word_count * 0.5))
    return {
        "quality_score": score,
        "approved": score >= settings.QUALITY_SCORE_RETRY_THRESHOLD,
        "improvement_suggestions": (
            ["Add more detail to the summary", "Include specific next action steps"]
            if score < settings.QUALITY_SCORE_RETRY_THRESHOLD
            else []
        ),
    }


def _normalize_request_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    cleaned = re.sub(r"\bi\b", "I", cleaned)

    replacements = {
        r"\bunble\b": "unable",
        r"\bplese\b": "please",
        r"\bteh\b": "the",
        r"\bhear me\b": "hear me",
        r"\bmic issue\b": "microphone issue",
        r"\basap\b": "as soon as possible",
        r"\bim\b": "I'm",
        r"\bcant\b": "can't",
        r"\bdont\b": "don't",
        r"\bwont\b": "won't",
    }
    for pattern, replacement in replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Normalize some common service-desk wording around Teams audio issues.
    cleaned = re.sub(
        r"Teams microphone issue unable to hear",
        "Teams microphone issue. Unable to hear audio",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"Teams mic issue unable to hear",
        "Teams microphone issue. Unable to hear audio",
        cleaned,
        flags=re.IGNORECASE,
    )

    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _build_summary(text: str, req_type: str) -> str:
    summary_text = sanitize_free_text_output(text[:180].rstrip(), max_length=180)
    if len(text) > 180:
        summary_text += "..."
    return f"[{req_type}] {summary_text}"


async def _emit(queue: Optional[asyncio.Queue], event: str, data: dict):
    if queue:
        await queue.put({"event": event, "data": data})
