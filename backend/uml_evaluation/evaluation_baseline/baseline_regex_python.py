# baseline_regex_python.py
# Direct regex parser for Python source code — NO AST, NO CIR.
# Naive approach: regex patterns applied directly to raw source text.
# Used as BASELINE to compare against the CIR-based pipeline.
#
# Known limitations (by design):
#   - Cannot detect fields set outside __init__ (dynamic attributes)
#   - Missing type hints = missing field types = missing relationships
#   - Confused by nested generics: Dict[str, List[float]]
#   - Cannot detect ABC / abstract class patterns reliably
#   - Indentation-sensitive logic is fragile with regex alone

import re
from typing import Dict, Set


def parse_python(source: str) -> Dict[str, Set[str]]:
    result = {
        "classes":    set(),
        "fields":     set(),
        "methods":    set(),
        "inherits":   set(),
        "implements": set(),
        "associates": set(),
        "depends_on": set(),
    }

    # ── Strip comments ────────────────────────────────────────────────────
    source = re.sub(r'#[^\n]*', '', source)
    # Strip docstrings (triple-quoted)
    source = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
    source = re.sub(r"'''.*?'''", '', source, flags=re.DOTALL)

    lines = source.split('\n')

    # ── Class declarations ────────────────────────────────────────────────
    # Matches: class Foo:  or  class Foo(Bar):  or  class Foo(Bar, Baz):
    class_pattern = re.compile(r'^class\s+(\w+)\s*(?:\((.*?)\))?\s*:', re.MULTILINE)

    class_names = set()
    for m in class_pattern.finditer(source):
        name    = m.group(1)
        parents = m.group(2)
        result["classes"].add(name)
        class_names.add(name)

        if parents:
            for parent in re.split(r',\s*', parents):
                parent = parent.strip()
                if not parent or parent in ('object', 'ABC', 'abc.ABC'):
                    # WEAKNESS: ABC treated as implements but we skip it here
                    if parent in ('ABC', 'abc.ABC'):
                        result["implements"].add(f"{name}->ABC")
                    continue
                result["inherits"].add(f"{name}->{parent}")

    # ── Fields from __init__ only ─────────────────────────────────────────
    # WEAKNESS: misses fields set in other methods (dynamic attributes)
    # WEAKNESS: misses fields without type hints
    # WEAKNESS: confused by nested generics in annotations

    current_class  = None
    in_init        = False
    init_indent    = None
    class_indent   = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        indent = len(line) - len(line.lstrip())

        # Detect class
        cm = re.match(r'^class\s+(\w+)', stripped)
        if cm:
            current_class = cm.group(1)
            class_indent  = indent
            in_init       = False
            init_indent   = None
            continue

        # Detect __init__
        if current_class and re.match(r'^def\s+__init__\s*\(', stripped):
            in_init     = True
            init_indent = indent
            continue

        # Leave __init__ when indentation returns
        if in_init and init_indent is not None:
            if stripped and indent <= init_indent and not stripped.startswith('self'):
                in_init = False

        # Inside __init__: look for self.field = ... or self.field: Type = ...
        if in_init and current_class:
            # Annotated: self.name: str = value
            ann_m = re.match(r'self\.(\w+)\s*:\s*([\w\[\],\s]+?)\s*=', stripped)
            if ann_m:
                fname = ann_m.group(1)
                ftype = ann_m.group(2).strip()
                result["fields"].add(f"{current_class}.{fname}")

                # Association heuristic
                base_type = re.sub(r'\[.*\]', '', ftype).strip()
                if base_type in class_names and base_type != current_class:
                    result["associates"].add(f"{current_class}->{base_type}")

                # List[T] heuristic — WEAKNESS: fails on nested generics
                list_m = re.match(r'(?:List|Set|Sequence)\[(\w+)\]', ftype)
                if list_m:
                    inner = list_m.group(1)
                    if inner in class_names and inner != current_class:
                        result["associates"].add(f"{current_class}->{inner}")
                continue

            # Plain: self.name = value  (no type hint)
            # WEAKNESS: we cannot infer type, so no relationship can be added
            plain_m = re.match(r'self\.(\w+)\s*=\s*(.+)', stripped)
            if plain_m:
                fname = plain_m.group(1)
                # Skip dunder-like or private
                if not fname.startswith('__'):
                    result["fields"].add(f"{current_class}.{fname}")
                continue

    # ── Methods ───────────────────────────────────────────────────────────
    # WEAKNESS: misses async def, decorated methods with complex decorators
    # WEAKNESS: no class context tracking = cannot assign method to class
    # We use indentation heuristic — methods inside a class are indented

    current_class = None
    class_indent  = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip())

        cm = re.match(r'^class\s+(\w+)', stripped)
        if cm:
            current_class = cm.group(1)
            class_indent  = indent
            continue

        # If we dedent back to class level or less, leave class context
        if current_class and class_indent is not None:
            if indent <= class_indent and not stripped.startswith('def') and not stripped.startswith('@'):
                if re.match(r'^class\s+', stripped) or indent <= class_indent:
                    if not stripped.startswith('def'):
                        current_class = None
                        class_indent  = None

        if not current_class:
            continue

        # Method declaration
        mm = re.match(r'^def\s+(\w+)\s*\((.*?)\)', stripped)
        if mm:
            mname  = mm.group(1)
            params = mm.group(2)

            # Skip constructors and dunder methods
            if mname == '__init__':
                continue
            if mname.startswith('__') and mname.endswith('__'):
                continue

            result["methods"].add(f"{current_class}.{mname}")

            # DEPENDS_ON from typed parameters
            # WEAKNESS: only works for params on a single line
            for param in re.split(r',\s*', params):
                param = param.strip()
                if param in ('self', 'cls', ''):
                    continue
                # name: Type pattern
                type_m = re.match(r'\w+\s*:\s*([\w]+)', param)
                if type_m:
                    ptype = type_m.group(1).strip()
                    if ptype in class_names and ptype != current_class:
                        result["depends_on"].add(f"{current_class}->{ptype}")

    return result