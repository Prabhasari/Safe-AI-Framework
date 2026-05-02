from adapters.java_adapter import JavaAdapter
from adapters.python_adapter import PythonAdapter

java_adapter = JavaAdapter()
python_adapter = PythonAdapter()

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

    return {"error": "Unsupported file type. Supported: .java, .py"}