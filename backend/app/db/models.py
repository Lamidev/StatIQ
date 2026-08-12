import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON

from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base

class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    country: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    type: Mapped[str] = mapped_column(String(30), default="DOMESTIC_LEAGUE")
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    seasons = relationship("Season", back_populates="competition")

class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"), index=True)
    name: Mapped[str] = mapped_column(String(20))  # e.g., "2024" or "2024/2025"
    start_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    competition = relationship("Competition", back_populates="seasons")
    fixtures = relationship("Fixture", back_populates="season")

class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_external_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    tla: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    crest_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class Fixture(Base):
    __tablename__ = "fixtures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_external_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"), index=True)
    competition_code: Mapped[str] = mapped_column(String(30), index=True)
    matchday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stage: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    kickoff_datetime: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED", index=True)
    
    # Results
    home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    home_ht_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_ht_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    winner: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # HOME_TEAM, AWAY_TEAM, DRAW

    effective_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    retrieved_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    season = relationship("Season", back_populates="fixtures")

class RawProviderData(Base):
    __tablename__ = "raw_provider_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(String(50), default="FOOTBALL_DATA_ORG")
    endpoint: Mapped[str] = mapped_column(String(100))
    provider_record_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    retrieved_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class DataSyncRun(Base):
    __tablename__ = "data_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(String(50), default="FOOTBALL_DATA_ORG")
    endpoint: Mapped[str] = mapped_column(String(100))
    competition_code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    season_name: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")

class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    as_of_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    feature_vector: Mapped[dict] = mapped_column(JSON)
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    model_type: Mapped[str] = mapped_column(String(30))  # ELO, POISSON, DIXON_COLES, XGBOOST, ENSEMBLE
    hyperparameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    brier_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    log_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(50), index=True)  # ELO, POISSON, DIXON_COLES
    model_version_code: Mapped[str] = mapped_column(String(30), default="v1.0.0")
    model_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("model_versions.id"), nullable=True)
    feature_snapshot_id: Mapped[Optional[int]] = mapped_column(ForeignKey("feature_snapshots.id"), nullable=True)
    prediction_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    
    # 1X2 Model Probabilities
    prob_home: Mapped[float] = mapped_column(Float)
    prob_draw: Mapped[float] = mapped_column(Float)
    prob_away: Mapped[float] = mapped_column(Float)
    
    # Over/Under Probabilities
    prob_over_0_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prob_over_1_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prob_over_2_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prob_over_3_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    prob_under_0_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prob_under_1_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prob_under_2_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prob_under_3_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Both Teams to Score (BTTS)
    prob_btts_yes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prob_btts_no: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Expected Goals
    expected_home_goals: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_away_goals: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Actual Result Audit
    actual_outcome: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # HOME_TEAM, DRAW, AWAY_TEAM
    actual_home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    brier_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    log_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

