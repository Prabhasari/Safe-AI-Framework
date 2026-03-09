# backend/uml-gen-ai/llm_client.py
"""
Gemini LLM client for PlantUML generation.

All five diagram types are standardized to match the rule-based generator exactly:

CLASS     — skinparam classAttributeIconSize 0, set namespaceSeparator .,
            +/-/#/~ visibility, typed fields/methods, no constructors, flat layout
PACKAGE   — packageStyle folder, shadowing false, FontStyle Bold FontSize 12,
            full FQN package labels, class/interface inside, rels outside blocks
SEQUENCE  — sequenceArrowThickness 2, roundcorner 5, responseMessageBelowArrow,
            actor/boundary/control/database participant keywords, activate/deactivate,
            opt (boolean) / loop (list) boxes, ... dots
COMPONENT — componentStyle uml2, defaultTextAlignment center, shadowing false,
            left to right direction, [Component] brackets, () lollipop interfaces,
            <<Stereotype>> package labels, assembly connectors
ACTIVITY  — shadowing false, activityBorderColor / BackgroundColor skinparams,
            start/stop, swimlane markers OR if/repeat/fork (NEVER mixed),
            :action; nodes with ClassName.method(params) format
"""
from __future__ import annotations

import os
import re
from typing import Literal

from dotenv import load_dotenv  # type: ignore
import google.generativeai as genai  # type: ignore

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL   = (os.getenv("GEMINI_MODEL") or "").strip() or "gemini-2.5-flash"

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Put it in .env for UML AI generator.")

genai.configure(api_key=GEMINI_API_KEY)

GEN_CFG = {
    "temperature":       0.2,
    "max_output_tokens": 4096,
    "top_p":  0.9,
    "top_k":  40,
}

# =============================================================================
#  SYSTEM INSTRUCTIONS
# =============================================================================

_BASE_SYSTEM = """
You are an assistant that generates **PlantUML** diagrams from provided context.
Hard rules:
- Output MUST be valid PlantUML between @startuml and @enduml.
- Do NOT explain anything in natural language.
- Do NOT wrap the result in ``` fences.
- No external includes or URLs (!include, !includeurl, !pragma, etc.).
""".strip()

_CLASS_SYSTEM = _BASE_SYSTEM + """

DIAGRAM TYPE: CLASS

MANDATORY HEADER — these two lines must appear immediately after @startuml:
  skinparam classAttributeIconSize 0
  set namespaceSeparator .

VISIBILITY SYMBOLS — mandatory on every single member:
  +  public     -  private     #  protected     ~  package-private

Field format:      <vis><name> : <Type>
  -logger : Logger      -balance : BigDecimal      +items : List<Product>

Method format:     <vis><name>(<param>: <Type>, ...) : <ReturnType>
  +charge(amount: BigDecimal, currency: String) : boolean
  +getAllStudents() : List<Student>
  +{abstract} validate() : boolean
  +{static} getInstance() : Manager

Modifiers {abstract} or {static} go immediately after the visibility symbol.

Class block format:
  class ClassName {
    -fieldName : FieldType
    +methodName(param: Type) : ReturnType
  }
  abstract class Name { ... }
  interface Name { ... }
  enum Name { ... }

Relationships (outside class blocks):
  Child --|> Parent          (inheritance)
  Concrete ..|> Interface   (implementation)
  ClassA --> ClassB         (association)
  ClassA ..> ClassB         (dependency)

CRITICAL DO-NOT:
  1. Do NOT include constructors.
  2. Do NOT use colored icons, stereotypes, or markers on members.
  3. Do NOT wrap classes in package {} or namespace {} blocks.
  4. Do NOT use fully-qualified names (use Foo not com.example.sms.Foo).
  5. Include ALL fields and methods from the context. Do NOT omit or invent any.
""".strip()

_PACKAGE_SYSTEM = _BASE_SYSTEM + """

DIAGRAM TYPE: PACKAGE

MANDATORY HEADER — copy these lines EXACTLY after @startuml, preserving spacing:

  ' Package diagram — shows physical code organisation
  ' Folder-tab icon per package; C/I/E/A circle icons per class member

  skinparam packageStyle         folder
  skinparam classAttributeIconSize 0
  skinparam shadowing            false

  skinparam package {
    FontStyle        Bold
    FontSize         12
  }

PACKAGE BLOCKS — one block per package, full FQN label:
  package "com.example.sms.service" {
    class StudentService
    interface IStudentService
  }
  package "com.example.sms.dao" {
    class StudentDAO
    interface IStudentDAO
  }

TYPE KEYWORDS INSIDE — use ONLY the keyword + short name, NO curly braces, NO members:
  class ClassName
  interface InterfaceName
  abstract class AbstractClassName
  enum EnumName

RELATIONSHIP ARROWS — place ALL arrows AFTER all package blocks (never inside):
  StudentDAO --> DatabaseUtil
  StudentDAO ..|> IStudentDAO
  StudentService --> IStudentDAO
  StudentService ..> Student

Arrow types:
  --|>   inheritance (extends)
  ..|>   implementation (implements)
  -->    association (strong dependency)
  ..>    dependency (weak/uses)

CRITICAL DO-NOT:
  1. Do NOT add curly braces { } after type names inside packages.
  2. Do NOT add member bodies (fields, methods) inside packages.
  3. Do NOT use [BracketName] component syntax — ONLY class/interface/enum keywords.
  4. Do NOT put arrows inside package blocks.
  5. Do NOT use short package names — always use full FQN (com.example.app.service).
  6. Do NOT add colors or stereotypes.
  7. Include EVERY type from the context in its correct package.
  8. Do NOT nest package blocks inside other package blocks. EVERY package must be
     at the TOP LEVEL — never write  package "com" { package "example" { ... } }
     WRONG:  package "com" { package "example" { class Foo } }
     RIGHT:  package "com.example" { class Foo }
""".strip()

