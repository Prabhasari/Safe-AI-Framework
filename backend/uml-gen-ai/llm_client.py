# backend/uml-gen-ai/llm_client.py

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv  # type: ignore
import google.generativeai as genai  # type: ignore

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "").strip() or "gemini-2.5-flash"

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Put it in .env for UML AI generator.")

genai.configure(api_key=GEMINI_API_KEY)

GEN_CFG = {
    "temperature": 0.2,
    "max_output_tokens": 4096,
    "top_p": 0.9,
    "top_k": 40,
}

BASE_SYSTEM = """
You are an assistant that generates **PlantUML** diagrams from provided context.

Hard rules:
- Output MUST be valid PlantUML between @startuml and @enduml.
- Do NOT explain anything in natural language.
- Do NOT wrap the result in ``` fences.
- No external includes or URLs (!include, !includeurl, !pragma, etc.).
- Use simple, standard UML notation only.
""".strip()

CLASS_RULES = """
Diagram type: CLASS

You MUST:
- Use PlantUML class syntax with braces:
  class ClassName {
    +field: Type
    +method(param: Type): ReturnType
  }
- Include ATTRIBUTES and METHODS for each class when provided in the context.
- If the context lists fields/methods for a class, include at least:
  - up to 10 fields (if available)
  - up to 12 methods (if available)
- Prefer showing relationships:
  - inheritance: A --|> B
  - implementation: A ..|> I
  - association: A --> B
  - dependency: A ..> B
- DO NOT generate a package diagram:
  - Do NOT wrap classes inside "package { }" blocks.
  - Do NOT focus on packages; focus on class structure.
- If a class has no listed members in context, you may leave it empty or add 1 placeholder method ONLY if needed.
""".strip()

PACKAGE_RULES = """
Diagram type: PACKAGE

You MUST:
- Group by packages/namespaces using:
  package "pkg.name" {
    class A
  }
- Keep class bodies minimal (no need to list methods unless essential).
- Show dependencies between packages or major classes.
""".strip()

SEQUENCE_RULES = """
Diagram type: SEQUENCE

You MUST:
- Use a small set of main actors/objects.
- Show a high-level call flow using -> arrows.
- Keep it concise.
""".strip()

COMPONENT_RULES = """
Diagram type: COMPONENT

You MUST:
- Use components/modules and dependencies.
- Use component blocks or rectangles.
- Keep it high-level.
""".strip()


def _system_for(diagram_type: str) -> str:
    dt = (diagram_type or "class").lower().strip()
    if dt == "package":
        return f"{BASE_SYSTEM}\n\n{PACKAGE_RULES}"
    if dt == "sequence":
        return f"{BASE_SYSTEM}\n\n{SEQUENCE_RULES}"
    if dt == "component":
        return f"{BASE_SYSTEM}\n\n{COMPONENT_RULES}"
    return f"{BASE_SYSTEM}\n\n{CLASS_RULES}"


def _build_prompt(context: str, diagram_type: str) -> str:
    dt = diagram_type.lower().strip()
    if dt not in ("class", "package", "sequence", "component"):
        dt = "class"

    # Extra “in-prompt” constraint helps Gemini a lot
    extra = ""
    if dt == "class":
        extra = """
[IMPORTANT]
This is a CLASS diagram.
If the context includes sections named "FIELDS:" and "METHODS:", you MUST render them inside the class braces.
Do NOT output a package diagram.
""".strip()

    return f"""
[TASK]
Generate a {dt} UML diagram in PlantUML from the following context.

{extra}

[CONTEXT]
\"\"\"CONTEXT_START
{context}
CONTEXT_END\"\"\"

[OUTPUT]
Return ONLY valid PlantUML text:

@startuml
...
@enduml
""".strip()


def _extract_plantuml(text: str) -> str:
    if not text:
        raise RuntimeError("Empty response from Gemini when generating PlantUML.")

    lower = text.lower()
    start_idx = lower.find("@startuml")
    end_idx = lower.rfind("@enduml")

    if start_idx == -1 or end_idx == -1:
        return text.strip()

    end_idx += len("@enduml")
    return text[start_idx:end_idx].strip()


def generate_plantuml_from_context(
    context: str,
    diagram_type: Literal["class", "package", "sequence", "component"] = "class",
) -> str:
    if not context or not context.strip():
        raise RuntimeError("No context provided for AI UML generation.")

    dt = (diagram_type or "class").lower().strip()
    prompt = _build_prompt(context, dt)

    model = genai.GenerativeModel(
        GEMINI_MODEL,
        generation_config=GEN_CFG,
        system_instruction=_system_for(dt),
    )

    try:
        resp = model.generate_content(prompt)
    except Exception as e:
        raise RuntimeError(f"Gemini call failed: {type(e).__name__}: {e}") from e

    parts_text = ""
    if hasattr(resp, "candidates") and resp.candidates:
        for cand in resp.candidates:
            content = getattr(cand, "content", None)
            if content and getattr(content, "parts", None):
                for p in content.parts:
                    parts_text += (getattr(p, "text", "") or "")
    else:
        parts_text = getattr(resp, "text", "") or ""

    plantuml = _extract_plantuml(parts_text)
    if "@startuml" not in plantuml or "@enduml" not in plantuml:
        raise RuntimeError("Gemini did not return a valid @startuml...@enduml block.")

    return plantuml
