import json
from uuid import uuid4

import cv2
from sqlalchemy import select

from database import AsyncSessionLocal
from models import Project


async def process_floor_plan(file_path: str, project_id: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project is None:
            return

        try:
            img = cv2.imread(file_path)
            if img is None:
                raise ValueError(f"Could not read image: {file_path}")

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            filtered = [c for c in contours if cv2.contourArea(c) > 5000]
            filtered.sort(key=cv2.contourArea, reverse=True)

            if not filtered:
                project.rooms_json = json.dumps([])
                project.status = "ready"
                await session.commit()
                return

            largest_x, largest_y, largest_w, largest_h = cv2.boundingRect(filtered[0])
            px_per_m = max(largest_w, largest_h) / 5.0

            rooms = []
            for i, contour in enumerate(filtered):
                x, y, w, h = cv2.boundingRect(contour)
                rooms.append({
                    "id": str(uuid4()),
                    "label": f"Room {i + 1}",
                    "width_m": round(w / px_per_m, 2),
                    "height_m": round(h / px_per_m, 2),
                    "area_m2": round((w * h) / (px_per_m ** 2), 2),
                    "ceiling_height_m": 2.7,
                    "x_m": round(x / px_per_m, 2),
                    "y_m": round(y / px_per_m, 2),
                    "wall_material": "drywall",
                    "wall_color": "#FFFFFF",
                    "floor_material": "hardwood",
                    "floor_color": "#C4A265",
                    "windows": [],
                    "doors": [],
                })

            project.rooms_json = json.dumps(rooms)
            project.status = "ready"
            await session.commit()

        except Exception:
            project.status = "failed"
            await session.commit()
            raise
