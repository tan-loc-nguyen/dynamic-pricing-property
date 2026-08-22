"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .routers import history, market, recommendations, settings as settings_router, system

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the database exists and demo data is present before serving.

    Makes `make dev` a genuine one-command start: no separate migrate/seed step.
    """
    from .seed import bootstrap

    print("Dynamic Pricing Property API starting…")
    try:
        summary = bootstrap(force=False, quiet=False)
        if summary.get("skipped"):
            print("  Using existing database.")
    except Exception as exc:  # noqa: BLE001 - never block startup on seeding
        print(f"  ! Bootstrap failed: {type(exc).__name__}: {exc}")
        print("    The API will still start; use POST /api/demo/reset to retry.")
    print(f"  Data provider: {settings.data_provider} | Market provider: {settings.market_provider}")
    yield


app = FastAPI(
    title="Dynamic Pricing Property API",
    version=__version__,
    description=(
        "Explainable pricing copilot for Luminous Luxury Apartment. "
        "Pricing Engine V1 uses provisional, UNVALIDATED business assumptions."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(recommendations.router)
app.include_router(settings_router.router)
app.include_router(history.router)
app.include_router(market.router)


@app.get("/")
def root():
    return {
        "name": "Dynamic Pricing Property API",
        "version": __version__,
        "docs": "/docs",
        "notice": "Pricing Engine V1 assumptions are provisional and UNVALIDATED.",
    }