_SEQUENCE_SYSTEM = _BASE_SYSTEM + """

DIAGRAM TYPE: SEQUENCE

MANDATORY HEADER — copy exactly after @startuml:

  skinparam sequenceArrowThickness 2
  skinparam roundcorner 5
  skinparam maxmessagesize 250
  skinparam responseMessageBelowArrow true
  skinparam shadowing false

PARTICIPANT SHAPE KEYWORDS:
  actor        — entry point / main app (nobody calls it)
  boundary     — controllers / REST endpoints / handlers
  control      — services / managers / facades / business logic
  database     — DAOs / repositories / DB utilities
  participant  — utilities / helpers / config / anything else

Declaration:   actor "AppName" as AppName
               control "ServiceName" as ServiceName
               database "DAOName" as DAOName

CALL PATTERN — always activate/deactivate the callee:
  Caller -> Callee : methodName(param: Type)
  activate Callee
  Callee --> Caller : ReturnType
  deactivate Callee

Boolean return — wrap in opt:
  opt if successful
    Caller -> Callee : methodName()
    activate Callee
    Callee --> Caller : boolean
    deactivate Callee
  end

List/collection return — wrap in loop:
  loop for each item
    Caller -> Callee : getAllItems()
    activate Callee
    Callee --> Caller : List
    deactivate Callee
  end

Use ... on its own line between call groups for spacing.
Call order: entry-point -> controller -> service -> DAO -> DB.

CRITICAL:
  - Every activate MUST have its matching deactivate. NEVER leave one open.
  - Do NOT include model/entity/DTO types as participants.
""".strip()

_COMPONENT_SYSTEM = _BASE_SYSTEM + """

DIAGRAM TYPE: COMPONENT

MANDATORY HEADER — copy these lines EXACTLY after @startuml, preserving spacing:

  ' Component diagram — shows architectural components and their interfaces
  ' Notched-rectangle icon = component   Circle (lollipop) = provided interface

  skinparam componentStyle      uml2
  skinparam defaultTextAlignment center
  skinparam shadowing           false
  left to right direction

  skinparam package {
    FontStyle        Bold
  }

STRUCTURE — root FQN package wrapping short-name sub-packages:

  package "com.example.sms" {
    [MainApp] as t_Main

    package "controller" <<Controller>> {
      [StudentController] as t_Ctrl
      () "StudentController" as I_t_Ctrl
      t_Ctrl - I_t_Ctrl
    }

    package "service" <<Service>> {
      [StudentService] as t_Svc
      () "StudentService" as I_t_Svc
      t_Svc - I_t_Svc
    }

    package "dao" <<Repository>> {
      [StudentDAO] as t_DAO
      () "StudentDAO" as I_t_DAO
      t_DAO - I_t_DAO
    }

    package "database" <<Database>> {
      [DatabaseUtil] as t_DB
      () "DatabaseUtil" as I_t_DB
      t_DB - I_t_DB
    }

    package "model" <<Model>> {
      [Student] as t_Student
      () "Student" as I_t_Student
      t_Student - I_t_Student
    }
  }

COMPONENT SYNTAX — THREE lines per component that is depended on:
  [ClassName] as alias          ← 1. notched-rectangle component
  () "ClassName" as I_alias     ← 2. lollipop interface  (ONLY if this component is called by another)
  alias - I_alias               ← 3. assembly connector  (MANDATORY with every lollipop, NO exceptions)

WITHOUT line 3 the diagram renders broken (giant circle, no connector).
Every () lollipop line MUST be immediately followed by its alias - I_alias line.

STEREOTYPE labels for sub-packages (pick best match):
  <<Controller>>   controllers / REST endpoints / handlers
  <<Service>>      services / managers / facades
  <<Repository>>   DAOs / repositories / stores
  <<Database>>     database utilities / connection pools
  <<Model>>        entity / model / domain / DTO classes
  <<Utility>>      utility / helper classes
  <<Config>>       configuration classes
  <<Security>>     security / auth classes

DEPENDENCY ARROWS — after the root package block, target the lollipop alias:
  t_Main  --> I_t_Ctrl    : uses
  t_Ctrl  --> I_t_Svc     : uses
  t_Svc   --> I_t_DAO     : delegates
  t_DAO   --> I_t_DB      : queries
  t_Ctrl  --> I_t_Student : maps
  t_Svc   --> I_t_Student : maps

Arrow labels: uses / delegates / queries / maps / implements

CRITICAL DO-NOT:
  1. Root package label = full FQN (com.example.sms).
  2. Sub-package labels = short last segment only (controller, service, dao).
  3. Every component that is targeted by an arrow MUST have a lollipop.
  4. Arrows MUST target I_alias (lollipop), NOT the component alias directly.
  5. Every lollipop MUST have an assembly connector:  alias - I_alias
  6. Do NOT add class body members (fields, methods) inside components.
  7. Do NOT add colors.
  8. Do NOT use ..|> or --|> inside a component diagram — use --> arrows with labels only.
""".strip()

