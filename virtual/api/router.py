from fastapi import APIRouter
from virtual.api.dashboard import router as dashboard_router
from virtual.api.data import router as data_router
from virtual.api.research import router as research_router
from virtual.api.predictions import router as predictions_router
from virtual.api.backtest_routes import router as backtest_router
from virtual.api.paper_routes import router as paper_router
from virtual.api.risk_routes import router as risk_router
from virtual.api.agent_control_routes import router as agent_control_router
from virtual.api.fronttest_routes import router as fronttest_router

router = APIRouter()

router.include_router(agent_control_router, tags=["Virtual Trader - Agent Controller"])
router.include_router(fronttest_router, tags=["Virtual Trader - Front Testing & Telegram"])
router.include_router(dashboard_router, tags=["Virtual Trader - Dashboard"])
router.include_router(data_router, tags=["Virtual Trader - Data Warehouse"])
router.include_router(research_router, prefix="/research", tags=["Virtual Trader - Research Engine"])
router.include_router(predictions_router, prefix="/predictions", tags=["Virtual Trader - Predictions & Signals"])
router.include_router(backtest_router, prefix="/backtesting", tags=["Virtual Trader - Backtesting Engine"])
router.include_router(paper_router, prefix="/paper", tags=["Virtual Trader - Paper Trading Ledger"])
router.include_router(risk_router, prefix="/risk", tags=["Virtual Trader - Risk Engine"])



