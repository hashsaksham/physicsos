import json

import numpy as np
import pyroomacoustics as pra

from database import AsyncSessionLocal
from models import AnalysisResult

ABSORPTION = {
    "hardwood": {"energy_absorption": 0.07},
    "carpet":   {"energy_absorption": 0.37},
    "concrete": {"energy_absorption": 0.02},
    "tile":     {"energy_absorption": 0.02},
}


def _sabine_rt60(room_dim: list[float], alpha: float) -> float:
    V = room_dim[0] * room_dim[1] * room_dim[2]
    S = 2 * (
        room_dim[0] * room_dim[1]
        + room_dim[1] * room_dim[2]
        + room_dim[0] * room_dim[2]
    )
    return 0.161 * V / max(alpha * S, 0.001)


def _classify(rt60: float) -> str:
    if rt60 < 0.3:
        return "Excellent — studio quality"
    elif rt60 < 0.6:
        return "Good — suitable for conversation"
    elif rt60 < 1.0:
        return "Fair — some echo present"
    return "Poor — significant echo"


def _recommendations(rt60: float, floor_material: str, wall_material: str) -> list[str]:
    if rt60 <= 0.3:
        return ["Room acoustics are excellent — no changes needed"]

    recs = []
    if rt60 > 1.0:
        recs.append("Add heavy curtains or acoustic panels to walls")
        recs.append("Install carpet — estimated 40% RT60 reduction")
    elif rt60 > 0.6:
        recs.append("Add soft furnishings (rugs, sofas) to absorb reflections")
        recs.append("Consider acoustic ceiling tiles")

    if rt60 > 0.3 and floor_material == "hardwood":
        recs.append("Add a large area rug to reduce echo by ~30%")
    if rt60 > 0.3 and wall_material == "drywall":
        recs.append("Bookshelves or wall hangings will diffuse reflections")
    return recs


async def run_acoustic_analysis(project_id: str, room_id: str, rooms_json: str) -> None:
    async with AsyncSessionLocal() as session:
        try:
            rooms = json.loads(rooms_json)
            room = next((r for r in rooms if r["id"] == room_id), None)
            if room is None:
                raise ValueError(f"Room {room_id} not found")

            room_dim = [
                max(room["width_m"], 0.5),
                max(room["height_m"], 0.5),
                max(room["ceiling_height_m"], 0.5),
            ]
            floor_mat = room.get("floor_material", "hardwood")
            wall_mat = room.get("wall_material", "drywall")
            absorption = ABSORPTION.get(floor_mat, ABSORPTION["hardwood"])

            rt60: float
            try:
                material = pra.Material(absorption)
                pra_room = pra.ShoeBox(room_dim, materials=material, fs=16000, max_order=3)

                src = [room_dim[0] / 2, room_dim[1] / 2, 1.2]
                pra_room.add_source(src)

                mic_x = min(room_dim[0] / 2 + 1.5, room_dim[0] - 0.1)
                mic = np.array([[mic_x], [room_dim[1] / 2], [1.2]])
                pra_room.add_microphone(mic)

                pra_room.simulate()
                rt60_arr = pra_room.measure_rt60()
                rt60 = float(np.mean(rt60_arr))
            except Exception:
                rt60 = _sabine_rt60(room_dim, absorption["energy_absorption"])

            rt60 = max(rt60, 0.01)
            quality = _classify(rt60)
            recommendations = _recommendations(rt60, floor_mat, wall_mat)

            result = AnalysisResult(
                project_id=project_id,
                analysis_type="acoustics",
                result_json=json.dumps({
                    "rt60_seconds": round(rt60, 3),
                    "quality_rating": quality,
                    "recommendations": recommendations,
                }),
            )
            session.add(result)
            await session.commit()

        except Exception as exc:
            error_result = AnalysisResult(
                project_id=project_id,
                analysis_type="acoustics",
                result_json=json.dumps({"error": str(exc)}),
            )
            session.add(error_result)
            await session.commit()
            raise
