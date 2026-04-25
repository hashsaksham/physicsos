"""
PhysicsOS Integration Test
Run with: .venv/bin/python test_all.py
Server must be running on http://localhost:8000
"""

import json
import time

import requests
from PIL import Image, ImageDraw

BASE = "http://localhost:8000"
passed = 0
failed = 0


# ── helpers ──────────────────────────────────────────────────────────────────

def _badge(success: bool) -> str:
    return "✅ PASS" if success else "❌ FAIL"


def check(label: str, resp: requests.Response, assert_fn=None):
    global passed, failed
    try:
        resp.raise_for_status()
        data = resp.json()
        if assert_fn:
            assert_fn(data)
        print(f"✅ PASS: {label}")
        passed += 1
        return data
    except Exception as exc:
        body = ""
        try:
            body = resp.text[:120]
        except Exception:
            pass
        print(f"❌ FAIL: {label} — {exc} {body}")
        failed += 1
        return None


def poll(label: str, url: str, until_fn, timeout: int = 30, interval: int = 2):
    global passed, failed
    deadline = time.time() + timeout
    last_data = None
    while time.time() < deadline:
        try:
            resp = requests.get(url)
            if resp.status_code == 404:
                time.sleep(interval)
                continue
            data = resp.json()
            last_data = data
            if until_fn(data):
                print(f"✅ PASS: {label}")
                passed += 1
                return data
        except Exception:
            pass
        time.sleep(interval)
    print(f"❌ FAIL: {label} — timed out after {timeout}s. Last response: {str(last_data)[:120]}")
    failed += 1
    return None


# ── generate test image ───────────────────────────────────────────────────────

img = Image.new("RGB", (500, 500), "white")
draw = ImageDraw.Draw(img)
draw.rectangle([10, 10, 490, 490], outline="black", width=8)
# Add an inner room to give the CV pipeline a second contour
draw.rectangle([60, 60, 250, 240], outline="black", width=6)
img.save("test_floor_plan.png")


# ── run tests ─────────────────────────────────────────────────────────────────

print("Running PhysicsOS Integration Tests")
print("=" * 45)

state = {}

# 1. Health
resp = requests.get(f"{BASE}/health")
data = check("GET /health", resp, lambda d: d["status"] == "ok")

# 2. Create project
with open("test_floor_plan.png", "rb") as f:
    resp = requests.post(
        f"{BASE}/api/projects/",
        files={"file": ("test_floor_plan.png", f, "image/png")},
        data={"name": "Integration Test Project"},
    )
data = check(
    "POST /api/projects",
    resp,
    lambda d: "project_id" in d,
)
if data:
    state["project_id"] = data["project_id"]
    print(f"         project_id = {state['project_id']}")

if not state.get("project_id"):
    print("\n❌ Cannot continue without project_id. Is the server running on port 8000?")
    raise SystemExit(1)

pid = state["project_id"]

# 3. Poll project until ready
data = poll(
    f"GET /api/projects/{pid} (wait for ready)",
    f"{BASE}/api/projects/{pid}",
    lambda d: d.get("status") in ("ready", "failed"),
    timeout=30,
)
if data:
    status = data.get("status")
    rooms = data.get("rooms", [])
    print(f"         status={status}, rooms={len(rooms)}")
    if status == "ready" and rooms:
        state["room_id"] = rooms[0]["id"]
        print(f"         room_id = {state['room_id']}")
    elif status == "failed":
        print(f"         error = {data.get('rooms')}")

room_id = state.get("room_id")
if not room_id:
    print("\n⚠️  No room_id — analysis tests will be skipped.")

# 4. Start WiFi analysis
if room_id:
    resp = requests.post(
        f"{BASE}/api/projects/{pid}/analysis/wifi",
        json={"room_id": room_id, "router_x": 2.5, "router_y": 2.5, "frequency_ghz": 2.4},
    )
    check("POST /api/projects/{id}/analysis/wifi", resp, lambda d: "status" in d)

# 5. Poll WiFi result
if room_id:
    data = poll(
        "GET /api/projects/{id}/analysis/wifi/result",
        f"{BASE}/api/projects/{pid}/analysis/wifi/result",
        lambda d: "result" in d,
        timeout=30,
    )
    if data:
        result = data.get("result", {})
        heatmap = data.get("heatmap_url")
        if "error" in result:
            print(f"         ⚠️  analysis error: {result['error']}")
        else:
            print(f"         dead_zone={result.get('dead_zone_percentage')}%, "
                  f"avg_signal={result.get('average_signal_dbm')} dBm, "
                  f"heatmap_url={heatmap}")

# 6. Start acoustics
if room_id:
    resp = requests.post(
        f"{BASE}/api/projects/{pid}/analysis/acoustics",
        json={"room_id": room_id},
    )
    check("POST /api/projects/{id}/analysis/acoustics", resp, lambda d: "status" in d)

# 7. Poll acoustics result
if room_id:
    data = poll(
        "GET /api/projects/{id}/analysis/acoustics/result",
        f"{BASE}/api/projects/{pid}/analysis/acoustics/result",
        lambda d: "result" in d,
        timeout=30,
    )
    if data:
        result = data.get("result", {})
        if "error" in result:
            print(f"         ⚠️  analysis error: {result['error']}")
        else:
            print(f"         rt60={result.get('rt60_seconds')}s, "
                  f"quality={result.get('quality_rating')}")

# 8. Start thermal
if room_id:
    resp = requests.post(
        f"{BASE}/api/projects/{pid}/analysis/thermal",
        json={"room_id": room_id, "outdoor_temp_celsius": 10},
    )
    check("POST /api/projects/{id}/analysis/thermal", resp, lambda d: "status" in d)

# 9. Poll thermal result
if room_id:
    data = poll(
        "GET /api/projects/{id}/analysis/thermal/result",
        f"{BASE}/api/projects/{pid}/analysis/thermal/result",
        lambda d: "result" in d,
        timeout=30,
    )
    if data:
        result = data.get("result", {})
        heatmap = data.get("heatmap_url")
        if "error" in result:
            print(f"         ⚠️  analysis error: {result['error']}")
        else:
            print(f"         total_loss={result.get('total_heat_loss_watts')}W, "
                  f"hvac={result.get('recommended_hvac_tons')} tons, "
                  f"heatmap_url={heatmap}")

# 10. Chat
if room_id:
    resp = requests.post(
        f"{BASE}/api/projects/{pid}/chat",
        json={"message": "what is the RT60 of this room", "room_id": room_id},
    )
    data = check(
        "POST /api/projects/{id}/chat",
        resp,
        lambda d: "action_type" in d and "user_message" in d,
    )
    if data:
        print(f"         action_type={data.get('action_type')}")
        print(f"         user_message={data.get('user_message', '')[:80]}")

# 11. List products (empty list is fine)
resp = requests.get(f"{BASE}/api/projects/{pid}/products")
check("GET /api/projects/{id}/products", resp, lambda d: isinstance(d, list))

# ── summary ───────────────────────────────────────────────────────────────────

print("=" * 45)
total = passed + failed
print(f"Results: {passed}/{total} passed", "🎉" if failed == 0 else "")
