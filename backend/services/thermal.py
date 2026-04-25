import json
from uuid import uuid4

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from database import AsyncSessionLocal
from models import AnalysisResult

INDOOR_TEMP = 21.0

U_VALUES = {
    "drywall":   1.7,
    "concrete":  3.5,
    "brick":     2.1,
    "insulated": 0.3,
    "hardwood":  1.5,
    "carpet":    0.9,
    "tile":      1.8,
}


def _u(material: str) -> float:
    return U_VALUES.get(material, 1.7)


def _build_surfaces(room: dict) -> list[dict]:
    w = room["width_m"]
    h = room["height_m"]
    ch = room["ceiling_height_m"]
    wall_mat = room.get("wall_material", "drywall")
    floor_mat = room.get("floor_material", "hardwood")

    return [
        {"name": "North Wall", "area_m2": w * ch,  "u_value": _u(wall_mat)},
        {"name": "South Wall", "area_m2": w * ch,  "u_value": _u(wall_mat)},
        {"name": "East Wall",  "area_m2": h * ch,  "u_value": _u(wall_mat)},
        {"name": "West Wall",  "area_m2": h * ch,  "u_value": _u(wall_mat)},
        {"name": "Floor",      "area_m2": w * h,   "u_value": _u(floor_mat)},
        {"name": "Ceiling",    "area_m2": w * h,   "u_value": _u(wall_mat)},
    ]


def _recommendations(surfaces: list[dict], worst: dict, outdoor_temp: float, floor_mat: str) -> list[str]:
    recs = []
    recs.append(f"Insulate {worst['name']} to reduce heat loss by ~60%")

    for s in surfaces:
        if s["u_value"] >= 3.0 and "Wall" in s["name"]:
            recs.append(f"{s['name']} uses high-conductivity material — consider insulated panels")

    if outdoor_temp < 0:
        recs.append("Install double-pane windows to reduce convective losses")

    if floor_mat in ("tile", "concrete"):
        recs.append("Add underfloor insulation or rugs — cold floors increase perceived heat loss")

    return list(dict.fromkeys(recs))  # deduplicate while preserving order


async def run_thermal_analysis(
    project_id: str,
    room_id: str,
    rooms_json: str,
    outdoor_temp_celsius: float,
) -> None:
    async with AsyncSessionLocal() as session:
        try:
            rooms = json.loads(rooms_json)
            room = next((r for r in rooms if r["id"] == room_id), None)
            if room is None:
                raise ValueError(f"Room {room_id} not found")

            delta_t = INDOOR_TEMP - outdoor_temp_celsius
            surfaces = _build_surfaces(room)

            for s in surfaces:
                s["heat_loss_w"] = s["u_value"] * s["area_m2"] * delta_t

            total_watts = sum(s["heat_loss_w"] for s in surfaces)
            total_btu = round(total_watts * 3.412, 1)
            hvac_tons = round(total_btu / 12000, 2)
            worst = max(surfaces, key=lambda s: s["heat_loss_w"])

            # Bar chart
            names = [s["name"] for s in surfaces]
            losses = [s["heat_loss_w"] for s in surfaces]
            max_loss = max(losses) if losses else 1

            colors = []
            for loss in losses:
                ratio = loss / max_loss
                if ratio >= 0.8:
                    colors.append("#E53935")
                elif ratio >= 0.5:
                    colors.append("#FB8C00")
                else:
                    colors.append("#43A047")

            fig, ax = plt.subplots(figsize=(9, 5))
            bars = ax.bar(names, losses, color=colors)
            ax.set_title(f"Heat Loss by Surface — ΔT={delta_t:.1f}°C")
            ax.set_ylabel("Heat Loss (W)")
            ax.set_xlabel("Surface")
            for bar, loss in zip(bars, losses):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                        f"{loss:.0f}W", ha="center", va="bottom", fontsize=8)
            plt.tight_layout()

            filename = f"thermal_{uuid4().hex}.png"
            save_path = f"uploads/{filename}"
            plt.savefig(save_path, dpi=100)
            plt.close(fig)

            floor_mat = room.get("floor_material", "hardwood")
            recs = _recommendations(surfaces, worst, outdoor_temp_celsius, floor_mat)

            result = AnalysisResult(
                project_id=project_id,
                analysis_type="thermal",
                result_json=json.dumps({
                    "total_heat_loss_watts": round(total_watts, 1),
                    "total_heat_loss_btu": total_btu,
                    "recommended_hvac_tons": hvac_tons,
                    "worst_surface": worst["name"],
                    "chart_filename": filename,
                    "recommendations": recs,
                }),
                heatmap_path=save_path,
            )
            session.add(result)
            await session.commit()

        except Exception as exc:
            error_result = AnalysisResult(
                project_id=project_id,
                analysis_type="thermal",
                result_json=json.dumps({"error": str(exc)}),
            )
            session.add(error_result)
            await session.commit()
            raise
