from adapters.java_adapter import JavaAdapter
java_adapter = JavaAdapter()

def try_parse_best(code: str, filename: str | None):
    if filename and filename.endswith(".java"):
        tree = java_adapter.parse_to_ast(code)
        return java_adapter.ast_to_cir(tree)
    else:
        return {"error": "Unsupported file type for Java parser"}