_ACTIVITY_SYSTEM = _BASE_SYSTEM + """

DIAGRAM TYPE: ACTIVITY

MANDATORY HEADER — copy these lines EXACTLY after @startuml:

  skinparam shadowing               false
  skinparam activityBorderColor     #000000
  skinparam activityBackgroundColor #ffffff
  skinparam activityFontColor       #000000
  skinparam activityFontSize        13
  skinparam arrowColor              #000000
  skinparam ActivityDiamondBorderColor #000000
  skinparam ActivityDiamondBackgroundColor #ffffff
  skinparam ActivityDiamondFontColor #000000

YOU MUST CHOOSE EXACTLY ONE MODE — never mix them:

══════════════════════════════════════════════════════
MODE A — FLAT SWIMLANES (use when flow is purely sequential, NO decisions/loops)
══════════════════════════════════════════════════════
  |Controller|
  :action1;
  |Service|
  :action2;
  |Repository|
  :action3;

Rules for MODE A:
  - ONLY plain :action; nodes allowed — NO if/repeat/fork anywhere
  - Lane switches happen between actions, NEVER inside any block
  - Use this mode when the call chain has no branches or loops

══════════════════════════════════════════════════════
MODE B — STRUCTURED FLOW (use when flow has decisions, loops, or parallel steps)
══════════════════════════════════════════════════════
  start

  :ClassName.methodName(params);

  if (condition?) then (yes)
    :handle success;
  else (no)
    :handle error;
  endif

  repeat
    :process item;
  repeat while (more items?) is (yes) -> no;

  stop

Rules for MODE B:
  - NO swimlane markers (|Lane|) anywhere — not even outside blocks
  - Prefix ALL action labels with ClassName: :ServiceName.method(params);
  - Use if/endif for boolean/guard/Optional returns
  - Use repeat/repeat while for List/Collection returns
  - start and stop are REQUIRED

ABSOLUTE FORBIDDEN PATTERN (causes PlantUML crash):
  |ServiceA|              ← swimlane marker
  if (valid?) then (yes)  ← structured block
    |ServiceB|            ← CRASH: lane switch inside block
  endif

GUARD LABEL CONVENTIONS:
  validateInput()    → if (input valid?) then (yes)
  existsByUsername() → if (username exists?) then (yes)
  findById()         → if (record found?) then (yes)
  checkPassword()    → if (password correct?) then (yes)
  isActive()         → if (active?) then (yes)
  Optional<T> return → if (entity found?) then (yes)

ACTION LABEL RULES:
  - Format: :ClassName.methodName(param: Type);
  - NEVER use < > or | inside labels — replace with ( ) and /
  - Keep labels concise

ORDERING:
  Follow the provided call chain from top to bottom.
  Guards/validations come BEFORE the main action they protect.

CRITICAL DO-NOT:
  1. NEVER mix |Lane| markers with if/repeat/fork in the same diagram.
  2. Do NOT include field declarations or class structure.
  3. start and stop MUST be present.
  4. Every if must have endif. Every repeat must have repeat while.
  5. Do NOT produce an empty or trivial diagram.
  6. Do NOT use < > or | inside :action; labels.
""".strip()


def _system_for(diagram_type: str) -> str:
    dt = (diagram_type or "class").lower().strip()
    return {
        "package":   _PACKAGE_SYSTEM,
        "sequence":  _SEQUENCE_SYSTEM,
        "component": _COMPONENT_SYSTEM,
        "activity":  _ACTIVITY_SYSTEM,
    }.get(dt, _CLASS_SYSTEM)


# =============================================================================
#  REMINDER BLOCKS (injected into user prompt)
# =============================================================================

_CLASS_REMINDER = """
[CLASS DIAGRAM REMINDER]
Output MUST begin:
  @startuml
  skinparam classAttributeIconSize 0
  set namespaceSeparator .

- Every member needs a visibility symbol (+/-/#/~).
- NO constructors. NO package/namespace blocks. SHORT names only.
- Include ALL fields and methods from the FIELDS/METHODS sections.
""".strip()

_PACKAGE_REMINDER = """
[PACKAGE DIAGRAM REMINDER]
Output MUST begin with these lines exactly:

  @startuml

  ' Package diagram — shows physical code organisation
  ' Folder-tab icon per package; C/I/E/A circle icons per class member

  skinparam packageStyle         folder
  skinparam classAttributeIconSize 0
  skinparam shadowing            false

  skinparam package {
    FontStyle        Bold
    FontSize         12
  }

RULES (violations = wrong diagram):
- Full FQN for every package label:  package "com.example.app.service" { ... }
- Inside packages: ONLY keyword + name, no braces, no members:
    class ClassName
    interface InterfaceName
- NOT this:  class ClassName { }   (no body allowed)
- NOT this:  [ClassName]           (no bracket syntax — that is component style)
- ALL arrows go AFTER all package blocks, never inside.
- Arrow types:  --|>  ..|>  -->  ..>
- NEVER nest package blocks — ALL packages must be flat at the top level:
    WRONG:  package "com" { package "example" { class Foo } }
    RIGHT:  package "com.example" { class Foo }  ..>
""".strip()

_SEQUENCE_REMINDER = """
[SEQUENCE DIAGRAM REMINDER]
Output MUST begin:
  @startuml
  
  skinparam sequenceArrowThickness 2
  skinparam roundcorner 5
  skinparam maxmessagesize 250
  skinparam responseMessageBelowArrow true
  skinparam shadowing false

- Use actor/boundary/control/database/participant keywords.
- Every -> needs: activate Callee after it, deactivate Callee after the return -->.
- Boolean returns -> opt box. List returns -> loop box.
- ... between groups. NEVER leave an activate without deactivate.
""".strip()

