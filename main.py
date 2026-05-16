from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.domains.auth.router import router as auth_router
from app.domains.courses.router import router as courses_router
from app.domains.concepts.router import router as concepts_router
from app.domains.recall.router import router as recall_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 StudyCore API starting — environment: {settings.APP_ENV}")
    yield
    print("👋 StudyCore API shutting down")


app = FastAPI(
    title="StudyCore API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url=None,
)

# CORS — must be explicit origins (no wildcard) when allow_credentials=True
# Add every frontend URL you use here
allowed_origins = [
    settings.FRONTEND_URL,          # Production Vercel URL
    "http://localhost:3000",        # Local dev
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,          # Required for cookies
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
    expose_headers=["Set-Cookie"],   # Allow frontend to see Set-Cookie header
)

app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(concepts_router)
app.include_router(recall_router)


@app.get("/health")
def health_check():
    from app.db.session import SessionLocal
    from app.models.user import User
    try:
        db = SessionLocal()
        count = db.query(User).count()
        db.close()
        return {
            "status": "healthy",
            "env": settings.APP_ENV,
            "db": "connected",
            "users": count,
            "frontend_url": settings.FRONTEND_URL,
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.head("/health")
def health_head():
    from fastapi.responses import Response
    return Response(status_code=200)
