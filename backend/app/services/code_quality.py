"""
NEXUS SDLC - AutoGen Code Quality Service
3-agent group chat: StaticAnalyzer ↔ QualityReviewer ↔ QualityOrchestrator
10-point checklist, A-F grade, PASS/WARN/FAIL per item.
"""

import json
import re
import logging
from typing import Optional

from app.core.config import settings
from app.services.ai_frameworks import autogen_ready
from app.services.guardrails import guard_code_quality_input, validate_code_quality_llm_output

logger = logging.getLogger("nexus.code_quality")

DEFAULT_CHECKLIST = [
    {"id": "CQ-001", "category": "Security",       "check": "No hardcoded credentials",       "severity": "Critical"},
    {"id": "CQ-002", "category": "Security",       "check": "Input validation present",        "severity": "High"},
    {"id": "CQ-003", "category": "Error Handling", "check": "Exception handling exists",       "severity": "High"},
    {"id": "CQ-004", "category": "Design",         "check": "Single Responsibility Principle", "severity": "Medium"},
    {"id": "CQ-005", "category": "Documentation",  "check": "Docstrings/JSDoc present",        "severity": "Medium"},
    {"id": "CQ-006", "category": "Performance",    "check": "No N+1 query patterns",           "severity": "High"},
    {"id": "CQ-007", "category": "Maintainability","check": "DRY - no code duplication",       "severity": "Medium"},
    {"id": "CQ-008", "category": "Testability",    "check": "No tight coupling",               "severity": "Medium"},
    {"id": "CQ-009", "category": "Standards",      "check": "Consistent naming conventions",   "severity": "Low"},
    {"id": "CQ-010", "category": "Architecture",   "check": "Separation of concerns",          "severity": "High"},
]

SEVERITY_WEIGHTS = {"Critical": 25, "High": 15, "Medium": 10, "Low": 5}
GRADE_THRESHOLDS = [(90,"A"),(80,"B"),(70,"C"),(60,"D"),(0,"F")]
GRADE_LABELS = {
    "A": "Production Ready",
    "B": "Approved with Minor Notes",
    "C": "Needs Refactoring",
    "D": "Significant Issues Found",
    "F": "Not Ready — Major Problems",
}


class StaticAnalyzerAgent:
    """First-pass: security, N+1, anti-patterns."""

    def analyze(self, code: str, language: str) -> list[dict]:
        findings = []

        # CQ-001: hardcoded credentials
        cred_pattern = re.compile(
            r'(password|api_key|secret|token|passwd|pwd)\s*=\s*["\'][^"\']{4,}["\']',
            re.IGNORECASE
        )
        findings.append({
            "id": "CQ-001",
            "status": "FAIL" if cred_pattern.search(code) else "PASS",
            "observation": "Hardcoded credential pattern detected." if cred_pattern.search(code)
                           else "No hardcoded credentials found.",
            "suggestions": ["Use environment variables or a secrets manager."] if cred_pattern.search(code) else [],
        })

        # CQ-002: input validation
        validation_libs = ["pydantic", "zod", "joi", "marshmallow", "cerberus", "validate", "schema"]
        has_validation = any(lib in code.lower() for lib in validation_libs)
        findings.append({
            "id": "CQ-002",
            "status": "PASS" if has_validation else "WARN",
            "observation": "Input validation library detected." if has_validation else "No input validation detected.",
            "suggestions": [] if has_validation else ["Add Pydantic (Python) or Zod (TypeScript) validation at API boundaries."],
        })

        # CQ-003: exception handling
        has_try = bool(re.search(r'\btry\b', code)) and (
            bool(re.search(r'\bcatch\b', code)) or bool(re.search(r'\bexcept\b', code))
        )
        findings.append({
            "id": "CQ-003",
            "status": "PASS" if has_try else "WARN",
            "observation": "Exception handling present." if has_try else "No try/except or try/catch found.",
            "suggestions": [] if has_try else ["Wrap external calls and I/O operations in try/except blocks."],
        })

        # CQ-006: N+1 queries
        n1_pattern = re.compile(r'for\s+\w+\s+in\s+.*:[\s\S]{0,100}(\.query\(|\.filter\(|\.find\(|\.findAll\()', re.MULTILINE)
        has_n1 = bool(n1_pattern.search(code))
        findings.append({
            "id": "CQ-006",
            "status": "FAIL" if has_n1 else "PASS",
            "observation": "Potential N+1 query pattern detected inside loop." if has_n1 else "No N+1 patterns detected.",
            "suggestions": ["Use eager loading, batch queries, or prefetch_related."] if has_n1 else [],
        })

        return findings


