import asyncio
import datetime
import hashlib
import json
import sys
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db.session import Base
from app.db.models import Competition, Season, Team, Fixture
from app.features.feature_engine import PointInTimeFeatureEngine



from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def setup_test_db():
    Base.metadata.create_all(bind=engine)

def test_temporal_leakage_protection():
    """
    Automated Test: Verify that adding future matches to the database
    does NOT alter the point-in-time feature snapshot for a target fixture.
    """
    setup_test_db()

    with TestingSessionLocal() as session:
        # Create competition & season
        comp = Competition(code="PL", name="Premier League", country="England", type="DOMESTIC_LEAGUE")
        session.add(comp)
        session.flush()

        season = Season(competition_id=comp.id, name="2024", is_current=True)
        session.add(season)
        session.flush()

        # Create 2 teams
        team_a = Team(provider_external_id=101, name="Arsenal", short_name="ARS")
        team_b = Team(provider_external_id=102, name="Chelsea", short_name="CHE")
        session.add_all([team_a, team_b])
        session.flush()

        t0 = datetime.datetime(2024, 10, 1, 15, 0, tzinfo=datetime.timezone.utc)
        t1 = datetime.datetime(2024, 10, 5, 15, 0, tzinfo=datetime.timezone.utc)
        target_t = datetime.datetime(2024, 10, 10, 15, 0, tzinfo=datetime.timezone.utc)
        future_t1 = datetime.datetime(2024, 10, 12, 15, 0, tzinfo=datetime.timezone.utc)
        future_t2 = datetime.datetime(2024, 10, 20, 15, 0, tzinfo=datetime.timezone.utc)

        # Match 1 (Past)
        m1 = Fixture(
            provider_external_id=1, season_id=season.id, competition_code="PL",
            kickoff_datetime=t0, home_team_id=team_a.id, away_team_id=team_b.id,
            status="FINISHED", home_score=2, away_score=1, winner="HOME_TEAM"
        )
        # Match 2 (Past)
        m2 = Fixture(
            provider_external_id=2, season_id=season.id, competition_code="PL",
            kickoff_datetime=t1, home_team_id=team_b.id, away_team_id=team_a.id,
            status="FINISHED", home_score=0, away_score=0, winner="DRAW"
        )
        # Target Match
        target_match = Fixture(
            provider_external_id=3, season_id=season.id, competition_code="PL",
            kickoff_datetime=target_t, home_team_id=team_a.id, away_team_id=team_b.id,
            status="SCHEDULED"
        )
        session.add_all([m1, m2, target_match])
        session.commit()

        # Compute initial feature snapshot at target_t
        engine_inst = PointInTimeFeatureEngine(session)
        features_before = engine_inst.compute_features_for_fixture(target_match)
        hash_before = hashlib.sha256(json.dumps(features_before, sort_keys=True).encode("utf-8")).hexdigest()

        # Now simulate insertion of FUTURE matches occurring AFTER target_t
        future_m1 = Fixture(
            provider_external_id=4, season_id=season.id, competition_code="PL",
            kickoff_datetime=future_t1, home_team_id=team_a.id, away_team_id=team_b.id,
            status="FINISHED", home_score=5, away_score=0, winner="HOME_TEAM"
        )
        future_m2 = Fixture(
            provider_external_id=5, season_id=season.id, competition_code="PL",
            kickoff_datetime=future_t2, home_team_id=team_b.id, away_team_id=team_a.id,
            status="FINISHED", home_score=0, away_score=4, winner="AWAY_TEAM"
        )
        session.add_all([future_m1, future_m2])
        session.commit()

        # Re-compute features for target_match
        features_after = engine_inst.compute_features_for_fixture(target_match)
        hash_after = hashlib.sha256(json.dumps(features_after, sort_keys=True).encode("utf-8")).hexdigest()

        # ASSERTION 1: Feature vectors must be 100% identical
        assert features_before == features_after, "LEAKAGE DETECTED: Feature vector changed after future matches inserted!"
        
        # ASSERTION 2: Hashes must match
        assert hash_before == hash_after, "LEAKAGE DETECTED: Feature hash changed!"

        print("[SUCCESS] TEMPORAL LEAKAGE TEST PASSED: Zero-lookahead verified!")

if __name__ == "__main__":
    test_temporal_leakage_protection()


