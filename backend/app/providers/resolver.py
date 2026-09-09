import re
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from app.db.models import CanonicalFixture, FixtureProviderMapping

class FixtureIdentityResolver:
    """
    StatIQ V2.0 Canonical Fixture Identity Resolver.
    Ensures every match gets a permanent internal ID (fx_...) mapped to external provider IDs.
    """

    @staticmethod
    def generate_canonical_id(home_team: str, away_team: str, date_str: Optional[str] = None) -> str:
        clean_h = re.sub(r"[^a-zA-Z0-9]", "", home_team.lower())
        clean_a = re.sub(r"[^a-zA-Z0-9]", "", away_team.lower())
        d_part = date_str or datetime.now(timezone.utc).strftime("%Y%m%d")
        raw_key = f"{clean_h}_{clean_a}_{d_part}"
        h = hashlib.md5(raw_key.encode()).hexdigest()[:10]
        return f"fx_{h}"

    @staticmethod
    def parse_kickoff_datetime(raw_val: Any) -> datetime:
        if not raw_val:
            return datetime.now(timezone.utc)
        if isinstance(raw_val, datetime):
            return raw_val if raw_val.tzinfo else raw_val.replace(tzinfo=timezone.utc)
        if isinstance(raw_val, (int, float)):
            try:
                ts = raw_val / 1000.0 if raw_val > 1e11 else float(raw_val)
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                return datetime.now(timezone.utc)
        if isinstance(raw_val, str):
            raw_val = raw_val.strip()
            if not raw_val:
                return datetime.now(timezone.utc)
            try:
                num = float(raw_val)
                ts = num / 1000.0 if num > 1e11 else num
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except ValueError:
                pass
            try:
                clean_str = raw_val.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_str)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
        return datetime.now(timezone.utc)

    @classmethod
    def resolve_and_persist(
        cls,
        db: Session,
        home_team: str,
        away_team: str,
        competition: str = "League",
        kickoff_ms: Optional[Any] = None,
        sportybet_game_id: Optional[str] = None,
        sportradar_event_id: Optional[str] = None,
        api_football_id: Optional[str] = None,
        country: Optional[str] = None
    ) -> CanonicalFixture:
        """
        Resolves or creates a canonical fixture record and links all available provider IDs.
        """
        clean_h = home_team.strip()
        clean_a = away_team.strip()
        
        kickoff_dt = cls.parse_kickoff_datetime(kickoff_ms)
        date_str = kickoff_dt.strftime("%Y%m%d")
        
        # Check if provider ID already exists in DB
        existing_fix_id = None
        if sportybet_game_id:
            mapping = db.query(FixtureProviderMapping).filter(
                FixtureProviderMapping.provider == "SPORTYBET",
                FixtureProviderMapping.provider_game_id == str(sportybet_game_id)
            ).first()
            if mapping:
                existing_fix_id = mapping.fixture_id
                
        if not existing_fix_id and sportradar_event_id:
            mapping = db.query(FixtureProviderMapping).filter(
                FixtureProviderMapping.provider == "SPORTRADAR",
                FixtureProviderMapping.provider_event_id == str(sportradar_event_id)
            ).first()
            if mapping:
                existing_fix_id = mapping.fixture_id

        if not existing_fix_id and api_football_id:
            mapping = db.query(FixtureProviderMapping).filter(
                FixtureProviderMapping.provider == "API_FOOTBALL",
                FixtureProviderMapping.provider_event_id == str(api_football_id)
            ).first()
            if mapping:
                existing_fix_id = mapping.fixture_id

        if existing_fix_id:
            fixture = db.query(CanonicalFixture).filter(CanonicalFixture.id == existing_fix_id).first()
            if fixture:
                cls._ensure_mappings(db, fixture.id, sportybet_game_id, sportradar_event_id, api_football_id)
                return fixture

        # Generate new canonical fixture
        canon_id = cls.generate_canonical_id(clean_h, clean_a, date_str)
        fixture = db.query(CanonicalFixture).filter(CanonicalFixture.id == canon_id).first()
        
        if not fixture:
            fixture = CanonicalFixture(
                id=canon_id,
                home_team=clean_h,
                away_team=clean_a,
                competition=competition,
                country=country,
                kickoff_utc=kickoff_dt,
                status="SCHEDULED",
                home_score=None,
                away_score=None
            )
            db.add(fixture)
            db.flush()

        cls._ensure_mappings(db, fixture.id, sportybet_game_id, sportradar_event_id, api_football_id)
        db.commit()
        return fixture

    @classmethod
    def _ensure_mappings(
        cls,
        db: Session,
        fixture_id: str,
        sportybet_game_id: Optional[str],
        sportradar_event_id: Optional[str],
        api_football_id: Optional[str]
    ):
        if sportybet_game_id:
            exists = db.query(FixtureProviderMapping).filter(
                FixtureProviderMapping.fixture_id == fixture_id,
                FixtureProviderMapping.provider == "SPORTYBET",
                FixtureProviderMapping.provider_game_id == str(sportybet_game_id)
            ).first()
            if not exists:
                db.add(FixtureProviderMapping(
                    fixture_id=fixture_id,
                    provider="SPORTYBET",
                    provider_game_id=str(sportybet_game_id),
                    confidence=1.0
                ))

        if sportradar_event_id:
            exists = db.query(FixtureProviderMapping).filter(
                FixtureProviderMapping.fixture_id == fixture_id,
                FixtureProviderMapping.provider == "SPORTRADAR",
                FixtureProviderMapping.provider_event_id == str(sportradar_event_id)
            ).first()
            if not exists:
                db.add(FixtureProviderMapping(
                    fixture_id=fixture_id,
                    provider="SPORTRADAR",
                    provider_event_id=str(sportradar_event_id),
                    confidence=1.0
                ))

        if api_football_id:
            exists = db.query(FixtureProviderMapping).filter(
                FixtureProviderMapping.fixture_id == fixture_id,
                FixtureProviderMapping.provider == "API_FOOTBALL",
                FixtureProviderMapping.provider_event_id == str(api_football_id)
            ).first()
            if not exists:
                db.add(FixtureProviderMapping(
                    fixture_id=fixture_id,
                    provider="API_FOOTBALL",
                    provider_event_id=str(api_football_id),
                    confidence=1.0
                ))
        db.flush()
