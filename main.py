from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.domains.auth.router import router as auth_router
from app.domains.courses.router import router as courses_router
from app.domains.concepts.router import router as concepts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 StudyCore API starting — environment: {settings.APP_ENV}")
    yield
    print("👋 StudyCore API shutting down")


app = FastAPI(
    title="StudyCore API",
    description="Cognitive fitness engine for university students",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(concepts_router)


@app.get("/health")
def health_check():
    from app.db.session import SessionLocal
    from app.models.user import User
    try:
        db = SessionLocal()
        count = db.query(User).count()
        db.close()
        return {"status": "healthy", "env": settings.APP_ENV, "db": "connected", "users": count}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.head("/health")
def health_head():
    from fastapi.responses import Response
    return Response(status_code=200)
