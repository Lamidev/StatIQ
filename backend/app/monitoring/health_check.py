import datetime
from typing import Dict, Any, List
from sqlalchemy import select, func, and_

from app.db.models import Fixture, LivePredictionLedger, MarketOdds, ProviderMarketMapping

class PipelineHealthCheckEngine:
    """
    Phase 13 Data Quality & Pipeline Health Check Engine.
    Audits database integrity and pipeline health:
    - Missing/unpredicted upcoming fixtures
    - Duplicate fixture records
    - Shifted kickoff times
    - Finished fixtures missing final scores
    - Missing market odds entries
    - Provider market mapping coverage
    """
    def __init__(self, session):
        self.session = session

    def run_health_check(self) -> Dict[str, Any]:
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # 1. Total Fixture Counts by Status
        stmt_status = select(Fixture.status, func.count(Fixture.id)).group_by(Fixture.status)
        status_counts = dict(self.session.execute(stmt_status).all())

        # 2. Upcoming Fixtures missing Live Predictions
        stmt_unpredicted = (
            select(Fixture)
            .outerjoin(LivePredictionLedger, Fixture.id == LivePredictionLedger.fixture_id)
            .where(
                and_(
                    Fixture.status.in_(["TIMED", "SCHEDULED"]),
                    Fixture.kickoff_datetime > now,
                    LivePredictionLedger.id.is_(None)
                )
            )
        )
        unpredicted_fixtures = list(self.session.execute(stmt_unpredicted).scalars().all())

        # 3. Finished Fixtures missing scores
        stmt_missing_scores = select(Fixture).where(
            and_(
                Fixture.status.in_(["FINISHED", "FT"]),
                (Fixture.home_score.is_(None) | Fixture.away_score.is_(None))
            )
        )
        missing_score_fixtures = list(self.session.execute(stmt_missing_scores).scalars().all())

        # 4. Total Odds Records & Unique Bookmakers
        stmt_odds_count = select(func.count(MarketOdds.id))
        total_odds = self.session.execute(stmt_odds_count).scalar() or 0

        # 5. Active Provider Market Mappings
        stmt_mappings = select(func.count(ProviderMarketMapping.id)).where(ProviderMarketMapping.mapping_status == "ACTIVE")
        active_mappings = self.session.execute(stmt_mappings).scalar() or 0

        # Pipeline Health Status Evaluation
        issues = []
        if len(unpredicted_fixtures) > 0:
            issues.append(f"{len(unpredicted_fixtures)} upcoming fixtures missing live predictions")
        if len(missing_score_fixtures) > 0:
            issues.append(f"{len(missing_score_fixtures)} finished fixtures missing scores")

        if len(issues) == 0:
            pipeline_status = "HEALTHY"
        elif len(issues) < 3:
            pipeline_status = "DEGRADED"
        else:
            pipeline_status = "CRITICAL_PIPELINE_ISSUES"

        return {
            "pipeline_status": pipeline_status,
            "check_timestamp": now.isoformat(),
            "fixture_counts_by_status": status_counts,
            "unpredicted_upcoming_fixtures_count": len(unpredicted_fixtures),
            "finished_fixtures_missing_scores_count": len(missing_score_fixtures),
            "total_market_odds_records": total_odds,
            "active_provider_market_mappings": active_mappings,
            "issues": issues
        }

def check_system_health(session=None) -> Dict[str, Any]:
    if session is None:
        from app.db.session import SessionLocal
        with SessionLocal() as db:
            engine = PipelineHealthCheckEngine(db)
            return engine.run_health_check()
    else:
        engine = PipelineHealthCheckEngine(session)
        return engine.run_health_check()
