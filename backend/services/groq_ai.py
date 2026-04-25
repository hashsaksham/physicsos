import json
import os

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

_FALLBACK = {
    "action_type": "INFORMATION",
    "parameters": {},
    "user_message": "AI service is currently unavailable. Please check your API key.",
}

_SYSTEM_TEMPLATE = """\
You are PhysicsOS, an AI spatial intelligence assistant.
You help users understand and modify their room.

Current room data:
{room_json}

You must respond with ONLY a valid JSON object in this exact format:
{{
  "action_type": "MATERIAL_CHANGE" or "INFORMATION" or "ANALYSIS_REQUEST" or "STYLE_CHANGE",
  "parameters": {{
    // for MATERIAL_CHANGE: {{"property": "wall_color", "value": "#FF0000"}}
    // for ANALYSIS_REQUEST: {{"analysis_type": "wifi" or "acoustics" or "thermal"}}
    // for STYLE_CHANGE: {{"description": "..."}}
    // for INFORMATION: {{}}
  }},
  "user_message": "friendly plain English response to the user explaining what you are doing or answering their question"
}}"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


async def process_chat_message(
    message: str,
    project_id: str,
    room_id: str,
    rooms_json: str,
) -> dict:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return _FALLBACK.copy()

    rooms = json.loads(rooms_json) if rooms_json else []
    room = next((r for r in rooms if r["id"] == room_id), None)
    room_json_str = json.dumps(room, indent=2) if room else "{}"

    system_prompt = _SYSTEM_TEMPLATE.format(room_json=room_json_str)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return _FALLBACK.copy()

    try:
        action = json.loads(_strip_fences(content))
    except (json.JSONDecodeError, ValueError):
        return _FALLBACK.copy()

    if "action_type" not in action:
        action["action_type"] = "INFORMATION"
    if "parameters" not in action:
        action["parameters"] = {}
    if "user_message" not in action:
        action["user_message"] = content

    return action