_COMPONENT_REMINDER = """
[COMPONENT DIAGRAM REMINDER]
Output MUST begin with these lines exactly:

  @startuml

  ' Component diagram — shows architectural components and their interfaces
  ' Notched-rectangle icon = component   Circle (lollipop) = provided interface

  skinparam componentStyle      uml2
  skinparam defaultTextAlignment center
  skinparam shadowing           false
  left to right direction

  skinparam package {
    FontStyle        Bold
  }

RULES (violations = wrong diagram):
- Root package = full FQN:  package "com.example.sms" { ... }
- Sub-packages = short name + stereotype:  package "service" <<Service>> { ... }
- Every class → [ClassName] as alias
- Every depended-on component → three consecutive lines:
    () "ClassName" as I_alias
    alias - I_alias            ← MANDATORY — omitting this causes broken rendering
- Arrows target lollipop alias, NOT component alias:  t_Ctrl --> I_t_Svc : uses
- All arrows go AFTER the closing } of the root package.
- NO ..|> or --|> arrows — only --> with a label.
""".strip()

_ACTIVITY_REMINDER = """
[ACTIVITY DIAGRAM REMINDER]
Output MUST begin:
  @startuml

  skinparam shadowing               false
  skinparam activityBorderColor     #000000
  skinparam activityBackgroundColor #ffffff
  skinparam activityFontColor       #000000
  skinparam activityFontSize        13
  skinparam arrowColor              #000000
  skinparam ActivityDiamondBorderColor #000000
  skinparam ActivityDiamondBackgroundColor #ffffff
  skinparam ActivityDiamondFontColor #000000

CHOOSE ONE MODE — NEVER MIX:

MODE A (flat swimlanes, no if/repeat/fork):
  |Lane|
  :action;
  |OtherLane|
  :other action;

MODE B (structured flow, no swimlanes):
  start
  :ClassName.method(params);
  if (condition?) then (yes)
    :success action;
  else (no)
    :error action;
  endif
  stop

ABSOLUTE RULE — NEVER mix swimlane markers with structured blocks:
  WRONG:  |ServiceA|
          if (valid?) then (yes)
            |ServiceB|         ← lane switch INSIDE if = CRASH
          endif
  CORRECT option A: flat swimlanes with ONLY plain :action; nodes.
  CORRECT option B: no swimlanes + structured blocks, prefix with ClassName.

- start and stop are REQUIRED.
- Action labels must NOT contain < > or | — use ( ) and /.
- Use 'ClassName.method(params)' format in :action; labels.
- [GUARD] calls → if (...) then (yes) ... else (no) ... endif
- [LOOP] calls  → repeat ... repeat while (more items?) is (yes) -> no;
- Follow the ORDERED CALL CHAIN from the context exactly.
""".strip()

_REMINDERS = {
    "class":     _CLASS_REMINDER,
    "package":   _PACKAGE_REMINDER,
    "sequence":  _SEQUENCE_REMINDER,
    "component": _COMPONENT_REMINDER,
    "activity":  _ACTIVITY_REMINDER,
}


def _build_prompt(context: str, diagram_type: str) -> str:
    dt = (diagram_type or "class").lower().strip()
    if dt not in _REMINDERS:
        dt = "class"
    return f"""[TASK]
Generate a {dt} UML diagram in valid PlantUML from the context below.

{_REMINDERS[dt]}

[CONTEXT]
\"\"\"
{context}
\"\"\"

[OUTPUT]
Return ONLY valid PlantUML text (nothing else):

@startuml
...
@enduml""".strip()


# =============================================================================
#  POST-PROCESSORS — enforce mandatory headers deterministically
# =============================================================================

def _inject_after_startuml(plantuml: str, lines_to_inject: list) -> str:
    result = []
    injected = False
    for line in plantuml.splitlines():
        result.append(line)
        if not injected and line.strip().lower().startswith("@startuml"):
            for inject_line in lines_to_inject:
                if inject_line not in plantuml:
                    result.append(inject_line)
            injected = True
    return "\n".join(result)