class LivePredictionLedger(Base):
    """
    Phase 8 Live Prediction Shadow Ledger.
    Strictly persists real-time forward predictions for upcoming 2026+ fixtures prior to kickoff.
    Completely isolated from historical 2023-2025 backtest records.
    """
    __tablename__ = "live_prediction_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True, unique=True)
    
    # Versioning Audit
    model_name: Mapped[str] = mapped_column(String(50), default="Weighted_Ensemble")
    model_version: Mapped[str] = mapped_column(String(30), default="v1.0.0")
    feature_version: Mapped[str] = mapped_column(String(30), default="v1.0.0")
    calibration_version: Mapped[str] = mapped_column(String(30), default="temp_scale_v1")
    feature_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prediction_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    # Probabilities
    prob_home: Mapped[float] = mapped_column(Float)
    prob_draw: Mapped[float] = mapped_column(Float)
    prob_away: Mapped[float] = mapped_column(Float)

    prob_over_1_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prob_over_2_5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prob_btts_yes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    expected_home_goals: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_away_goals: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status: PENDING, COMPLETED, CANCELLED
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)

    # Post-Kickoff Resolution Audit
    actual_home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_result: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # HOME_TEAM, DRAW, AWAY_TEAM
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    brier_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    log_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class MarketOdds(Base):
    """
    Market Odds Entity.
    Stores real-world decimal odds from external data feeds.
    Strictly decoupled from prediction engine probabilities.
    """
    __tablename__ = "market_odds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    bookmaker: Mapped[str] = mapped_column(String(50), index=True)  # e.g. Bet365, Pinnacle, SportyBet, Consensus
    market: Mapped[str] = mapped_column(String(30), index=True)     # 1X2, OVER_UNDER_2_5, BTTS
    selection: Mapped[str] = mapped_column(String(30), index=True)  # HOME, DRAW, AWAY, OVER, UNDER, YES, NO
    odds: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class MarketShadowLedger(Base):
    """
    Phase 8.5 / Phase 9 Market Shadow Ledger.
    Tracks model value bets: Model Probability vs Implied Bookmaker Odds, Model Edge, EV, and P&L.
    """
    __tablename__ = "market_shadow_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    live_prediction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("live_prediction_ledger.id"), nullable=True)

    market: Mapped[str] = mapped_column(String(30))      # 1X2, OVER_UNDER_2_5, BTTS
    selection: Mapped[str] = mapped_column(String(30))   # HOME, DRAW, AWAY, OVER, UNDER, YES, NO
    bookmaker: Mapped[str] = mapped_column(String(50))   # e.g. Bet365, Pinnacle, Consensus
    odds: Mapped[float] = mapped_column(Float)          # Decimal odds e.g. 1.80

    model_probability: Mapped[float] = mapped_column(Float)      # e.g. 0.65 (65%)
    implied_probability: Mapped[float] = mapped_column(Float)    # e.g. 1 / 1.80 = 0.5556 (55.56%)
    model_edge: Mapped[float] = mapped_column(Float)             # e.g. 0.65 - 0.5556 = +0.0944 (+9.44%)
    expected_value: Mapped[float] = mapped_column(Float)         # e.g. (0.65 * 1.80) - 1 = +0.17 (+17% EV)

    # Status: PENDING, WIN, LOSS, CANCELLED
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    profit_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # e.g. +0.80 or -1.00
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

# --- PHASE 10: SCENARIO BUILDER DOMAIN MODELS ---

class ScenarioAnalysis(Base):
    """
    Phase 10 Target Scenario Analysis Entity.
    Stores multi-match candidate scenarios generated under strict model probability preservation.
    """
    __tablename__ = "scenario_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[str] = mapped_column(String(50), index=True, unique=True)
    model_version: Mapped[str] = mapped_column(String(50), default="Weighted_Ensemble_v1.0.0")
    request_parameters: Mapped[Dict[str, Any]] = mapped_column(JSON)
    scenario_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class ScenarioAnalysisItem(Base):
    """
    Phase 10 Scenario Item / Candidate Selection.
    """
    __tablename__ = "scenario_analysis_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_analysis_id: Mapped[int] = mapped_column(ForeignKey("scenario_analysis.id"), index=True)
    scenario_item_group_id: Mapped[str] = mapped_column(String(50), index=True)
    fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    prediction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("live_prediction_ledger.id"), nullable=True)
    
    market_type: Mapped[str] = mapped_column(String(30))       # 1X2, OVER_UNDER, BTTS
    market_line: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # e.g. 2.5
    selection: Mapped[str] = mapped_column(String(30))        # HOME, DRAW, AWAY, OVER, UNDER, YES, NO
    
    model_probability: Mapped[float] = mapped_column(Float)
    implied_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_edge: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

# --- PHASE 11: EXTERNAL CODE ANALYZER DOMAIN MODELS ---

