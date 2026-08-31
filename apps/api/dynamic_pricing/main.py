"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import get_settings
from .packaging import web_dist
from .routers import (
    bookings,
    events,
    history,
    market,
    outcomes,
    pms,
    rate,
    rate_book,
    recommendations,
    seasons as seasons_router,
    settings as settings_router,
    system,
)

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
        "Explainable Revenue Intelligence Copilot above Blue Jay PMS, for Luminous "
        "Luxury Apartments. Anchored on the client-validated seasonal NET rate book; "
        "the dynamic layer on top is UNVALIDATED. Runs in Shadow Mode — nothing is "
        "pushed to Blue Jay or any OTA."
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
app.include_router(bookings.router)
app.include_router(pms.router)
app.include_router(rate.router)
app.include_router(seasons_router.router)
app.include_router(recommendations.router)
app.include_router(settings_router.router)
app.include_router(history.router)
app.include_router(market.router)
app.include_router(rate_book.router)
app.include_router(events.router)
app.include_router(outcomes.router)


@app.get("/api")
def api_root():
    """The API's own banner.

    This used to answer "/", which the packaged build needs for the web app —
    Starlette matches routes before mounts, so a route here would have served
    JSON to every operator who opened the address.
    """
    return {
        "name": "Dynamic Pricing Property API",
        "version": __version__,
        "docs": "/docs",
        "mode": "shadow",
        "notice": (
            "Seasonal NET rate book is CLIENT_VALIDATED. The dynamic layer "
            "(pace, pickup, events, market) is UNVALIDATED."
        ),
    }


# --- the web app ------------------------------------------------------------
# Mounted LAST so every route above still wins: Starlette matches routes in
# registration order, and a mount at "/" registered earlier would answer /api
# and /docs with an HTML page. The failure would surface in the browser as a
# JSON parse error, nowhere near this file.
#
# Absence is the normal case in development — `make dev` serves the frontend
# from Next's own server on :3000 and never exports at all.
_web_dist = web_dist()
if _web_dist is not None:
    app.mount("/", StaticFiles(directory=_web_dist, html=True), name="web")