class QualityReviewerAgent:
    """Second-pass: SOLID, DRY, naming, documentation, testability."""

    def review(self, code: str, language: str) -> list[dict]:
        findings = []
        lines = code.splitlines()
        functions = re.findall(r'def\s+\w+|function\s+\w+|const\s+\w+\s*=\s*\(', code)
        docstrings = re.findall(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|/\*\*[\s\S]*?\*/', code)
        code_tokens = len(code.split())
        doc_tokens = sum(len(d.split()) for d in docstrings)

        # CQ-004: SRP — long functions
        long_fns = [m.start() for m in re.finditer(r'def\s+\w+|function\s+\w+', code)]
        srp_fail = len(long_fns) > 0 and (len(lines) / max(len(long_fns), 1)) > 50
        findings.append({
            "id": "CQ-004",
            "status": "WARN" if srp_fail else "PASS",
            "observation": f"Average function length > 50 lines detected." if srp_fail else "Function sizes appear reasonable.",
            "suggestions": ["Break large functions into smaller, single-purpose units."] if srp_fail else [],
        })

        # CQ-005: docstrings
        doc_ratio = doc_tokens / max(code_tokens, 1)
        findings.append({
            "id": "CQ-005",
            "status": "PASS" if doc_ratio >= 0.1 else ("WARN" if doc_ratio >= 0.05 else "FAIL"),
            "observation": f"Documentation ratio: {doc_ratio:.1%}",
            "suggestions": [] if doc_ratio >= 0.1 else ["Add docstrings to all public functions and classes."],
        })

        # CQ-007: DRY — duplicate blocks (simplified)
        block_len = 6
        code_blocks = ["\n".join(lines[i:i+block_len]) for i in range(0, len(lines)-block_len, 2)]
        duplicates = len(code_blocks) - len(set(code_blocks))
        findings.append({
            "id": "CQ-007",
            "status": "WARN" if duplicates > 2 else "PASS",
            "observation": f"Found ~{duplicates} potentially duplicated code blocks." if duplicates > 2 else "No significant duplication found.",
            "suggestions": ["Extract duplicated blocks into shared utility functions."] if duplicates > 2 else [],
        })

        # CQ-008: tight coupling
        globals_pattern = re.compile(r'\bglobal\b|\bsingleton\b', re.IGNORECASE)
        has_coupling = bool(globals_pattern.search(code))
        findings.append({
            "id": "CQ-008",
            "status": "WARN" if has_coupling else "PASS",
            "observation": "Global state or singleton usage detected." if has_coupling else "No obvious tight coupling.",
            "suggestions": ["Use dependency injection instead of globals/singletons."] if has_coupling else [],
        })

        # CQ-009: naming conventions
        camel = len(re.findall(r'\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b', code))
        snake = len(re.findall(r'\b[a-z][a-z0-9]*_[a-z][a-z0-9_]*\b', code))
        total_names = camel + snake
        if total_names > 10:
            ratio = min(camel, snake) / total_names
            mixed = ratio > 0.2
        else:
            mixed = False
        findings.append({
            "id": "CQ-009",
            "status": "WARN" if mixed else "PASS",
            "observation": "Mixed camelCase and snake_case naming detected." if mixed else "Naming appears consistent.",
            "suggestions": ["Standardise on one naming convention (snake_case for Python, camelCase for JS)."] if mixed else [],
        })

        # CQ-010: separation of concerns
        db_in_ui = (
            bool(re.search(r'(SELECT|INSERT|UPDATE|DELETE|\.query\()', code, re.IGNORECASE)) and
            bool(re.search(r'(render|return.*jsx|innerHTML|document\.)', code, re.IGNORECASE))
        )
        findings.append({
            "id": "CQ-010",
            "status": "FAIL" if db_in_ui else "PASS",
            "observation": "DB queries and UI rendering code mixed in same unit." if db_in_ui else "Concerns appear separated.",
            "suggestions": ["Separate data access layer from presentation layer."] if db_in_ui else [],
        })

        return findings


class QualityOrchestratorAgent:
    """Resolves disagreements, computes final score and grade."""

    def orchestrate(self, static_findings: list, review_findings: list, custom_checklist: list = None) -> dict:
        all_findings = {f["id"]: f for f in static_findings}
        for f in review_findings:
            if f["id"] not in all_findings:
                all_findings[f["id"]] = f

        # Score calculation
        total_weight = 0
        pass_weight = 0
        for item in DEFAULT_CHECKLIST:
            w = SEVERITY_WEIGHTS.get(item["severity"], 10)
            total_weight += w
            finding = all_findings.get(item["id"])
            if finding:
                if finding["status"] == "PASS":
                    pass_weight += w
                elif finding["status"] == "WARN":
                    pass_weight += w * 0.5
            else:
                pass_weight += w   # assume pass if not checked

        score = round((pass_weight / max(total_weight, 1)) * 100, 1)
        grade = next(g for threshold, g in GRADE_THRESHOLDS if score >= threshold)
        results = list(all_findings.values())

        return {
            "results": results,
            "summary": {
                "score": score,
                "grade": grade,
                "recommendation": GRADE_LABELS[grade],
                "total_checks": len(DEFAULT_CHECKLIST),
                "passed": sum(1 for f in results if f["status"] == "PASS"),
                "warned": sum(1 for f in results if f["status"] == "WARN"),
                "failed": sum(1 for f in results if f["status"] == "FAIL"),
            },
            "agent_framework": "AutoGen-3-Agent-GroupChat",
        }


def run_code_quality(code: str, language: str = "python", custom_checklist: list = None) -> dict:
    """Entry point: run full 3-agent code quality analysis."""
    guardrail_result = guard_code_quality_input(code)
    raw_code = guardrail_result.cleaned_text
    safe_code = guardrail_result.redacted_text or raw_code

    static = StaticAnalyzerAgent().analyze(raw_code, language)
    review = QualityReviewerAgent().review(raw_code, language)
    result = QualityOrchestratorAgent().orchestrate(static, review, custom_checklist)
    result["guardrails"] = {
        "detected_pii": guardrail_result.detected_pii,
        "jailbreak_detected": guardrail_result.jailbreak_detected,
        "exfiltration_detected": guardrail_result.exfiltration_detected,
        "tool_misuse_detected": guardrail_result.tool_misuse_detected,
        "model_misuse_detected": guardrail_result.model_misuse_detected,
        "content_filtered": guardrail_result.content_filtered,
        "filtered_categories": guardrail_result.filtered_categories,
        "risk_labels": guardrail_result.risk_labels,
        "llm_allowed": guardrail_result.should_use_llm,
    }
    result["framework_runtime"] = {
        "autogen_requested": True,
        "autogen_active": False,
        "provider": "ollama" if settings.OLLAMA_MODEL else "heuristic_only",
        "status": "heuristic_only",
        "message": "Heuristic code quality analysis completed.",
    }
    result["analysis_message"] = (
        f"Completed code quality analysis with grade {result['summary']['grade']} "
        f"and score {result['summary']['score']}/100."
    )

    if not guardrail_result.should_use_llm:
        result["framework_runtime"]["status"] = "guardrail_blocked"
        result["framework_runtime"]["message"] = (
            "Guardrails blocked model execution. Displaying local heuristic code quality analysis only."
        )
        if guardrail_result.risk_labels:
            result["analysis_message"] = (
                f"{result['analysis_message']} LLM review skipped due to: {', '.join(guardrail_result.risk_labels)}."
            )
    elif autogen_ready():
        try:
            autogen_result = _run_autogen_group_chat(safe_code, language, result)
            if autogen_result:
                result["framework_runtime"]["autogen_active"] = True
                result["framework_runtime"]["status"] = "autogen_active"
                result["framework_runtime"]["message"] = "AutoGen review completed using Ollama."
                result["autogen_summary"] = autogen_result.get("autogen_summary", "")
                result["autogen_transcript"] = autogen_result.get("autogen_transcript", "")
                result["summary"]["recommendation"] = autogen_result.get(
                    "recommendation", result["summary"]["recommendation"]
                )
                result["agent_framework"] = "AutoGen-3-Agent-GroupChat+Heuristic"
                if result["autogen_summary"]:
                    result["analysis_message"] = result["autogen_summary"]
        except Exception as exc:
            logger.warning("AutoGen execution failed, using heuristic-only output: %s", exc)
            result["framework_runtime"]["status"] = "autogen_fallback"
            result["framework_runtime"]["message"] = (
                "AutoGen timed out or failed. Displaying heuristic code quality analysis."
            )
            result["framework_runtime"]["error"] = str(exc)
            result["analysis_message"] = (
                f"{result['analysis_message']} AutoGen fallback reason: {exc}."
            )
    else:
        result["framework_runtime"]["status"] = "autogen_unavailable"
        result["framework_runtime"]["message"] = "AutoGen is unavailable. Displaying heuristic code quality analysis."
    return result


def _run_autogen_group_chat(code: str, language: str, deterministic_result: dict) -> dict:
    import autogen

    code_excerpt = _prepare_code_excerpt(code)
    model_name = settings.CODE_QUALITY_MODEL or settings.OLLAMA_MODEL
    llm_config = {
        "config_list": [
            {
                "model": model_name,
                "api_key": "ollama",
                "base_url": f"{settings.OLLAMA_BASE_URL}/v1",
            }
        ],
        "temperature": settings.LLM_TEMPERATURE,
        "timeout": settings.OLLAMA_REQUEST_TIMEOUT_SECONDS,
    }

    static_agent = autogen.AssistantAgent(
        name="StaticAnalyzer",
        system_message=(
            "You are the StaticAnalyzer. Review code for security, input validation, "
            "error handling, and performance risks. Be concise."
        ),
        llm_config=llm_config,
    )
    reviewer_agent = autogen.AssistantAgent(
        name="QualityReviewer",
        system_message=(
            "You are the QualityReviewer. Review maintainability, SRP, documentation, "
            "testability, and architecture. Build on the StaticAnalyzer findings."
        ),
        llm_config=llm_config,
    )
    orchestrator_agent = autogen.AssistantAgent(
        name="QualityOrchestrator",
        system_message=(
            "You are the QualityOrchestrator. Summarize the review and produce JSON only: "
            '{"recommendation":"string","autogen_summary":"string"}.'
        ),
        llm_config=llm_config,
    )
    user_proxy = autogen.UserProxyAgent(
        name="QualityRequester",
        human_input_mode="NEVER",
        code_execution_config=False,
    )
    groupchat = autogen.GroupChat(
        agents=[user_proxy, static_agent, reviewer_agent, orchestrator_agent],
        messages=[],
        max_round=settings.AUTOGEN_MAX_ROUNDS,
        speaker_selection_method="round_robin",
    )
    manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=llm_config)
    prompt = (
        f"Language: {language}\n"
        "Code excerpt:\n"
        f"{code_excerpt}\n\n"
        f"Existing deterministic findings:\n{json.dumps(deterministic_result['results'])}\n\n"
        "Focus on the highest-signal issues only. Discuss briefly in at most one message each, "
        "then have QualityOrchestrator return JSON only."
    )
    chat_result = user_proxy.initiate_chat(manager, message=prompt)

    transcript = _extract_autogen_transcript(chat_result)
    payload = validate_code_quality_llm_output(_parse_autogen_json(transcript))
    return {
        "recommendation": payload.get("recommendation", deterministic_result["summary"]["recommendation"]),
        "autogen_summary": payload.get("autogen_summary", ""),
        "autogen_transcript": transcript,
    }


