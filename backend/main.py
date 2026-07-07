"""
FastAPI Application Entry Point

Features:
- Lifespan management: DB pool init / cleanup
- CORS for local frontend development
- Router groups: /api/v1/data (Dashboard), /api/v1/analyze (AI exploration)
- Static file serving for built frontend
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routers import data, analyze
from backend.services.data_service import data_service


# ---------------------------------------------------------------------------
# Lifespan: Initialize services on startup, cleanup on shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    print("🚀 Initializing GDELT Analysis Platform...")
    
    # Initialize DataService (DB pool)
    db_ok = False
    try:
        await data_service.initialize()
        print("✅ DataService initialized")
        db_ok = True
    except Exception as e:
        print(f"⚠️  DataService initialization failed: {e}")
        print("   Dashboard and Analyze endpoints will return errors until DB is available.")
    
    # Print available routes
    print("\n📡 Available endpoints:")
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods = ",".join(route.methods - {"HEAD"})
            if methods:
                print(f"   {methods:8s} {route.path}")
    
    status = "🟢" if db_ok else "🟡"
    print(f"\n{status} Server ready (DB: {'connected' if db_ok else 'disconnected'})\n")
    
    yield
    
    # Cleanup
    print("\n🛑 Shutting down...")
    try:
        await data_service.close()
        print("✅ DataService closed")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# App Factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="GDELT Analysis Platform",
        description="AI-driven data visualization and exploration for GDELT 2.0",
        version="3.0.0",
        lifespan=lifespan,
    )
    
    # CORS: Allow local frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # API Routers
    app.include_router(data.router, prefix="/api/v1")
    app.include_router(analyze.router, prefix="/api/v1")
    
    # Health check at root
    @app.get("/health", tags=["health"])
    async def root_health():
        return {"ok": True, "service": "gdelt-platform", "version": "3.0.0"}
    
    # Serve built frontend (if exists)
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
    
    return app


# Global app instance
app = create_app()
