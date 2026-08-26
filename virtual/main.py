import os
import sys

# Ensure root directory is always on sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from virtual.core.config import virtual_config
from virtual.core.db import engine, Base
from virtual.models import virtual_models
from virtual.api.router import router as virtual_api_router
from virtual.workers.ingestion_worker import VirtualIngestionWorker
from virtual.workers.paper_worker import PaperTradingWorker
from virtual.workers.fronttest_worker import VirtualFrontTestWorker

# Auto-create virtual database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="StatIQ Virtual Trader — Standalone Autonomous Virtual Sports Agent",
    description="Autonomous Virtual Sports Data Warehouse, Research, and Simulation Trading Engine.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(virtual_api_router, prefix="/api/v1/virtual-trader")

@app.on_event("startup")
def startup_event():
    print(f"[VirtualTrader] Service initializing on port {virtual_config.PORT}...")
    VirtualIngestionWorker.start()
    PaperTradingWorker.start()
    VirtualFrontTestWorker.start()

@app.get("/health")
def health_check():
    return {
        "service": "StatIQ Virtual Trader",
        "status": "HEALTHY",
        "agent_mode": virtual_config.AGENT_MODE,
        "ingestion_worker": VirtualIngestionWorker.get_status(),
        "paper_worker": PaperTradingWorker.get_status(),
        "fronttest_worker": VirtualFrontTestWorker.is_enabled(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("virtual.main:app", host=virtual_config.HOST, port=virtual_config.PORT, reload=True)
