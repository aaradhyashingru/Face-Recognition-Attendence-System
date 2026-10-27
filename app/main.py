from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response

from app.auth import seed_default_admin
from app.config import STATIC_DIR, CORS_ORIGINS, logger
from app.database import engine, Base, SessionLocal
from app.models import Department
from app.routers import auth_router, user_router, attendance_router, web_router
from app.services.vision_engine import get_vision_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Create tables
    logger.info("Initializing database tables...")
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error("Database schema creation warning: %s", e)

    # 2. Safe schema migrations via table inspection (prevents transaction abort errors)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            try:
                res = conn.execute(text("PRAGMA table_info(users)"))
                existing_cols = {row[1] for row in res.fetchall()}
            except Exception:
                existing_cols = set()

            col_defs = [
                ("hourly_rate", "ALTER TABLE users ADD COLUMN hourly_rate FLOAT DEFAULT 25.0"),
                ("designation", "ALTER TABLE users ADD COLUMN designation VARCHAR(100) DEFAULT 'Staff'"),
                ("grace_period_mins", "ALTER TABLE users ADD COLUMN grace_period_mins INTEGER DEFAULT NULL"),
            ]
            for col_name, sql in col_defs:
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        logger.info("Added missing database column: %s", col_name)
                    except Exception as e:
                        logger.warning("Could not add column %s: %s", col_name, e)
                        try:
                            conn.rollback()
                        except Exception:
                            pass
    except Exception as e:
        logger.warning("Column migration inspection warning: %s", e)

    # 3. Seed Default Department & Admin
    try:
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
                logger.info("Default Department created: Computer Science & Engineering")

            seed_default_admin(db)
        finally:
            db.close()
    except Exception as e:
        logger.error("Department or Admin seeding warning: %s", e)

    # 4. Pre-warm AI Vision Engine (checks/downloads models if needed)
    try:
        logger.info("Pre-warming Vision Engine models...")
        get_vision_engine()
        logger.info("AI Vision Engine successfully loaded!")
    except Exception as e:
        logger.error("Vision Engine pre-warming warning: %s (Kiosk will retry on scan)", e)

    logger.info("FRAS Enterprise Backend successfully loaded and ready for requests!")

    yield

    # Shutdown
    logger.info("Shutting down FRAS Backend...")


app = FastAPI(
    title="Enterprise Face Recognition Attendance System (FRAS)",
    description="High-accuracy, real-time biometric attendance system with deep metric embeddings.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS Policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "service": "FRAS Enterprise", "version": "2.0.0"}