def _flatten_package_diagram(plantuml: str, known_fqns: list = None) -> str:
    if not re.search(
        r'package\s+"[^"]+"\s*\{[^}]*package\s+"[^"]+"\s*\{',
        plantuml, re.DOTALL
    ):
        return plantuml

    start_m = re.search(r'@startuml\b', plantuml, re.IGNORECASE)
    end_m   = re.search(r'@enduml\b',   plantuml, re.IGNORECASE)
    if not start_m or not end_m:
        return plantuml

    header_end = start_m.end()
    body       = plantuml[header_end:end_m.start()]

    header_lines  = []
    content_lines = []
    in_skinparam  = False
    sp_depth      = 0

    for line in body.splitlines():
        s = line.strip()
        if in_skinparam:
            header_lines.append(line)
            sp_depth += s.count("{") - s.count("}")
            if sp_depth <= 0:
                in_skinparam = False
            continue
        if s.startswith("skinparam") and "{" in s:
            in_skinparam = True
            sp_depth = s.count("{") - s.count("}")
            header_lines.append(line)
            continue
        if s.startswith("skinparam") or s.startswith("'") or s.startswith("!"):
            header_lines.append(line)
            continue
        content_lines.append(line)

    content = "\n".join(content_lines)

    pkg_types:  dict = {}
    arrow_lines = []

    def _parse(text: str, prefix: str) -> None:
        lines = text.splitlines()
        n = len(lines)
        i = 0
        while i < n:
            raw = lines[i]
            s   = raw.strip()

            pm = re.match(
                r'^package\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+?))\s*(?:<<[^>]*>>)?\s*\{',
                s
            )
            if pm:
                pkg_name = (pm.group(1) or pm.group(2) or pm.group(3) or "").strip()
                new_pfx  = f"{prefix}.{pkg_name}" if prefix else pkg_name
                open_ct  = s.count("{")
                close_ct = s.count("}")
                if open_ct == close_ct and open_ct > 0:
                    inner_m = re.search(r'\{(.*)\}', s)
                    if inner_m:
                        _parse(inner_m.group(1).strip(), new_pfx)
                    i += 1
                    continue
                depth = open_ct - close_ct
                j = i + 1
                block = []
                while j < n and depth > 0:
                    bl = lines[j]
                    bls = bl.strip()
                    depth += bls.count("{") - bls.count("}")
                    if depth > 0:
                        block.append(bl)
                    j += 1
                _parse("\n".join(block), new_pfx)
                i = j
                continue

            tm = re.match(r'^((?:abstract\s+)?(?:class|interface|enum))\s+(\w+)\s*$', s)
            if tm:
                key = prefix or "(default)"
                pkg_types.setdefault(key, []).append(f"{tm.group(1)} {tm.group(2)}")
                i += 1
                continue

            tbm = re.match(r'^((?:abstract\s+)?(?:class|interface|enum))\s+(\w+)\s*\{', s)
            if tbm:
                key = prefix or "(default)"
                pkg_types.setdefault(key, []).append(f"{tbm.group(1)} {tbm.group(2)}")
                depth = s.count("{") - s.count("}")
                i += 1
                while i < n and depth > 0:
                    depth += lines[i].strip().count("{") - lines[i].strip().count("}")
                    i += 1
                continue

            if s and not s.startswith("'"):
                if re.search(r'(-{2,}|\.{2,})[|><!]|[|><!](-{2,}|\.{2,})', s):
                    arrow_lines.append(s)
            i += 1

    _parse(content, "")

    fqn_remap: dict = {}
    if known_fqns:
        for fqn in known_fqns:
            parts = fqn.split(".")
            for length in range(1, len(parts) + 1):
                suffix = ".".join(parts[-length:])
                if suffix not in fqn_remap or len(fqn) > len(fqn_remap[suffix]):
                    fqn_remap[suffix] = fqn

    def _remap(pkg: str) -> str:
        return fqn_remap.get(pkg, pkg)

    out = [plantuml[:header_end].rstrip(), ""]
    prev_blank = True
    for hl in header_lines:
        if hl.strip() == "":
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(hl)
            prev_blank = False
    out.append("")

    for fqn in sorted(pkg_types.keys()):
        canonical = _remap(fqn)
        out.append(f'package "{canonical}" {{')
        for tl in sorted(set(pkg_types[fqn])):
            out.append(f"  {tl}")
        out.append("}")
        out.append("")

    if arrow_lines:
        for al in sorted(set(arrow_lines)):
            out.append(al)
        out.append("")

    out.append("@enduml")
    return "\n".join(out)


def _fix_component_assembly_connectors(plantuml: str) -> str:
    comp_aliases: dict = {}
    for line in plantuml.splitlines():
        m = re.search(r'\[([^\]]+)\]\s+as\s+(\w+)', line)
        if m:
            comp_aliases[m.group(1)] = m.group(2)

    result = []
    for line in plantuml.splitlines():
        result.append(line)
        m = re.search(r'\(\)\s+"([^"]+)"\s+as\s+(\w+)', line)
        if m:
            name   = m.group(1)
            ialias = m.group(2)
            comp_alias = comp_aliases.get(name)
            if comp_alias:
                connector = f"{comp_alias} - {ialias}"
                if connector not in plantuml:
                    indent = len(line) - len(line.lstrip())
                    result.append(" " * indent + connector)

    return "\n".join(result)


# =============================================================================
#  ACTIVITY DIAGRAM FIX  (complete rewrite — robust against all Gemini mistakes)
# =============================================================================

