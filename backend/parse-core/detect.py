import re
from typing import Optional, Tuple

# Common extensions mapping
_EXT = {
    ".py": "python",
    ".java": "java",
    ".ts": "typescript",
    ".js": "javascript"
}

# keyword hints for each language
# Java Language
_JAVA_HINTS = [
    r"\bclass\s+\w+",                         # class declarations
    r"\binterface\s+\w+",                     # interface declarations
    r"\bpublic\b",                            # public modifier
    r"\bprivate\b",                           # private modifier
    r"\bprotected\b",                         # protected modifier
    r"\bpackage\s+\w+",                       # package statement
    r"\bimport\s+java\.",                     # Java imports
    r"\bvoid\s+\w+\s*\(",                     # void methods
    r"System\.out\.println",                  # print statements
    r"new\s+\w+\s*\(",                        # object creation
    r"\bpublic\s+static\s+void\s+main\s*\(",  # entry point
    r"\bSystem\.err\.println",                # error print
    r"@\w+",                                  # annotations
    r"\bextends\s+\w+",                       # inheritance
    r"\bimplements\s+\w+",                    # interfaces
    r"\bthrows\s+\w+",                        # exception handling
    r"\btry\s*\{",                            # try block
    r"\bcatch\s*\(",                          # catch block
    r"\bfinally\s*\{",                        # finally block
    r"<\w+>",                                 # generics syntax
    r"List<\w+>",                             # collections
    r"Map<\w+,\s*\w+>",                       # maps
]

# Python language
_PY_HINTS = [
    r"\bdef\b",                                  # function definitions
    r"\bclass\b",                                # class definitions
    r"\bimport\b",                               # import statements
    r"\bself\b",                                 # self keyword inside classes
    r"__init__\s*\(",                            # constructor method
    r"print\s*\(",                               # print() function
    r":\s*\n",                                   # colon + newline pattern for indentation
    r"if\s+__name__\s*==\s*['\"]__main__['\"]",  # entry point check
    r"lambda\s+",                                # anonymous functions
    r"\basync\s+def\b",                          # async functions
    r"\bawait\b",                                # await keyword
    r"@\w+",                                     # decorators
    r"\btry\s*:\s*\n",                           # try/except block
    r"\bexcept\s+\w+\s*:\s*\n",                  # exception handling
    r"\bwith\s+\w+",                             # context managers
    r"\bfrom\s+\w+\s+import\b",                  # from-import syntax
    r"f['\"]",                                   # f-strings
    r"print\s*\(f['\"]",                         # f-string prints
    r"\bself\.",                                 # self usage inside class
    r"__main__",                                 # entry point
    r"\blen\s*\(",                               # built-in len()
]

# TypeScript
_TS_HINTS = [
    r"\binterface\s+\w+",   # interface declarations
    r"\bimplements\b",      # implements keyword
    r"\bexport\b",          # export statements
    r"\bimport\s+\{?\w+",   # import syntax
    r"\bclass\s+\w+",       # class declarations
    r"\bextends\s+\w+",     # inheritance
    r"\bconstructor\s*\(",  # constructors
    r"\bfunction\s+\w+",    # functions
    r"=>\s*\{",             # arrow functions
    r"console\.log",        # console logging
    r"\btype\s+\w+\s*=",    # type aliases
    r"\benum\s+\w+",        # enum declarations
    r":\s*\w+",             # typed variable/function params
    r"\bPromise<\w+>",      # promises
    r"@\w+",                # decorators
    r"\breadonly\b",        # readonly modifier
    r"\bprivate\b",         # access modifiers
    r"\bpublic\b",
    r"\bprotected\b",
    r"\bget\s+\w+",         # getter
    r"\bset\s+\w+",         # setter
    r"\bnamespace\s+\w+",   # namespace definitions
]

# Helper to measure match strength
# def _score(patterns, text, lang_name=None):
#     hits = 0
#     for p in patterns:
#         if re.search(p, text, re.M):
#             hits += 1
#     if lang_name:
#         print(f"{lang_name}: {hits} hits")
#     return min(1.0, 0.15 * hits)

def _score(patterns, text, lang_name=None):
    hits = sum(bool(re.search(p, text, re.M)) for p in patterns)
    if lang_name:
        print(f"{lang_name}: {hits} hits")

    # Scale: 6 hits --> 0.6, 10 hits --> 1.0
    if hits >= 10:
        conf = 1.0
    elif hits >= 6:
        conf = 0.6 + (hits - 6) * (0.4 / 4) 
    else:
        conf = hits * (0.6 / 6)

    return round(min(conf, 1.0), 2)


# Main detector function
def detect_language(code: str, filename: Optional[str] = None) -> Tuple[str, float, str]:
    # Check by file extension
    if filename:
        for ext, lang in _EXT.items():
            if filename.endswith(ext):
                return lang, 0.95, "extension"

    # Check by code content --> if extension missing
    py = _score(_PY_HINTS, code)
    java = _score(_JAVA_HINTS, code)
    ts = _score(_TS_HINTS, code)

    # Pick the highest confidence language
    lang, conf = max(
        (("python", py), ("java", java), ("typescript", ts)),
        key=lambda x: x[1]
    )

    # Only accept if confidence ≥ 0.6
    if conf >= 0.6:
        return lang, conf, "heuristic"

    return "unknown", 0.0, "none"