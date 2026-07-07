"""
FastAPI Dependencies

Provides dependency injection for DataService (Dashboard + Analyze queries).
"""

from typing import AsyncGenerator

from backend.services.data_service import data_service, DataService


async def get_data_service() -> AsyncGenerator[DataService, None]:
    """Yield the DataService singleton (lazy init if not already done)."""
    if not data_service._initialized:
        try:
            await data_service.initialize()
        except Exception:
            pass  # Let endpoints handle the error and return 503
    yield data_service
