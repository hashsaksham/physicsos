from fastapi import APIRouter

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/")
async def run_analysis():
    return {"message": "not implemented"}
