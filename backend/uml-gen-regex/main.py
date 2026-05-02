from fastapi import FastAPI, HTTPException  # type: ignore
from pydantic import BaseModel  # type: ignore
from typing import Any, Dict
from uml_validate import validate_plantuml

from uml_rules import (
    generate_plantuml_from_cir,  # default class diagram
    generate_class_diagram,
    generate_package_diagram,
    generate_sequence_diagram,
    generate_component_diagram,
    generate_activity_diagram,
)

app = FastAPI(title="UML Regex Generator (CIR -> PlantUML)")


class UMLRegexRequest(BaseModel):
    cir: Dict[str, Any]
    diagram_type: str = "class"  # "class", "package", "sequence", "component", "activity"


class UMLRegexResponse(BaseModel):
    ok: bool = True
    plantuml: str = ""
    validation_errors: list[str] = []


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/uml/regex", response_model=UMLRegexResponse)
def uml_regex(req: UMLRegexRequest):
    dt = req.diagram_type.lower().strip()

    if dt == "class":
        plantuml = generate_class_diagram(req.cir)
    elif dt == "package":
        plantuml = generate_package_diagram(req.cir)
    elif dt == "sequence":
        plantuml = generate_sequence_diagram(req.cir)
    elif dt == "component":
        plantuml = generate_component_diagram(req.cir)
    elif dt == "activity":
        plantuml = generate_activity_diagram(req.cir)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported diagram_type: {req.diagram_type}. "
                   f"Supported: class, package, sequence, component, activity",
        )

    ok, errs = validate_plantuml(plantuml)
    if not ok:
        return UMLRegexResponse(ok=False, plantuml=plantuml, validation_errors=errs)

    return UMLRegexResponse(ok=True, plantuml=plantuml, validation_errors=[])


# Optional: run locally
if __name__ == "__main__":
    import uvicorn # type: ignore

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=7080,
        reload=True,
    )
