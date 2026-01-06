from __future__ import annotations
from typing import Any, Dict

from stages.prompt import enhance_prompt
from stages.prompt_firewall import sanitize_prompt
from stages.llm import stream_code
from stages.semgrep_registry import run_semgrep_registry_over_blob
from stages.uml_pipeline import run_uml_pipeline_over_blob


async def run_pipeline(prompt: str) -> Dict[str, Any]:
    """
    Main pipeline: sanitize -> enhance -> generate -> SAST -> UML diagram
    Return code + security report (Semgrep + UML) to the API layer
    """

    # 1) Prompt hygiene (firewall + enhancement)
    safe_prompt = sanitize_prompt(prompt or "")
    enhanced = enhance_prompt(safe_prompt)
    hardened_prompt: str = enhanced["text"]
    policy_version: str = enhanced.get("policy_version", "v1")

    # 2) LLM code generation (stream into a single string)
    parts: list[str] = []
    async for chunk in stream_code(hardened_prompt):
        if not chunk:
            continue
        parts.append(chunk)

    code_blob = "".join(parts).strip()
    if not code_blob:
        code_blob = "// empty"

    # 3) Static analysis (Semgrep) over the generated code
    semgrep_report = run_semgrep_registry_over_blob(code_blob)

    # 4) UML pipeline (CIR -> PlantUML -> SVG) over the same blob
    uml_report = run_uml_pipeline_over_blob(code_blob)

    # 5) Final result consumed by FastAPI endpoint (/api/generate)
    return {
        "code": code_blob,
        "report": {
            "policy_version": policy_version,
            "prompt_after_enhancement": hardened_prompt,
            "semgrep": semgrep_report,
            "uml": uml_report,
        },
        "decision": "CODE_ONLY",
    }
