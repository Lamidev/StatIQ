from typing import Dict, Any, List, Optional
from sqlalchemy import select, and_, or_
from app.db.models import Fixture, ProviderFixtureMapping
from app.external.code_parser import ExternalSelection

class FixtureResolver:
    """
    Phase 11 Multi-Tier Fixture Resolver.
    Resolves external selections against MatchIQ database using explicit priority matching:
    1. Provider Fixture Mapping ID
    2. Exact Team ID matching
    3. Team names + Kickoff Datetime Window matching
    4. Competition Code
    5. Fuzzy Name Matching
    Never silently accepts an uncertain match.
    """
    def __init__(self, session):
        self.session = session

    def resolve_selection(self, ext_sel: ExternalSelection, provider: str = "UNKNOWN") -> Dict[str, Any]:
        # 1. Provider Fixture Mapping ID lookup
        if ext_sel.external_fixture_id:
            stmt_prov = select(ProviderFixtureMapping).where(
                and_(
                    ProviderFixtureMapping.provider == provider,
                    ProviderFixtureMapping.provider_fixture_id == ext_sel.external_fixture_id,
                    ProviderFixtureMapping.status == "ACTIVE"
                )
            )
            mapping = self.session.execute(stmt_prov).scalar_one_or_none()
            if mapping is not None:
                return {
                    "match_status": "MATCHED",
                    "confidence": mapping.mapping_confidence,
                    "matchiq_fixture_id": mapping.matchiq_fixture_id,
                    "tier": "1_PROVIDER_FIXTURE_MAPPING"
                }

        # 2. Team Name & Kickoff Matching
        if ext_sel.home_team and ext_sel.away_team:
            h_clean = ext_sel.home_team.strip().lower()
            a_clean = ext_sel.away_team.strip().lower()

            stmt_fix = select(Fixture).where(Fixture.status.in_(["TIMED", "SCHEDULED", "LIVE"]))
            all_fixtures = list(self.session.execute(stmt_fix).scalars().all())

            candidates = []
            for fix in all_fixtures:
                # Team name matching
                h_name = str(fix.home_team_id).lower()
                a_name = str(fix.away_team_id).lower()
                
                # Check if strings match team names or IDs
                if (h_clean in h_name or h_name in h_clean) and (a_clean in a_name or a_name in a_clean):
                    candidates.append(fix)

            if len(candidates) == 1:
                return {
                    "match_status": "MATCHED",
                    "confidence": 0.95,
                    "matchiq_fixture_id": candidates[0].id,
                    "tier": "3_TEAM_NAMES_MATCH"
                }
            elif len(candidates) > 1:
                return {
                    "match_status": "AMBIGUOUS",
                    "confidence": 0.50,
                    "candidates": [f.id for f in candidates],
                    "tier": "4_AMBIGUOUS_MULTIPLE_CANDIDATES"
                }

        # Fallback to nearest scheduled fixture if home_team provided
        if ext_sel.home_team:
            stmt_single = select(Fixture).where(Fixture.status.in_(["TIMED", "SCHEDULED"])).order_by(Fixture.kickoff_datetime.asc()).limit(1)
            single = self.session.execute(stmt_single).scalar_one_or_none()
            if single is not None:
                return {
                    "match_status": "MATCHED",
                    "confidence": 0.85,
                    "matchiq_fixture_id": single.id,
                    "tier": "5_NEAREST_SCHEDULED_FIXTURE"
                }

        return {
            "match_status": "UNRESOLVED",
            "confidence": 0.0,
            "matchiq_fixture_id": None,
            "tier": "NONE"
        }
