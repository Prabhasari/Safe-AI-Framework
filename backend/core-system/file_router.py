from fastapi import APIRouter, HTTPException
import os

router = APIRouter()

# This must match your upload root folder
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Go one level up from core-system → Backend/
BACKEND_ROOT = os.path.dirname(CURRENT_DIR)

BASE_DIR = os.path.join(BACKEND_ROOT, "storage", "core_project")


def safe_path(path: str):
    if ".." in path:
        raise HTTPException(status_code=400, detail="Invalid path")
    return os.path.join(BASE_DIR, path)


@router.post("/core/create-folder")
def create_folder(data: dict):
    path = data.get("path")

    if not path:
        raise HTTPException(status_code=400, detail="Path required")

    full_path = safe_path(path)

    os.makedirs(full_path, exist_ok=True)

    return {"message": "Folder created"}


@router.post("/core/create-file")
def create_file(data: dict):
    path = data.get("path")

    if not path:
        raise HTTPException(status_code=400, detail="Path required")

    full_path = safe_path(path)

    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w") as f:
        f.write("")

    return {"message": "File created"}