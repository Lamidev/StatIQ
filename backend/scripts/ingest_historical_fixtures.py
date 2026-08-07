import asyncio
import datetime
import logging
from pathlib import Path
import sys
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select
from app.core.config import settings
from app.db.session import SessionLocal, init_db

from app.db.models import Competition, Season, Team, Fixture, RawProviderData, DataSyncRun
from app.ingestion.football_data_client import FootballDataClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ingest_historical")

ACCESSIBLE_COMPETITIONS = [
    {"code": "PL", "name": "Premier League", "country": "England", "type": "DOMESTIC_LEAGUE"},
    {"code": "PD", "name": "La Liga", "country": "Spain", "type": "DOMESTIC_LEAGUE"},
    {"code": "SA", "name": "Serie A", "country": "Italy", "type": "DOMESTIC_LEAGUE"},
    {"code": "BL1", "name": "Bundesliga", "country": "Germany", "type": "DOMESTIC_LEAGUE"},
    {"code": "FL1", "name": "Ligue 1", "country": "France", "type": "DOMESTIC_LEAGUE"},
    {"code": "DED", "name": "Eredivisie", "country": "Netherlands", "type": "DOMESTIC_LEAGUE"},
    {"code": "PPL", "name": "Primeira Liga", "country": "Portugal", "type": "DOMESTIC_LEAGUE"},
    {"code": "CL", "name": "Champions League", "country": "UEFA", "type": "UEFA_COMPETITION"},
]

RESTRICTED_COMPETITIONS = [
    {"code": "EL", "name": "Europa League", "country": "UEFA", "type": "UEFA_COMPETITION"},
    {"code": "KL", "name": "Conference League", "country": "UEFA", "type": "UEFA_COMPETITION"},
]

# Configurable training window (Modern historical period: e.g., 2021 to 2025)
DEFAULT_SEASONS_WINDOW = ["2021", "2022", "2023", "2024", "2025"]

def sync_competitions(session):
    logger.info("Initializing Competitions table...")
    for comp_data in ACCESSIBLE_COMPETITIONS:
        stmt = select(Competition).where(Competition.code == comp_data["code"])
        res = session.execute(stmt)
        comp = res.scalar_one_or_none()
        if not comp:
            comp = Competition(
                code=comp_data["code"],
                name=comp_data["name"],
                country=comp_data["country"],
                type=comp_data["type"],
                is_available=True
            )
            session.add(comp)

    for comp_data in RESTRICTED_COMPETITIONS:
        stmt = select(Competition).where(Competition.code == comp_data["code"])
        res = session.execute(stmt)
        comp = res.scalar_one_or_none()
        if not comp:
            comp = Competition(
                code=comp_data["code"],
                name=comp_data["name"],
                country=comp_data["country"],
                type=comp_data["type"],
                is_available=False
            )
            session.add(comp)

    session.commit()
    logger.info("Competitions table initialized.")

def sync_team(session, team_data: dict) -> Team:
    ext_id = team_data["id"]
    stmt = select(Team).where(Team.provider_external_id == ext_id)
    res = session.execute(stmt)
    team = res.scalar_one_or_none()

    if not team:
        team = Team(
            provider_external_id=ext_id,
            name=team_data.get("name") or f"Team_{ext_id}",
            short_name=team_data.get("shortName"),
            tla=team_data.get("tla"),
            crest_url=team_data.get("crest")
        )
        session.add(team)
        session.flush()
    return team

def sync_season(session, comp_id: int, season_year: str) -> Season:
    stmt = select(Season).where(Season.competition_id == comp_id, Season.name == season_year)
    res = session.execute(stmt)
    season = res.scalar_one_or_none()

    if not season:
        season = Season(
            competition_id=comp_id,
            name=season_year,
            is_current=(season_year == "2025" or season_year == "2026")
        )
        session.add(season)
        session.flush()
    return season

