# baseline_regex_java.py
# Direct regex parser for Java source code — NO AST, NO CIR.
# This is the naive approach: apply regex patterns directly to raw source text.
# Used as a BASELINE to compare against the CIR-based pipeline.
#
# Known limitations (by design — these are what we want to demonstrate):
#   - Struggles with multi-line field/method declarations
#   - Confused by nested generics like Map<String, List<T>>
#   - Misses relationships inferred from field types (needs type resolution)
#   - Cannot handle anonymous classes or lambda bodies
#   - Whitespace irregularities in AI-generated code cause misses

import re
from typing import Dict, Set


def parse_java(source: str) -> Dict[str, Set[str]]:
    result = {
        "classes":    set(),
        "fields":     set(),
        "methods":    set(),
        "inherits":   set(),
        "implements": set(),
        "associates": set(),
        "depends_on": set(),
    }

    # ── Strip single-line and block comments ──────────────────────────────
    source = re.sub(r'//[^\n]*', '', source)
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)

    # ── Class / interface / abstract class declarations ───────────────────
    # Matches: public class Foo extends Bar implements Baz {
    class_pattern = re.compile(
        r'(?:public\s+|private\s+|protected\s+)?'
        r'(?:abstract\s+)?'
        r'(class|interface|enum)\s+'
        r'(\w+)'
        r'(?:\s+extends\s+(\w+))?'
        r'(?:\s+implements\s+([\w\s,]+?))?'
        r'\s*\{',
        re.MULTILINE
    )

    class_names = {}  # name -> kind

    for m in class_pattern.finditer(source):
        kind       = m.group(1)
        name       = m.group(2)
        extends    = m.group(3)
        implements = m.group(4)

        result["classes"].add(name)
        class_names[name] = kind

        if extends:
            result["inherits"].add(f"{name}->{extends.strip()}")

        if implements:
            for iface in re.split(r',\s*', implements.strip()):
                iface = iface.strip()
                if iface:
                    result["implements"].add(f"{name}->{iface}")

    # ── Field declarations ────────────────────────────────────────────────
    # Matches: private String name;  or  private List<Course> courses;
    # WEAKNESS: multi-line declarations and complex generics confuse this
    field_pattern = re.compile(
        r'(?:private|public|protected)\s+'
        r'(?:static\s+)?(?:final\s+)?'
        r'([\w<>\[\],\s]+?)\s+'   # type — greedy, confused by nested <>
        r'(\w+)\s*;',
        re.MULTILINE
    )

    # We need to know which class each field belongs to — simple heuristic:
    # assign to the most recently seen class declaration
    lines = source.split('\n')
    current_class = None
    brace_depth   = 0

    for line in lines:
        stripped = line.strip()

        # Track class context
        cm = class_pattern.search(line)
        if cm:
            current_class = cm.group(2)
            brace_depth   = 0

        brace_depth += stripped.count('{') - stripped.count('}')
        if brace_depth <= 0 and current_class:
            current_class = None

        if not current_class:
            continue

        # Field match on this line
        fm = re.match(
            r'(?:private|public|protected)\s+'
            r'(?:static\s+)?(?:final\s+)?'
            r'([\w<>\[\],\s]+?)\s+'
            r'(\w+)\s*(?:=|;)',
            stripped
        )
        if fm:
            field_type = fm.group(1).strip()
            field_name = fm.group(2).strip()
            # Skip if it looks like a method (type is void or common return type keywords)
            if field_name and not re.search(r'\(', stripped[:fm.end()]):
                result["fields"].add(f"{current_class}.{field_name}")

                # Association heuristic: if field type is a known class, add ASSOCIATES
                # WEAKNESS: can only detect types seen in this file, not imported ones
                base_type = re.sub(r'<.*>', '', field_type).strip()
                if base_type in class_names and base_type != current_class:
                    result["associates"].add(f"{current_class}->{base_type}")

                # List<T> heuristic
                list_m = re.match(r'(?:List|Set|Collection)<(\w+)>', field_type)
                if list_m:
                    inner = list_m.group(1)
                    if inner in class_names and inner != current_class:
                        result["associates"].add(f"{current_class}->{inner}")

    # ── Method declarations ───────────────────────────────────────────────
    # WEAKNESS: constructors are hard to distinguish without full parsing
    # WEAKNESS: multi-line signatures are missed entirely
    method_pattern = re.compile(
        r'(?:public|private|protected)\s+'
        r'(?:static\s+)?(?:abstract\s+)?(?:final\s+)?'
        r'(?:synchronized\s+)?'
        r'([\w<>\[\]]+)\s+'          # return type
        r'(\w+)\s*\('                # method name
        r'([^)]*)\)',                # params — WEAKNESS: fails on multi-line
        re.MULTILINE
    )

    # Reset to track class context
    current_class = None
    brace_depth   = 0

    for line in lines:
        stripped = line.strip()

        cm = class_pattern.search(line)
        if cm:
            current_class = cm.group(2)
            brace_depth   = 0

        brace_depth += stripped.count('{') - stripped.count('}')
        if brace_depth <= 0 and current_class:
            current_class = None

        if not current_class:
            continue

        mm = method_pattern.search(line)
        if mm:
            return_type = mm.group(1).strip()
            method_name = mm.group(2).strip()
            params      = mm.group(3).strip()

            # Skip constructors (return type matches class name)
            if return_type == current_class:
                continue
            # Skip main method and common noise
            if method_name in ("main", "toString", "hashCode", "equals"):
                continue

            result["methods"].add(f"{current_class}.{method_name}")

            # DEPENDS_ON heuristic: if a param type is a known class
            for param in re.split(r',\s*', params):
                param = param.strip()
                if not param:
                    continue
                type_m = re.match(r'([\w<>]+)\s+\w+', param)
                if type_m:
                    ptype = re.sub(r'<.*>', '', type_m.group(1)).strip()
                    if ptype in class_names and ptype != current_class:
                        result["depends_on"].add(f"{current_class}->{ptype}")

    return result