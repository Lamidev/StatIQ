import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import unittest
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Fixture, LivePredictionLedger


from app.markets.scenario_builder import ScenarioBuilderEngine, ScenarioRequest
from app.external.code_parser import ExternalCodeParser
from app.external.fixture_resolver import FixtureResolver
from app.external.selection_analyzer import SelectionAnalyzerEngine
from app.adapters.bookmaker_adapter import SportyBetAdapter, CanonicalMarketRegistry

class TestPhases10To12(unittest.TestCase):
    def setUp(self):
        # In-memory SQLite database
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

        # Seed sample fixtures
        now = datetime.datetime.now(datetime.timezone.utc)
        self.fix1 = Fixture(id=1001, provider_external_id="FD_1001", season_id=1, competition_code="PL", home_team_id=1, away_team_id=2, kickoff_datetime=now + datetime.timedelta(days=1), status="TIMED")
        self.fix2 = Fixture(id=1002, provider_external_id="FD_1002", season_id=1, competition_code="PD", home_team_id=3, away_team_id=4, kickoff_datetime=now + datetime.timedelta(days=2), status="TIMED")
        self.session.add_all([self.fix1, self.fix2])


        self.session.commit()

        # Seed predictions
        self.pred1 = LivePredictionLedger(
            fixture_id=1001, model_name="Weighted_Ensemble", model_version="v1.0.0",
            prob_home=0.71, prob_draw=0.18, prob_away=0.11, prob_over_1_5=0.82, prob_over_2_5=0.65, prob_btts_yes=0.55, status="PENDING"
        )
        self.pred2 = LivePredictionLedger(
            fixture_id=1002, model_name="Weighted_Ensemble", model_version="v1.0.0",
            prob_home=0.42, prob_draw=0.28, prob_away=0.30, prob_over_1_5=0.78, prob_over_2_5=0.58, prob_btts_yes=0.68, status="PENDING"
        )
        self.session.add_all([self.pred1, self.pred2])
        self.session.commit()

    def tearDown(self):
        self.session.close()

    # --- PHASE 10 TESTS ---
    def test_scenario_builder_candidate_filtering_and_independence(self):
        builder = ScenarioBuilderEngine(self.session)
        req = ScenarioRequest(minimum_probability=0.60, allow_same_fixture_multiple_markets=False)
        candidates = builder.get_candidate_pool(req)
        
        # Max 1 candidate per fixture when allow_same_fixture_multiple_markets is False
        fixture_ids = [c.fixture_id for c in candidates]
        self.assertEqual(len(fixture_ids), len(set(fixture_ids)))

    def test_scenario_builder_probability_preservation(self):
        builder = ScenarioBuilderEngine(self.session)
        req = ScenarioRequest(minimum_probability=0.60, minimum_legs=1, maximum_legs=2)
        res = builder.build_scenarios(req)
        
        self.assertEqual(res["status"] if "status" in res else "COMPLETED", "COMPLETED")
        self.assertGreater(len(res["scenarios"]), 0)
        
        # Verify model probability preservation
        top_scenario = res["scenarios"][0]
        for sel in top_scenario["selections"]:
            if sel["fixture_id"] == 1001 and sel["selection"] == "HOME":
                self.assertEqual(sel["model_probability"], 0.71)

    # --- PHASE 11 & 12 SPORTYBET ADAPTER TESTS ---
    def test_sportybet_code_parser(self):
        parser = ExternalCodeParser()
        res = parser.parse_external_code("BC7F49A", provider="SPORTYBET", session=self.session)
        self.assertEqual(res.parse_status, "PARSED")
        self.assertEqual(res.provider, "SPORTYBET")
        self.assertGreater(len(res.selections), 0)

    def test_sportybet_adapter_capabilities_and_code_gen(self):
        adapter = SportyBetAdapter(self.session)
        caps = adapter.get_capabilities()
        self.assertEqual(caps.provider, "SPORTYBET")
        self.assertTrue(caps.supports_code_reading)
        self.assertTrue(caps.supports_code_generation)

        # Test Code Generation
        sample_selections = [
            {"fixture_id": 1001, "selection": "HOME", "odds": 2.10},
            {"fixture_id": 1002, "selection": "OVER_2_5", "odds": 1.70}
        ]
        code_res = adapter.generate_booking_code(sample_selections)
        self.assertIn("booking_code", code_res)
        self.assertTrue(code_res["booking_code"].startswith("BC"))

    def test_canonical_market_registry(self):
        self.assertIn("OVER_2_5", CanonicalMarketRegistry.CANONICAL_MARKETS)
        self.assertEqual(CanonicalMarketRegistry.CANONICAL_MARKETS["OVER_2_5"], ("OVER_UNDER", 2.5, "OVER"))


if __name__ == "__main__":
    unittest.main()
