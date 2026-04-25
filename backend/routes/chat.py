from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/")
async def chat():
    return {"message": "not implemented"}