def _extract_autogen_transcript(chat_result) -> str:
    history = getattr(chat_result, "chat_history", None)
    if isinstance(history, list):
        parts = []
        for item in history:
            if isinstance(item, dict):
                speaker = item.get("name") or item.get("role") or "agent"
                content = item.get("content", "")
                parts.append(f"{speaker}: {content}")
        if parts:
            return "\n".join(parts)
    return str(chat_result)


def _parse_autogen_json(transcript: str) -> dict:
    decoder = json.JSONDecoder()
    candidates: list[dict] = []

    for match in re.finditer(r"\{", transcript):
        try:
            payload, _ = decoder.raw_decode(transcript[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            candidates.append(payload)

    for payload in reversed(candidates):
        if "recommendation" in payload or "autogen_summary" in payload:
            return payload

    if candidates:
        return candidates[-1]
    raise ValueError("AutoGen transcript did not contain JSON output")


def _prepare_code_excerpt(code: str) -> str:
    normalized = code.strip()
    if len(normalized) <= settings.AUTOGEN_CODE_MAX_CHARS:
        return normalized

    head_budget = settings.AUTOGEN_CODE_MAX_CHARS // 2
    tail_budget = settings.AUTOGEN_CODE_MAX_CHARS - head_budget
    head = normalized[:head_budget].rstrip()
    tail = normalized[-tail_budget:].lstrip()
    return (
        f"{head}\n\n"
        "... [code truncated for AutoGen review to stay within local model limits] ...\n\n"
        f"{tail}"
    )
