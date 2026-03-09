from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pipeline import run_pipeline  # <-- changed (no app.)
from history_router import router as history_router 

app = FastAPI(title="Secure-by-Design Code Generator")

# CORS for local dev (Vite @ 5173, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(history_router, prefix="/api")

@app.options("/api/generate")
def options_generate():
    return Response(status_code=200)

class GenerateIn(BaseModel):
    prompt: str = Field(min_length=5, description="Describe the code to generate")

@app.post("/api/generate")
async def generate(inp: GenerateIn):
    return await run_pipeline(prompt=inp.prompt)

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/model")
def model_name():
    from stages.llm import _MODEL_NAME  # <-- changed (no app.)
    return {"model": _MODEL_NAME}
