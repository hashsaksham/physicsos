import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AnalysisResult, Project
from services.acoustics import run_acoustic_analysis
from services.thermal import run_thermal_analysis
from services.wifi import run_wifi_analysis

router = APIRouter(prefix="/api/projects", tags=["analysis"])
uploads_router = APIRouter(tags=["uploads"])


@uploads_router.get("/api/uploads/{filename}")
async def serve_upload(filename: str):
    path = f"uploads/{filename}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
    return FileResponse(path)


def _heatmap_url(heatmap_path: str | None) -> str | None:
    if not heatmap_path:
        return None
    return f"/api/{heatmap_path}"


class WifiRequest(BaseModel):
    room_id: str
    router_x: float
    router_y: float
    frequency_ghz: float = 2.4


@router.post("/{project_id}/analysis/wifi")
async def start_wifi_analysis(
    project_id: str,
    body: WifiRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.rooms_json:
        raise HTTPException(status_code=400, detail="Project has no rooms yet — wait for processing to complete")

    background_tasks.add_task(
        run_wifi_analysis,
        project_id,
        body.room_id,
        project.rooms_json,
        body.router_x,
        body.router_y,
        body.frequency_ghz,
    )
    return {"status": "processing", "project_id": project_id}


@router.get("/{project_id}/analysis/wifi/result")
async def get_wifi_result(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        stmt = (
            select(AnalysisResult)
            .where(AnalysisResult.project_id == project_id)
            .where(AnalysisResult.analysis_type == "wifi")
            .order_by(AnalysisResult.created_at.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="No WiFi analysis result found")
        return {"result": json.loads(row.result_json), "heatmap_url": _heatmap_url(row.heatmap_path)}
    except HTTPException:
        raise
    except Exception as exc:
        return {"result": {"error": str(exc)}, "heatmap_url": None}


class AcousticsRequest(BaseModel):
    room_id: str


@router.post("/{project_id}/analysis/acoustics")
async def start_acoustic_analysis(
    project_id: str,
    body: AcousticsRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.rooms_json:
        raise HTTPException(status_code=400, detail="Project has no rooms yet — wait for processing to complete")

    background_tasks.add_task(
        run_acoustic_analysis,
        project_id,
        body.room_id,
        project.rooms_json,
    )
    return {"status": "processing", "project_id": project_id}


@router.get("/{project_id}/analysis/acoustics/result")
async def get_acoustics_result(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        stmt = (
            select(AnalysisResult)
            .where(AnalysisResult.project_id == project_id)
            .where(AnalysisResult.analysis_type == "acoustics")
            .order_by(AnalysisResult.created_at.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="No acoustics analysis result found")
        return {"result": json.loads(row.result_json), "heatmap_url": None}
    except HTTPException:
        raise
    except Exception as exc:
        return {"result": {"error": str(exc)}, "heatmap_url": None}


class ThermalRequest(BaseModel):
    room_id: str
    outdoor_temp_celsius: float = 0.0


@router.post("/{project_id}/analysis/thermal")
async def start_thermal_analysis(
    project_id: str,
    body: ThermalRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.rooms_json:
        raise HTTPException(status_code=400, detail="Project has no rooms yet — wait for processing to complete")

    background_tasks.add_task(
        run_thermal_analysis,
        project_id,
        body.room_id,
        project.rooms_json,
        body.outdoor_temp_celsius,
    )
    return {"status": "processing", "project_id": project_id}


@router.get("/{project_id}/analysis/thermal/result")
async def get_thermal_result(project_id: str, db: AsyncSession = Depends(get_db)):
    try:
        stmt = (
            select(AnalysisResult)
            .where(AnalysisResult.project_id == project_id)
            .where(AnalysisResult.analysis_type == "thermal")
            .order_by(AnalysisResult.created_at.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="No thermal analysis result found")
        return {"result": json.loads(row.result_json), "heatmap_url": _heatmap_url(row.heatmap_path)}
    except HTTPException:
        raise
    except Exception as exc:
        return {"result": {"error": str(exc)}, "heatmap_url": None}