class ExternalCodeAnalysis(Base):
    """
    Phase 11 External Booking Code Audit Entity.
    """
    __tablename__ = "external_code_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    raw_code: Mapped[str] = mapped_column(String(100), index=True)
    parse_status: Mapped[str] = mapped_column(String(30))  # PARSED, PARTIALLY_PARSED, UNSUPPORTED, INVALID
    total_selections: Mapped[int] = mapped_column(Integer, default=0)
    resolved_count: Mapped[int] = mapped_column(Integer, default=0)
    unresolved_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class ExternalCodeItem(Base):
    """
    Phase 11 Individual Decoded & Analyzed Selection.
    """
    __tablename__ = "external_code_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("external_code_analysis.id"), index=True)
    matchiq_fixture_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fixtures.id"), nullable=True)
    
    external_fixture_name: Mapped[str] = mapped_column(String(100))
    external_market_name: Mapped[str] = mapped_column(String(50))
    external_selection: Mapped[str] = mapped_column(String(50))
    external_odds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    resolution_status: Mapped[str] = mapped_column(String(30))  # MATCHED, AMBIGUOUS, UNRESOLVED
    matchiq_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    classification: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # VERY_STRONG, STRONG, MODERATE, WEAK, INSUFFICIENT_DATA, UNSUPPORTED

# --- PHASE 12: PROVIDER MARKET ADAPTER DOMAIN MODELS ---

class ProviderMarketMapping(Base):
    """
    Phase 12 Provider-Specific Market & Selection Mapping Entity.
    Maps canonical MatchIQ market keys (e.g. OVER_2_5) to provider-specific names.
    """
    __tablename__ = "provider_market_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    provider_market_id: Mapped[str] = mapped_column(String(100))
    provider_market_name: Mapped[str] = mapped_column(String(100))

    matchiq_market_type: Mapped[str] = mapped_column(String(30))  # 1X2, OVER_UNDER, BTTS
    matchiq_market_line: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    matchiq_selection: Mapped[str] = mapped_column(String(30))   # HOME, DRAW, AWAY, OVER, UNDER, YES, NO
    
    mapping_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

class ProviderFixtureMapping(Base):
    """
    Phase 12 Provider-Specific Fixture ID Mapping Entity.
    """
    __tablename__ = "provider_fixture_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(50), index=True)
    provider_fixture_id: Mapped[str] = mapped_column(String(100), index=True)
    matchiq_fixture_id: Mapped[int] = mapped_column(ForeignKey("fixtures.id"), index=True)
    
    provider_home_team: Mapped[str] = mapped_column(String(100))
    provider_away_team: Mapped[str] = mapped_column(String(100))
    kickoff_datetime: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    mapping_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

class TrackedTicket(Base):
    """
    Tracked Staked Ticket Entity.
    Stores tickets locked for tracking and evaluation in SQLite database.
    """
    __tablename__ = "tracked_tickets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    code: Mapped[str] = mapped_column(String(50), index=True, default="CUSTOM")
    mode: Mapped[str] = mapped_column(String(30), default="SWAP")
    target_odds: Mapped[float] = mapped_column(Float, default=1.5)
    total_odds: Mapped[float] = mapped_column(Float, default=1.5)
    stake: Mapped[float] = mapped_column(Float, default=100.0)
    flex_cut: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    potential_win: Mapped[float] = mapped_column(Float, default=150.0)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING", index=True)
    created_at: Mapped[str] = mapped_column(String(30))
    locked_at_unix: Mapped[int] = mapped_column(Integer, index=True)
    selections: Mapped[list] = mapped_column(JSON, default=list)
    settled_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    flex_status_text: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    allowed_losses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    loss_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_live: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    stale: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class BookingAuditRecord(Base):
    """
    Phase 14 Booking Audit Record Entity.
    Stores comprehensive audit trail for every booking creation and verification attempt.
    """
    __tablename__ = "booking_audit_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    statiq_ticket_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="SPORTYBET", index=True)
    region: Mapped[str] = mapped_column(String(10), default="NG", index=True)

    requested_selections: Mapped[dict] = mapped_column(JSON)
    resolved_selections: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    returned_selections: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    booking_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    share_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    verification_status: Mapped[str] = mapped_column(String(30), default="CREATED", index=True)
    verification_errors: Mapped[list] = mapped_column(JSON, default=list)

    total_odds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    selection_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)