def _fix_activity_diagram(plantuml: str) -> str:
    """
    Post-process activity diagrams to guarantee PlantUML renderer compatibility.

    Fixes applied (in order):
    ──────────────────────────
    0.  Deduplicate @startuml — Gemini sometimes emits @startuml twice (confirmed
        in production logs: "@startuml\\n@startuml\\n...").  Keep only the first.

    1.  Strip hallucinated lane/partition syntax that Gemini invents but PlantUML
        does not support:
          • lane "Name" as Alias      ← not valid PlantUML
          • partition "Name" { ... }  ← crashes renderer
          • ClassName: action;        ← colon-prefix notation (also invalid)
        All of these are silently removed (lane/partition declarations dropped,
        colon-prefix lines converted to proper :action; nodes).

    2.  Detect whether the diagram uses structured blocks (if/repeat/fork).
    2a. If YES  → remove ALL |Lane| swimlane markers unconditionally (MODE B).
        PlantUML crashes whenever any |Lane| marker appears inside or adjacent
        to if/repeat/fork regardless of nesting depth.
    2b. If NO   → keep |Lane| swimlane markers (MODE A — flat lanes only).

    3.  Escape forbidden characters inside :action; labels (< > | -> <-).

    4.  Balance unclosed if/endif, repeat/repeat-while, fork/end-fork blocks.

    5.  Ensure start and stop are present.

    6.  Size guard — clamp body to 250 lines to avoid renderer OOM.
    """

    # ── -1. Repair truncated output ───────────────────────────────────────────
    # Confirmed crash: Gemini hits max_output_tokens mid-line, e.g.:
    #   ":UserDAO.\n@enduml" -- incomplete :action node with no closing semicolon.
    # Fix: drop any truncated trailing :action line so the renderer never sees it.
    plantuml = plantuml.rstrip()
    if not plantuml.lower().endswith("@enduml"):
        plantuml = plantuml + "\nstop\n@enduml"

    _pre = plantuml.splitlines()
    _repaired: list[str] = []
    for _i, _ln in enumerate(_pre):
        _is_trunc = (
            re.match(r'^\s*:[^;]*$', _ln)
            and not re.match(r'^\s*:[^;]+;\s*$', _ln)
        )
        if _is_trunc:
            _rest = [_l.strip().lower() for _l in _pre[_i + 1:] if _l.strip()]
            if all(_r in ("stop", "@enduml") for _r in _rest):
                continue
        _repaired.append(_ln)
    plantuml = "\n".join(_repaired)

    lines = plantuml.splitlines()

    # ── 0. Deduplicate @startuml ──────────────────────────────────────────────
    # Confirmed crash pattern from logs: "@startuml\n@startuml\n..."
    # Keep only the FIRST @startuml line; remove any subsequent ones.
    seen_startuml = False
    deduped: list[str] = []
    for ln in lines:
        if re.match(r'^\s*@startuml\b', ln, re.IGNORECASE):
            if not seen_startuml:
                seen_startuml = True
                deduped.append(ln)
            # else: silently drop the duplicate
        else:
            deduped.append(ln)
    lines = deduped

    # ── 1. Strip/convert hallucinated syntax ─────────────────────────────────
    #
    # Pattern A — `lane "Name" as Alias` or `lane Name`
    #   Gemini invents this; PlantUML has no `lane` keyword.  Drop the line.
    #
    # Pattern B — `partition "Name" {` ... `}`
    #   partition blocks are only valid in some PlantUML versions and crash
    #   others.  Convert the opening/closing lines to swimlane markers so the
    #   diagram stays readable, OR drop them if structured blocks are present
    #   (handled in step 2 below after detection).
    #
    # Pattern C — `ClassName: action text;` or `ClassName: action text`
    #   Gemini sometimes emits  `Repository: UserDAO.save(user);`
    #   This is NOT valid PlantUML activity syntax.  Convert to `:action;`.
    #
    # Pattern D — `ClassName` on a line by itself (bare type name as a node)
    #   e.g. `Repository` alone on a line.  Drop it — PlantUML misparses it.

    cleaned: list[str] = []
    for ln in lines:
        stripped = ln.strip()

        # Pattern A: lane declaration
        if re.match(r'^\s*lane\s+', ln, re.IGNORECASE):
            # Convert to a swimlane marker so we don't lose the label entirely
            m = re.search(r'lane\s+"([^"]+)"', ln, re.IGNORECASE) or \
                re.search(r'lane\s+(\w+)',      ln, re.IGNORECASE)
            if m:
                cleaned.append(f"|{m.group(1)}|")
            # else drop silently
            continue

        # Pattern B: partition opening — keep as swimlane marker
        m_part = re.match(r'^\s*partition\s+"([^"]+)"\s*\{?', ln, re.IGNORECASE) or \
                 re.match(r'^\s*partition\s+(\w+)\s*\{?',     ln, re.IGNORECASE)
        if m_part:
            cleaned.append(f"|{m_part.group(1)}|")
            continue

        # Pattern B: partition closing brace on its own line — drop
        if re.match(r'^\s*\}\s*$', ln) and any(
            re.match(r'^\s*partition\b', l, re.IGNORECASE) for l in cleaned
        ):
            continue

        # Pattern C: "ClassName: action text;" — convert to :action;
        m_colon = re.match(r'^\s*(\w+)\s*:\s*([^;{}\n]+?)\s*;?\s*$', ln)
        if m_colon:
            keyword = m_colon.group(1).lower()
            # Make sure this isn't a PlantUML keyword that legitimately uses colon
            _PLANTUML_KW = {
                "if", "else", "elseif", "endif", "repeat", "while", "fork",
                "split", "start", "stop", "end", "note", "skinparam",
                "actor", "boundary", "control", "database", "participant",
                "activate", "deactivate", "return", "autonumber", "title",
                "header", "footer", "loop", "opt", "alt", "group", "ref",
            }
            if keyword not in _PLANTUML_KW and re.match(r'^[A-Z]', m_colon.group(1)):
                # It's a ClassName: action pattern — convert
                action_text = m_colon.group(2).strip()
                cleaned.append(f":{action_text};")
                continue

        # Pattern D: bare ClassName on its own line (PascalCase, no punctuation)
        if re.match(r'^\s*[A-Z][a-zA-Z0-9]+\s*$', ln):
            # Drop it — it's a stray type name, not a valid activity node
            continue

        cleaned.append(ln)

    lines = cleaned

    # ── 2. Detect structured blocks & strip swimlanes if needed ──────────────
    _STRUCTURED_RE = re.compile(
        r'^\s*(?:if\s*\(|repeat\s*$|fork\s*$|split\s*$)',
        re.IGNORECASE,
    )
    has_structured = any(_STRUCTURED_RE.match(ln) for ln in lines)

    result: list[str] = []
    for ln in lines:
        # Remove |Lane| markers when structured blocks exist
        if has_structured and re.match(r'^\s*\|[^|]+\|', ln):
            result.append(f"' [auto-removed swimlane — structured mode]: {ln.strip()}")
            continue
        result.append(ln)

    # ── 3. Escape forbidden characters inside :action; labels ────────────────
    escaped: list[str] = []
    for ln in result:
        if re.match(r'\s*:[^;]+;', ln):
            ln = re.sub(r'<(\w)', r'(\1', ln)
            ln = re.sub(r'(\w)>', r'\1)', ln)
            ln = ln.replace("|", "/")
            ln = ln.replace("->", "to")
            ln = ln.replace("<-", "from")
        escaped.append(ln)
    result = escaped

    # ── 4. Balance unclosed structural keywords ───────────────────────────────
    combined = "\n".join(result)
    if_count       = len(re.findall(r'^\s*if\s*\(',        combined, re.MULTILINE | re.IGNORECASE))
    endif_count    = len(re.findall(r'^\s*endif\b',        combined, re.MULTILINE | re.IGNORECASE))
    repeat_count   = len(re.findall(r'^\s*repeat\s*$',     combined, re.MULTILINE | re.IGNORECASE))
    repwhile_count = len(re.findall(r'^\s*repeat\s+while', combined, re.MULTILINE | re.IGNORECASE))
    fork_count     = len(re.findall(r'^\s*fork\s*$',       combined, re.MULTILINE | re.IGNORECASE))
    endfork_count  = len(re.findall(r'^\s*end\s+fork\b',   combined, re.MULTILINE | re.IGNORECASE))
    split_count    = len(re.findall(r'^\s*split\s*$',      combined, re.MULTILINE | re.IGNORECASE))
    endsplit_count = len(re.findall(r'^\s*end\s+split\b',  combined, re.MULTILINE | re.IGNORECASE))

    closers: list[str] = []
    for _ in range(max(0, if_count - endif_count)):
        closers.append("endif")
    for _ in range(max(0, repeat_count - repwhile_count)):
        closers.append("repeat while (more items?) is (yes) -> no;")
    for _ in range(max(0, fork_count - endfork_count)):
        closers.append("end fork")
    for _ in range(max(0, split_count - endsplit_count)):
        closers.append("end split")

    if closers:
        new_result: list[str] = []
        inserted = False
        for ln in reversed(result):
            if not inserted and re.match(r'^\s*(stop\b|@enduml\b)', ln, re.IGNORECASE):
                for c in closers:
                    new_result.append(c)
                inserted = True
            new_result.append(ln)
        result = list(reversed(new_result))

    # ── 5. Ensure start and stop are present (MODE B only — no swimlanes) ──────
    # CRITICAL: swimlane diagrams (MODE A) must NOT have start/stop.
    # Adding start/stop to a swimlane diagram crashes the PlantUML renderer.
    # Only inject start/stop when the diagram has NO swimlane markers at all.
    combined = "\n".join(result)
    has_swimlanes = bool(re.search(r'^\s*\|[^|]+\|', combined, re.MULTILINE))

    if not has_swimlanes:
        if not re.search(r'^\s*start\b', combined, re.MULTILINE | re.IGNORECASE):
            new_result = []
            last_skinparam_idx = -1
            for i, ln in enumerate(result):
                if ln.strip().startswith("skinparam") or (ln.strip().startswith("'") and i < 15):
                    last_skinparam_idx = i
            for i, ln in enumerate(result):
                new_result.append(ln)
                if i == last_skinparam_idx:
                    new_result.append("")
                    new_result.append("start")
                    new_result.append("")
            result = new_result

        combined = "\n".join(result)
        if not re.search(r'^\s*stop\b', combined, re.MULTILINE | re.IGNORECASE):
            new_result = []
            for ln in result:
                if re.match(r'^\s*@enduml\b', ln, re.IGNORECASE):
                    new_result.append("")
                    new_result.append("stop")
                    new_result.append("")
                new_result.append(ln)
            result = new_result
    else:
        # MODE A (swimlanes): remove any start/stop that crept in
        result = [
            ln for ln in result
            if not re.match(r'^\s*(start|stop)\b', ln, re.IGNORECASE)
        ]

    # ── 6. Size guard — clamp to 250 body lines ───────────────────────────────
    startuml_idx = -1
    enduml_idx   = len(result)
    for i, ln in enumerate(result):
        if re.match(r'^\s*@startuml\b', ln, re.IGNORECASE) and startuml_idx == -1:
            startuml_idx = i
        if re.match(r'^\s*@enduml\b', ln, re.IGNORECASE):
            enduml_idx = i

    MAX_BODY_LINES = 250
    header_lines_list = result[:startuml_idx + 1] if startuml_idx >= 0 else []
    body_lines        = result[startuml_idx + 1:enduml_idx] if startuml_idx >= 0 else result
    footer_lines      = result[enduml_idx:] if enduml_idx < len(result) else []

    if len(body_lines) > MAX_BODY_LINES:
        body_lines = body_lines[:MAX_BODY_LINES]
        if not any(re.match(r'^\s*stop\b', ln, re.IGNORECASE) for ln in body_lines):
            body_lines.append("")
            body_lines.append("stop")
        result = header_lines_list + body_lines + footer_lines

    return "\n".join(result)


