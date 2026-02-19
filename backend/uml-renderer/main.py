from fastapi import FastAPI, HTTPException # type: ignore
from pydantic import BaseModel # type: ignore
from typing import Optional

from plantuml_runner import PlantUMLRenderer

# TODO: change this path to where your plantuml.jar is actually stored
PLANTUML_JAR_PATH = r"D:\SLIIT\Year 4\RP\PROJECT\tools\plantuml.jar"

renderer = PlantUMLRenderer(PLANTUML_JAR_PATH)
app = FastAPI(title="UML Render Service (PlantUML -> SVG)")


class RenderRequest(BaseModel):
    plantuml: str


class RenderResponse(BaseModel):
    svg: str


@app.post("/render/svg", response_model=RenderResponse)
def render_svg(req: RenderRequest):
    if not req.plantuml.strip():
        raise HTTPException(status_code=400, detail="Empty PlantUML text")

    svg, err = renderer.render_svg(req.plantuml)

    if err:
        raise HTTPException(status_code=500, detail=err)

    return RenderResponse(svg=svg)
