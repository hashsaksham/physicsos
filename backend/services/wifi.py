import json
import math
from uuid import uuid4

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sqlalchemy import select

from database import AsyncSessionLocal
from models import AnalysisResult

CELL = 0.1  # metres per grid cell


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return points


async def run_wifi_analysis(
    project_id: str,
    room_id: str,
    rooms_json: str,
    router_x: float,
    router_y: float,
    frequency_ghz: float,
) -> None:
    async with AsyncSessionLocal() as session:
        try:
            rooms = json.loads(rooms_json)
            room = next((r for r in rooms if r["id"] == room_id), None)
            if room is None:
                raise ValueError(f"Room {room_id} not found")

            cols = max(2, int(room["width_m"] / CELL))
            rows = max(2, int(room["height_m"] / CELL))

            wall_grid = np.zeros((rows, cols), dtype=bool)
            wall_grid[0, :] = True
            wall_grid[-1, :] = True
            wall_grid[:, 0] = True
            wall_grid[:, -1] = True

            router_gx = int(np.clip(router_x / CELL, 0, cols - 1))
            router_gy = int(np.clip(router_y / CELL, 0, rows - 1))

            frequency_mhz = frequency_ghz * 1000
            signal_grid = np.full((rows, cols), np.nan)

            for gy in range(rows):
                for gx in range(cols):
                    if wall_grid[gy, gx]:
                        continue
                    dx = (gx - router_gx) * CELL
                    dy = (gy - router_gy) * CELL
                    distance_m = max(math.sqrt(dx ** 2 + dy ** 2), 0.01)

                    ray = _bresenham(router_gx, router_gy, gx, gy)
                    wall_crossings = sum(
                        1 for (rx, ry) in ray[1:-1] if wall_grid[ry, rx]
                    )

                    signal_grid[gy, gx] = (
                        20
                        - 20 * math.log10(distance_m)
                        - 20 * math.log10(frequency_mhz)
                        + 27.55
                        - wall_crossings * 3
                    )

            # Build RGB heatmap
            rgb = np.ones((rows, cols, 3), dtype=np.uint8) * 180  # gray default (walls)
            free = ~wall_grid
            sig = signal_grid

            # Green: signal > -50
            mask_good = free & (sig > -50)
            rgb[mask_good] = [0, 200, 0]

            # Yellow: -70 to -50
            mask_ok = free & (sig <= -50) & (sig >= -70)
            rgb[mask_ok] = [255, 200, 0]

            # Red: signal < -70 (dead zone)
            mask_dead = free & (sig < -70)
            rgb[mask_dead] = [220, 30, 30]

            filename = f"wifi_{uuid4().hex}.png"
            save_path = f"uploads/{filename}"

            fig, ax = plt.subplots(figsize=(8, 6))
            ax.imshow(rgb, origin="upper")
            ax.set_title(f"WiFi Signal — {frequency_ghz} GHz")
            ax.set_xlabel("X (cells, 10 cm each)")
            ax.set_ylabel("Y (cells, 10 cm each)")

            from matplotlib.patches import Patch
            legend = [
                Patch(color=[0, 200 / 255, 0], label="Good (> -50 dBm)"),
                Patch(color=[1, 200 / 255, 0], label="Fair (-50 to -70 dBm)"),
                Patch(color=[220 / 255, 30 / 255, 30 / 255], label="Dead (< -70 dBm)"),
            ]
            ax.legend(handles=legend, loc="upper right", fontsize=8)
            plt.tight_layout()
            plt.savefig(save_path, dpi=100)
            plt.close(fig)

            free_signals = signal_grid[~np.isnan(signal_grid)]
            dead_zone_pct = (
                round(float(np.sum(free_signals < -70) / len(free_signals) * 100), 1)
                if len(free_signals) > 0
                else 0.0
            )
            avg_signal = round(float(np.mean(free_signals)), 1) if len(free_signals) > 0 else 0.0

            result = AnalysisResult(
                project_id=project_id,
                analysis_type="wifi",
                result_json=json.dumps({
                    "dead_zone_percentage": dead_zone_pct,
                    "average_signal_dbm": avg_signal,
                    "heatmap_filename": filename,
                }),
                heatmap_path=save_path,
            )
            session.add(result)
            await session.commit()

        except Exception as exc:
            error_result = AnalysisResult(
                project_id=project_id,
                analysis_type="wifi",
                result_json=json.dumps({"error": str(exc)}),
            )
            session.add(error_result)
            await session.commit()
            raise
