from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth import seed_default_admin
from app.config import STATIC_DIR
from app.database import engine, Base, SessionLocal
from app.models import Department
from app.routers import auth_router, user_router, attendance_router, web_router
from app.services.vision_engine import get_vision_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables
    print("Initializing Database tables...")
    Base.metadata.create_all(bind=engine)

    # Ensure schema migrations for columns if running on existing database
    from sqlalchemy import text
    with engine.connect() as conn:
        for col_sql in [
            "ALTER TABLE users ADD COLUMN hourly_rate FLOAT DEFAULT 25.0",
            "ALTER TABLE users ADD COLUMN designation VARCHAR(100) DEFAULT 'Staff'",
        ]:
            try:
                conn.execute(text(col_sql))
                conn.commit()
            except Exception:
                pass

    # Seed Default Department & Admin
    db = SessionLocal()
    try:
        if not db.query(Department).first():
            default_dept = Department(
                name="Computer Science & Engineering",
                shift_start="09:00:00",
                shift_end="17:00:00",
                grace_period_mins=15,
            )
            db.add(default_dept)
            db.commit()
            print("Default Department created: Computer Science & Engineering")

        seed_default_admin(db)
    finally:
        db.close()

    # Pre-warm AI Vision Engine (checks/downloads models if needed)
    print("Pre-warming Vision Engine models...")
    get_vision_engine()
    print("FRAS Enterprise Backend successfully loaded!")

    yield

    # Shutdown
    print("Shutting down FRAS Backend...")


app = FastAPI(
    title="Enterprise Face Recognition Attendance System (FRAS)",
    description="High-accuracy, real-time biometric attendance system with deep metric embeddings.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS Policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount Routers
app.include_router(auth_router.router)
app.include_router(user_router.router)
app.include_router(attendance_router.router)
app.include_router(web_router.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "service": "FRAS Enterprise", "version": "2.0.0"}
