from contextlib import asynccontextmanager
import logging
from sqlalchemy import inspect, text
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .config import BASE_DIR, get_settings
from .database import Base, engine, SessionLocal
from .routes import router
from .scheduler import start_scheduler, stop_scheduler, reset_stale_checks
from .demo import seed_demo
from .models import Monitor

logging.basicConfig(level=logging.INFO)
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    # Lightweight SQLite migration for existing installations.
    if engine.dialect.name == "sqlite":
        columns = {c["name"] for c in inspect(engine).get_columns("monitors")}
        with engine.begin() as conn:
            if "watch_selectors" not in columns:
                conn.execute(text("ALTER TABLE monitors ADD COLUMN watch_selectors TEXT"))
            if "ignore_selectors" not in columns:
                conn.execute(text("ALTER TABLE monitors ADD COLUMN ignore_selectors TEXT"))
    reset_stale_checks()
    if settings.demo_mode:
        with SessionLocal() as db:
            if not db.query(Monitor).count():
                seed_demo(db)
    if settings.scheduler_enabled:
        start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(title="Watchtower API", version="1.0.0", lifespan=lifespan)
origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["http://localhost:5173"], allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])
app.include_router(router, prefix="/api")
app.mount("/screenshots", StaticFiles(directory=settings.screenshots_dir, check_dir=False), name="screenshots")

@app.get("/")
def root():
    # In Docker, serve the existing built React dashboard from the same origin as the API.
    frontend_index = BASE_DIR / "static" / "index.html"
    if frontend_index.is_file():
        return FileResponse(frontend_index)
    return {"name": "Watchtower", "docs": "/docs", "health": "/api/health"}

# The frontend build is included in the deployment image. API and screenshot routes
# are registered above this catch-all mount so they keep their existing behavior.
static_dir = BASE_DIR / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
