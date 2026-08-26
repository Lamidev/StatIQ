from typing import Dict, Any, List
from sqlalchemy.orm import Session
from virtual.models.virtual_models import VirtualStrategy

class StrategyRegistry:
    """
    Manages registered quantitative virtual trading strategies, their parameters,
    and lifecycle states (RESEARCH, BACKTESTING, PAPER, QUALIFIED, LIVE, SUSPENDED).
    """

    DEFAULT_STRATEGIES = [
        {
            "code": "VIRTUAL_OVER_15_STABLE",
            "name": "High-Expectancy Over 1.5 Goals Strategy",
            "target_market": "OVER_UNDER_1.5",
            "status": "PAPER",
            "current_version": "v1.0.0",
            "min_sample_size": 300,
            "min_edge_threshold": 0.03,
            "min_model_probability": 0.74,
            "max_odds": 1.95,
            "min_odds": 1.25,
            "description": "Exploits high-tempo virtual matches where Poisson goal expectancy exceeds 2.5 total expected goals."
        },
        {
            "code": "VIRTUAL_HOME_FAVORED_VALUE",
            "name": "Home-Dominance Value Strategy",
            "target_market": "1X2_HOME",
            "status": "PAPER",
            "current_version": "v1.0.0",
            "min_sample_size": 500,
            "min_edge_threshold": 0.04,
            "min_model_probability": 0.48,
            "max_odds": 2.60,
            "min_odds": 1.65,
            "description": "Selects Home selections where model probability exceeds bookmaker fair probability by >= 4%."
        },
        {
            "code": "VIRTUAL_DOUBLE_CHANCE_1X",
            "name": "Defensive 1X Double Chance Anchor",
            "target_market": "DOUBLE_CHANCE_1X",
            "status": "QUALIFIED",
            "current_version": "v1.1.0",
            "min_sample_size": 600,
            "min_edge_threshold": 0.02,
            "min_model_probability": 0.70,
            "max_odds": 1.60,
            "min_odds": 1.18,
            "description": "High-hit rate defensive line combining Home Win + Draw for steady compound capital growth."
        },
        {
            "code": "VIRTUAL_BTTS_HIGH_EXPECTANCY",
            "name": "Both Teams to Score (BTTS) Expectancy",
            "target_market": "BTTS_YES",
            "status": "RESEARCH",
            "current_version": "v0.9.0",
            "min_sample_size": 250,
            "min_edge_threshold": 0.035,
            "min_model_probability": 0.55,
            "max_odds": 2.10,
            "min_odds": 1.55,
            "description": "Identifies evenly-matched high-scoring virtual fixtures where both lambdas exceed 1.20 goals."
        }
    ]

    @classmethod
    def get_all_strategies(cls) -> List[Dict[str, Any]]:
        return cls.DEFAULT_STRATEGIES

    @classmethod
    def ensure_strategies_in_db(cls, db: Session):
        for s in cls.DEFAULT_STRATEGIES:
            existing = db.query(VirtualStrategy).filter(VirtualStrategy.code == s["code"]).first()
            if not existing:
                strat = VirtualStrategy(
                    code=s["code"],
                    name=s["name"],
                    target_market=s["target_market"],
                    status=s["status"],
                    current_version=s["current_version"],
                    min_sample_size=s["min_sample_size"],
                    min_edge_threshold=s["min_edge_threshold"],
                )
                db.add(strat)
        db.commit()