def _post_process(plantuml: str, diagram_type: str, known_fqns: list = None) -> str:
    dt = (diagram_type or "class").lower().strip()

    if dt == "class":
        if "classAttributeIconSize" not in plantuml:
            plantuml = _inject_after_startuml(plantuml, ["skinparam classAttributeIconSize 0"])
        if "namespaceSeparator" not in plantuml:
            plantuml = _inject_after_startuml(plantuml, ["set namespaceSeparator ."])

    elif dt == "package":
        needed = []
        if "packageStyle" not in plantuml:
            needed.append("skinparam packageStyle         folder")
        if "classAttributeIconSize" not in plantuml:
            needed.append("skinparam classAttributeIconSize 0")
        if "shadowing" not in plantuml:
            needed.append("skinparam shadowing            false")
        if needed:
            plantuml = _inject_after_startuml(plantuml, needed)
        plantuml = _flatten_package_diagram(plantuml, known_fqns=known_fqns)

    elif dt == "sequence":
        needed = []
        if "sequenceArrowThickness" not in plantuml:
            needed.append("skinparam sequenceArrowThickness 2")
        if "roundcorner" not in plantuml:
            needed.append("skinparam roundcorner 5")
        if "responseMessageBelowArrow" not in plantuml:
            needed.append("skinparam responseMessageBelowArrow true")
        if "shadowing" not in plantuml:
            needed.append("skinparam shadowing false")
        if needed:
            plantuml = _inject_after_startuml(plantuml, needed)

    elif dt == "component":
        needed = []
        if "componentStyle" not in plantuml:
            needed.append("skinparam componentStyle      uml2")
        if "defaultTextAlignment" not in plantuml:
            needed.append("skinparam defaultTextAlignment center")
        if "shadowing" not in plantuml:
            needed.append("skinparam shadowing           false")
        if "left to right direction" not in plantuml:
            needed.append("left to right direction")
        if needed:
            plantuml = _inject_after_startuml(plantuml, needed)
        plantuml = _fix_component_assembly_connectors(plantuml)

    elif dt == "activity":
        needed = []
        if "activityBorderColor" not in plantuml:
            needed.append("skinparam activityBorderColor     #000000")
        if "activityBackgroundColor" not in plantuml:
            needed.append("skinparam activityBackgroundColor #ffffff")
        if "activityFontColor" not in plantuml:
            needed.append("skinparam activityFontColor       #000000")
        if "activityFontSize" not in plantuml:
            needed.append("skinparam activityFontSize        13")
        if "arrowColor" not in plantuml:
            needed.append("skinparam arrowColor              #000000")
        if "ActivityDiamondBorderColor" not in plantuml:
            needed.append("skinparam ActivityDiamondBorderColor #000000")
        if "ActivityDiamondBackgroundColor" not in plantuml:
            needed.append("skinparam ActivityDiamondBackgroundColor #ffffff")
        if "ActivityDiamondFontColor" not in plantuml:
            needed.append("skinparam ActivityDiamondFontColor #000000")
        if "shadowing" not in plantuml:
            needed.append("skinparam shadowing               false")
        if needed:
            plantuml = _inject_after_startuml(plantuml, needed)
        # ← FULL robust fix: removes all swimlanes if structured blocks exist,
        #   escapes labels, balances blocks, ensures start/stop, clamps size
        plantuml = _fix_activity_diagram(plantuml)

    return plantuml


