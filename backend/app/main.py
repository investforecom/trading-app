from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import portfolio, analytics, insights, system, thesis

app = FastAPI(title="Trading API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(insights.router,  prefix="/api/insights",  tags=["insights"])
app.include_router(system.router,    prefix="/api/system",    tags=["system"])
app.include_router(thesis.router,    prefix="/api/thesis",    tags=["thesis"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
