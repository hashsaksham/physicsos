import json
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Project
from services.floor_plan import process_floor_plan
from utils.file_handler import save_upload_file

router = APIRouter(prefix="/api/projects", tags=["projects"])

SAFE_ROOM_KEYS = {"wall_color", "wall_material", "floor_color", "floor_material", "ceiling_height_m", "windows", "doors"}


@router.post("/")
async def create_project(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    name: Annotated[str, Form()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    content = await file.read()
    path = await save_upload_file(content, file.filename)

    project = Project(name=name, floor_plan_path=path, status="processing")
    db.add(project)
    await db.commit()
    await db.refresh(project)

    background_tasks.add_task(process_floor_plan, path, project.id)
    return {"project_id": project.id, "status": "processing"}


@router.get("/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    rooms = json.loads(project.rooms_json) if project.rooms_json else []
    return {
        "project_id": project.id,
        "name": project.name,
        "status": project.status,
        "rooms": rooms,
        "created_at": project.created_at.isoformat(),
    }


@router.patch("/{project_id}/rooms/{room_id}")
async def update_room(
    project_id: str,
    room_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    rooms = json.loads(project.rooms_json) if project.rooms_json else []
    room = next((r for r in rooms if r["id"] == room_id), None)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    room.update({k: v for k, v in body.items() if k in SAFE_ROOM_KEYS})

    project.rooms_json = json.dumps(rooms)
    await db.commit()
    return room