# =============================================================================
#  STRIP PACKAGE BLOCKS — for class diagrams only
# =============================================================================

def _strip_package_blocks(plantuml: str) -> str:
    def _remove_wrappers(text: str) -> str:
        result = []
        i = 0
        n = len(text)
        while i < n:
            m = re.match(
                r'^([ \t]*)(package|namespace)([ \t]+(?:"[^"]*"|[^\s{]+))?[ \t]*\{',
                text[i:],
                re.IGNORECASE,
            )
            if m:
                start = i + m.end()
                depth = 1
                j = start
                while j < n and depth > 0:
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                    j += 1
                inner = text[start: j - 1]
                inner_stripped = _remove_wrappers(inner)
                dedented = re.sub(r"^  ", "", inner_stripped, flags=re.MULTILINE)
                result.append(dedented)
                i = j
                if i < n and text[i] == "\n":
                    i += 1
            else:
                end = text.find("\n", i)
                if end == -1:
                    result.append(text[i:])
                    break
                result.append(text[i: end + 1])
                i = end + 1
        return "".join(result)

    return _remove_wrappers(plantuml)


# =============================================================================
#  PlantUML EXTRACTOR
# =============================================================================

def _extract_plantuml(text: str) -> str:
    if not text:
        raise RuntimeError("Empty response from Gemini.")

    lower     = text.lower()
    start_idx = lower.find("@startuml")
    end_idx   = lower.rfind("@enduml")

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return text[start_idx: end_idx + len("@enduml")].strip()

    fence_match = re.search(
        r"```(?:plantuml|uml|puml)?\s*\n(.*?)\n```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fence_match:
        inner = fence_match.group(1).strip()
        if inner:
            return f"@startuml\n{inner}\n@enduml"

    return text.strip()


# =============================================================================
#  PUBLIC ENTRY POINT
# =============================================================================

def _extract_known_fqns(context: str) -> list:
    fqns = set()

    for m in re.finditer(
        r'package\s+"([a-zA-Z][a-zA-Z0-9._]*\.[a-zA-Z][a-zA-Z0-9._]*)"',
        context
    ):
        fqns.add(m.group(1).strip())

    for m in re.finditer(
        r'package:\s*([a-zA-Z][a-zA-Z0-9._]*\.[a-zA-Z][a-zA-Z0-9._]*)',
        context
    ):
        fqns.add(m.group(1).rstrip(")").rstrip())

    return sorted(fqns)


def generate_plantuml_from_context(
    context: str,
    diagram_type: Literal["class", "package", "sequence", "component", "activity"] = "class",
) -> str:
    if not context or not context.strip():
        raise RuntimeError("No context provided for AI UML generation.")

    dt     = (diagram_type or "class").lower().strip()
    prompt = _build_prompt(context, dt)

    known_fqns = _extract_known_fqns(context) if dt == "package" else None

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

    if "@startuml" not in plantuml.lower() or "@enduml" not in plantuml.lower():
        if parts_text.strip():
            plantuml = f"@startuml\n{parts_text.strip()}\n@enduml"
        else:
            raise RuntimeError(
                "Gemini returned an empty or unrecognisable response "
                "(no @startuml/@enduml block found)."
            )

    # Class diagrams: strip any package/namespace wrappers Gemini emits
    if dt == "class":
        plantuml = _strip_package_blocks(plantuml)

    # All diagrams: enforce mandatory skinparam headers + diagram-specific fixes
    plantuml = _post_process(plantuml, dt, known_fqns=known_fqns)

    return plantuml