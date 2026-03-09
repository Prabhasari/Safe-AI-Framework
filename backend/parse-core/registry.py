from adapters.java_adapter import JavaAdapter
from adapters.python_adapter import PythonAdapter
from adapters.js_adapter import JSAdapter

java_adapter   = JavaAdapter()
python_adapter = PythonAdapter()
js_adapter     = JSAdapter()

_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

def try_parse_best(code: str, filename: str | None):
    """
    Attempt to parse code with the most appropriate adapter.
    Returns a CIR dict or an error dict.
    """
    if filename:
        if filename.endswith(".java"):
            graph = java_adapter.build_cir_graph_for_code(code, filename=filename)
            return graph.to_debug_json()
        if filename.endswith(".py"):
            graph = python_adapter.build_cir_graph_for_code(code, filename=filename)
            return graph.to_debug_json()
        for ext in _JS_EXTS:
            if filename.endswith(ext):
                graph = js_adapter.build_cir_graph_for_code(code, filename=filename)
                return graph.to_debug_json()

    return {"error": "Unsupported file type. Supported: .java, .py, .js, .jsx, .ts, .tsx"}