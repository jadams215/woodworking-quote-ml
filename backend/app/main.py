from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.models import Base
from app.routers import auth, catalog, customers, quotes, tracking

settings = get_settings()

app = FastAPI(
    title="B10 Union Woodworking Quote Engine",
    description="Production quoting system for B10 Union, LLC",
    version=settings.engine_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(quotes.router)
app.include_router(catalog.router)
app.include_router(tracking.router)


@app.on_event("startup")
async def startup_event():
    """Verify database connection on startup."""
    try:
        # Test database connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("* Database connection verified")
    except Exception as e:
        print(f"ERROR: Database connection failed: {e}")
        raise


@app.get("/health")
def health_check():
    return {"status": "ok", "version": settings.engine_version}
