# # uml-gen-regex/main.py
# from fastapi import FastAPI # type: ignore
# from pydantic import BaseModel # type: ignore
# from typing import Any, Dict

# from uml_rules import generate_plantuml_from_cir

# app = FastAPI(title="UML Regex Generator (CIR -> PlantUML)")


# class UMLRegexRequest(BaseModel):
#     cir: Dict[str, Any]  # expects { "nodes": [...], "edges": [...] }


# class UMLRegexResponse(BaseModel):
#     plantuml: str


# @app.post("/uml/regex", response_model=UMLRegexResponse)
# def uml_regex(req: UMLRegexRequest):
#     plantuml = generate_plantuml_from_cir(req.cir)
#     return UMLRegexResponse(plantuml=plantuml)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict

from uml_rules import (
    generate_plantuml_from_cir,  # default class diagram
    generate_class_diagram,
    generate_package_diagram,
)

app = FastAPI(title="UML Regex Generator (CIR -> PlantUML)")


class UMLRegexRequest(BaseModel):
    cir: Dict[str, Any]
    diagram_type: str = "class"  # "class" or "package" (can extend later)


class UMLRegexResponse(BaseModel):
    plantuml: str


@app.post("/uml/regex", response_model=UMLRegexResponse)
def uml_regex(req: UMLRegexRequest):
    dt = req.diagram_type.lower().strip()

    if dt == "class":
        plantuml = generate_class_diagram(req.cir)
    elif dt == "package":
        plantuml = generate_package_diagram(req.cir)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported diagram_type: {req.diagram_type}")

    return UMLRegexResponse(plantuml=plantuml)
