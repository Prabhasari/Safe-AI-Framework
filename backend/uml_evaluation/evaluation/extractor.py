# extractor.py
# Parses PlantUML class diagram text and extracts elements as sets.
# These sets are compared against CIR ground truth to compute metrics.

import re
from typing import Dict, Set, Optional


def extract_from_plantuml(puml: str) -> Dict[str, Set[str]]:
    result = {
        "classes":    set(),
        "fields":     set(),
        "methods":    set(),
        "inherits":   set(),
        "implements": set(),
        "associates": set(),
        "depends_on": set(),
    }

    if not puml:
        return result

    current_class: Optional[str] = None

    for line in puml.splitlines():
        s = line.strip()

        # ── Class / interface declaration ──────────────────────────
        m = re.match(r'^(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)', s)
        if m:
            current_class = m.group(1)
            result["classes"].add(current_class)
            continue

        if s == "}":
            current_class = None
            continue

        # ── Members inside a class block ───────────────────────────
        if current_class:
            # Field:  + fieldName : Type
            if re.match(r'^[+\-#~]', s) and "(" not in s and ":" in s:
                fm = re.match(r'^[+\-#~]\s*(?:\{.*?\}\s*)?(\w+)\s*:', s)
                if fm:
                    result["fields"].add(f"{current_class}.{fm.group(1)}")
                continue

            # Method: + methodName(...)
            if re.match(r'^[+\-#~]', s) and "(" in s:
                mm = re.match(r'^[+\-#~]\s*(?:\{.*?\}\s*)?(\w+)\s*\(', s)
                if mm:
                    result["methods"].add(f"{current_class}.{mm.group(1)}")
                continue

        # ── Relationship arrows (outside class blocks) ─────────────
        # Inheritance:     Child --|> Parent
        m = re.match(r'^(\w+)\s*--\|>\s*(\w+)', s)
        if m:
            result["inherits"].add(f"{m.group(1)}->{m.group(2)}")
            continue

        # Implementation:  Child ..|> Interface
        m = re.match(r'^(\w+)\s*\.\.\|>\s*(\w+)', s)
        if m:
            result["implements"].add(f"{m.group(1)}->{m.group(2)}")
            continue

        # Association:     ClassA --> ClassB  or  ClassA --> "1" ClassB
        m = re.match(r'^(\w+)\s*-->\s*(?:"[^"]*"\s*)?(\w+)', s)
        if m:
            result["associates"].add(f"{m.group(1)}->{m.group(2)}")
            continue

        # Dependency:      ClassA ..> ClassB
        m = re.match(r'^(\w+)\s*\.\.\>\s*(\w+)', s)
        if m:
            result["depends_on"].add(f"{m.group(1)}->{m.group(2)}")
            continue

    return result