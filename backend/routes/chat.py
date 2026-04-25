import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Project
from services.acoustics import run_acoustic_analysis
from services.groq_ai import process_chat_message
from services.thermal import run_thermal_analysis
from services.wifi import run_wifi_analysis

router = APIRouter(prefix="/api/projects", tags=["chat"])

SAFE_ROOM_KEYS = {
    "wall_color", "wall_material", "floor_color", "floor_material",
    "ceiling_height_m", "windows", "doors",
}


class ChatRequest(BaseModel):
    message: str
    room_id: str


@router.post("/{project_id}/chat")
async def chat(
    project_id: str,
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    rooms = json.loads(project.rooms_json) if project.rooms_json else []
    room = next((r for r in rooms if r["id"] == body.room_id), None)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    action = await process_chat_message(
        body.message, project_id, body.room_id, project.rooms_json
    )

    action_type = action.get("action_type")
    params = action.get("parameters", {})

    if action_type == "MATERIAL_CHANGE":
        prop = params.get("property")
        val = params.get("value")
        if prop in SAFE_ROOM_KEYS and val is not None:
            room[prop] = val
            project.rooms_json = json.dumps(rooms)
            await db.commit()

    elif action_type == "ANALYSIS_REQUEST":
        analysis_type = params.get("analysis_type")
        if analysis_type == "wifi":
            background_tasks.add_task(
                run_wifi_analysis,
                project_id,
                body.room_id,
                project.rooms_json,
                room["width_m"] / 2,
                room["height_m"] / 2,
                2.4,
            )
        elif analysis_type == "acoustics":
            background_tasks.add_task(
                run_acoustic_analysis,
                project_id,
                body.room_id,
                project.rooms_json,
            )
        elif analysis_type == "thermal":
            background_tasks.add_task(
                run_thermal_analysis,
                project_id,
                body.room_id,
                project.rooms_json,
                0.0,
            )

    return action
