from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from virtual.core.db import get_db
from virtual.research.frequency_analyzer import FrequencyAnalyzer
from virtual.research.sequence_analyzer import SequenceAnalyzer
from virtual.research.odds_analyzer import OddsAnalyzer

router = APIRouter()

@router.get("/frequencies")
def get_league_frequencies(
    league_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Returns empirical outcome distributions, goal expectancy histograms, and market hit rates.
    """
    return FrequencyAnalyzer.analyze_league_frequencies(db, league_id=league_id)

@router.get("/sequences")
def get_sequence_analysis(
    league_id: Optional[int] = Query(None),
    limit: int = Query(200, ge=20, le=1000),
    db: Session = Depends(get_db)
):
    """
    Tests streak dependencies (Chi-Square & Markov Transitions) to guard against Gambler's Fallacy.
    """
    return SequenceAnalyzer.test_over_under_independence(db, league_id=league_id, limit=limit)

@router.get("/odds-calibration")
def get_odds_calibration(db: Session = Depends(get_db)):
    """
    Returns calibration curve comparing Fair Market Implied Probabilities vs Actual Win Rates.
    """
    brackets = OddsAnalyzer.analyze_calibration_brackets(db)
    return {"calibration_brackets": brackets}