async def run_historical_ingestion(seasons: List[str] = DEFAULT_SEASONS_WINDOW):
    init_db()
    client = FootballDataClient()

    with SessionLocal() as session:
        sync_competitions(session)

        for comp_info in ACCESSIBLE_COMPETITIONS:
            code = comp_info["code"]
            logger.info(f"========== Ingesting {comp_info['name']} ({code}) ==========")

            stmt = select(Competition).where(Competition.code == code)
            res = session.execute(stmt)
            comp = res.scalar_one()

            for season_year in seasons:
                logger.info(f"Fetching {code} season {season_year} matches...")
                sync_run = DataSyncRun(
                    endpoint=f"competitions/{code}/matches?season={season_year}",
                    competition_code=code,
                    season_name=season_year
                )
                session.add(sync_run)
                session.flush()

                matches_payload = await client.get(f"competitions/{code}/matches", params={"season": season_year})

                if not matches_payload or "matches" not in matches_payload:
                    logger.warning(f"No matches returned for {code} season {season_year}")
                    sync_run.status = "FAILED"
                    session.commit()
                    continue

                # Store Raw Response
                raw_entry = RawProviderData(
                    endpoint=f"competitions/{code}/matches",
                    provider_record_id=f"{code}_{season_year}",
                    payload=matches_payload
                )
                session.add(raw_entry)

                season_obj = sync_season(session, comp.id, season_year)
                matches_list = matches_payload.get("matches", [])
                created_count = 0

                for m in matches_list:
                    match_ext_id = m["id"]
                    stmt_fix = select(Fixture).where(Fixture.provider_external_id == match_ext_id)
                    res_fix = session.execute(stmt_fix)
                    fixture = res_fix.scalar_one_or_none()

                    home_team = sync_team(session, m["homeTeam"])
                    away_team = sync_team(session, m["awayTeam"])


                    kickoff_str = m.get("utcDate")
                    kickoff_dt = datetime.datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")) if kickoff_str else datetime.datetime.utcnow()

                    score_info = m.get("score", {})
                    ft_score = score_info.get("fullTime", {})
                    ht_score = score_info.get("halfTime", {})

                    home_ft = ft_score.get("home")
                    away_ft = ft_score.get("away")
                    home_ht = ht_score.get("home")
                    away_ht = ht_score.get("away")

                    winner = score_info.get("winner")

                    if not fixture:
                        fixture = Fixture(
                            provider_external_id=match_ext_id,
                            season_id=season_obj.id,
                            competition_code=code,
                            matchday=m.get("matchday"),
                            stage=m.get("stage"),
                            kickoff_datetime=kickoff_dt,
                            home_team_id=home_team.id,
                            away_team_id=away_team.id,
                            status=m.get("status", "FINISHED"),
                            home_score=home_ft,
                            away_score=away_ft,
                            home_ht_score=home_ht,
                            away_ht_score=away_ht,
                            winner=winner
                        )
                        session.add(fixture)
                        created_count += 1
                    else:
                        # Update scores if completed
                        fixture.home_score = home_ft
                        fixture.away_score = away_ft
                        fixture.home_ht_score = home_ht
                        fixture.away_ht_score = away_ht
                        fixture.winner = winner
                        fixture.status = m.get("status", fixture.status)

                sync_run.records_received = len(matches_list)
                sync_run.records_created = created_count
                sync_run.status = "COMPLETED"
                sync_run.completed_at = datetime.datetime.utcnow()
                session.commit()


                logger.info(f"✅ Ingested {created_count} new fixtures for {code} ({season_year})")

    logger.info("🎉 Historical Data Ingestion Complete!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MatchIQ Football-Data.org Historical Data Ingestion")
    parser.add_argument("--seasons", nargs="+", help="Specific season years to ingest, e.g. --seasons 2022 2023 2024 2025")
    parser.add_argument("--start-year", type=int, help="Start year for season range, e.g. 2018")
    parser.add_argument("--end-year", type=int, help="End year for season range, e.g. 2025")
    args = parser.parse_args()

    target_seasons = DEFAULT_SEASONS_WINDOW
    if args.seasons:
        target_seasons = [str(s) for s in args.seasons]
    elif args.start_year and args.end_year:
        target_seasons = [str(y) for y in range(args.start_year, args.end_year + 1)]

    logger.info(f"Targeting ingestion for seasons: {target_seasons}")
    asyncio.run(run_historical_ingestion(seasons=target_seasons))

