import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from database import init_db
from routes import analysis, chat, products, projects
from routes.analysis import uploads_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("uploads", exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="PhysicsOS API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(analysis.router)
app.include_router(uploads_router)
app.include_router(chat.router)
app.include_router(products.router)


@app.get("/health")
async def health():
    return {"status": "ok"}

