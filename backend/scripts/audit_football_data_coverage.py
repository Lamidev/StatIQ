import asyncio
import json
import logging
from pathlib import Path
import sys

# Ensure backend directory is in python path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.ingestion.football_data_client import FootballDataClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("audit_coverage")

TARGET_COMPETITIONS = [
    {"code": "PL", "name": "Premier League", "country": "England"},
    {"code": "PD", "name": "La Liga", "country": "Spain"},
    {"code": "SA", "name": "Serie A", "country": "Italy"},
    {"code": "BL1", "name": "Bundesliga", "country": "Germany"},
    {"code": "FL1", "name": "Ligue 1", "country": "France"},
    {"code": "DED", "name": "Eredivisie", "country": "Netherlands"},
    {"code": "PPL", "name": "Primeira Liga", "country": "Portugal"},
    {"code": "CL", "name": "Champions League", "country": "UEFA"},
    {"code": "EL", "name": "Europa League", "country": "UEFA"},
    {"code": "KL", "name": "Conference League", "country": "UEFA"},
]

async def run_coverage_audit():
    logger.info("Starting Football-Data.org API Coverage Audit (Task 1)...")
    client = FootballDataClient()

    # 1. Test Overall Competitions List Endpoint
    logger.info("Fetching accessible competitions list via /v4/competitions...")
    all_comps_res = await client.get("competitions")
    available_codes = set()
    
    if "competitions" in all_comps_res:
        for c in all_comps_res["competitions"]:
            available_codes.add(c.get("code"))
        logger.info(f"Total competitions accessible on API key: {len(available_codes)}")

    report = {
        "summary": {
            "total_target_competitions": len(TARGET_COMPETITIONS),
            "accessible_count": 0,
            "restricted_count": 0,
        },
        "competitions": []
    }

    # 2. Audit Each Target Competition
    for comp in TARGET_COMPETITIONS:
        code = comp["code"]
        name = comp["name"]
        logger.info(f"--- Auditing {name} ({code}) ---")

        comp_detail = await client.get(f"competitions/{code}")

        if "error" in comp_detail and comp_detail.get("status_code") == 403:
            logger.warning(f"❌ {name} ({code}): RESTRICTED (403 Forbidden on Free Tier)")
            report["summary"]["restricted_count"] += 1
            report["competitions"].append({
                "code": code,
                "name": name,
                "country": comp["country"],
                "accessible": False,
                "reason": "403 Forbidden (Requires paid subscription plan)"
            })
            continue

        if "id" not in comp_detail:
            logger.warning(f"⚠️ {name} ({code}): Unable to fetch details (Response: {comp_detail})")
            report["competitions"].append({
                "code": code,
                "name": name,
                "country": comp["country"],
                "accessible": False,
                "reason": "Unexpected API response"
            })
            continue

        report["summary"]["accessible_count"] += 1
        seasons_info = comp_detail.get("seasons", [])
        season_years = [s.get("startDate")[:4] for s in seasons_info if s.get("startDate")]
        current_season = comp_detail.get("currentSeason", {}).get("startDate", "")[:4]

        # 3. Test Fixture/Match Fetch for Current Season
        sample_season = current_season or "2025"
        matches_res = await client.get(f"competitions/{code}/matches", params={"season": sample_season})
        matches = matches_res.get("matches", [])
        
        # Discover available fields from sample match
        sample_fields = []
        if matches:
            first_match = matches[0]
            sample_fields = list(first_match.keys())
            score_fields = list(first_match.get("score", {}).keys())
            logger.info(f"Sample match fields returned: {sample_fields}")
            logger.info(f"Score breakdown fields: {score_fields}")

        comp_report = {
            "code": code,
            "name": name,
            "country": comp["country"],
            "accessible": True,
            "id": comp_detail.get("id"),
            "current_season": current_season,
            "total_seasons_available": len(seasons_info),
            "seasons_range": f"{min(season_years) if season_years else 'N/A'} - {max(season_years) if season_years else 'N/A'}",
            "sample_season_tested": sample_season,
            "sample_season_fixture_count": len(matches),
            "available_fields": sample_fields,
            "has_halftime_scores": "halfTime" in matches[0].get("score", {}) if matches else False,
            "has_fulltime_scores": "fullTime" in matches[0].get("score", {}) if matches else False,
            "has_xg": "xg" in matches[0] if matches else False,
            "has_lineups": "lineups" in matches[0] if matches else False
        }

        report["competitions"].append(comp_report)
        logger.info(f"✅ {name} ({code}): ACCESSIBLE. {len(seasons_info)} seasons. Sample season ({sample_season}) has {len(matches)} fixtures.")

    # 4. Save Audit Report
    report_path = BASE_DIR.parent / "data_coverage_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Data Coverage Audit Complete! Report saved to {report_path}")

    # Print Summary Matrix
    print("\n" + "="*80)
    print("MATCHIQ — FOOTBALL-DATA.ORG FREE TIER DATA COVERAGE REPORT (TASK 1)")
    print("="*80)
    print(f"Total Target Competitions Tested: {report['summary']['total_target_competitions']}")
    print(f"Accessible on Free Tier: {report['summary']['accessible_count']}")
    print(f"Restricted (Paid Only): {report['summary']['restricted_count']}")
    print("-" * 80)
    print(f"{'Code':<6} | {'Competition':<22} | {'Status':<12} | {'Seasons Range':<15} | {'Fixtures'}")
    print("-" * 80)
    for c in report["competitions"]:
        status = "ACCESSIBLE" if c.get("accessible") else "RESTRICTED"
        seasons = c.get("seasons_range", "N/A")
        fixtures = f"{c.get('sample_season_fixture_count', 0)} matches" if c.get("accessible") else "N/A"
        print(f"{c['code']:<6} | {c['name']:<22} | {status:<12} | {seasons:<15} | {fixtures}")
    print("="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(run_coverage_audit())
