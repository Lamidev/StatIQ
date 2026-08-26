import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from virtual.core.db import Base

class VirtualLeague(Base):
    """
    Tracks distinct virtual tournament leagues (e.g. England Virtual, Spain Virtual).
    """
    __tablename__ = "virtual_leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    country: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    rounds = relationship("VirtualRound", back_populates="league")
    events = relationship("VirtualEvent", back_populates="league")


class VirtualRound(Base):
    """
    A single round/gameweek in a virtual league containing 10 matches.
    """
    __tablename__ = "virtual_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("virtual_leagues.id"), index=True)
    provider_round_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    round_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    scheduled_start: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    betting_deadline: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    
    status: Mapped[str] = mapped_column(String(30), default="UPCOMING", index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    league = relationship("VirtualLeague", back_populates="rounds")
    events = relationship("VirtualEvent", back_populates="round")


class VirtualEvent(Base):
    """
    Canonical Virtual Event.
    STRICT IDENTITY: (provider, provider_event_id).
    """
    __tablename__ = "virtual_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(30), default="sportybet", index=True)
    provider_event_id: Mapped[str] = mapped_column(String(64), index=True)
    provider_game_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    league_id: Mapped[int] = mapped_column(ForeignKey("virtual_leagues.id"), index=True)
    round_id: Mapped[Optional[int]] = mapped_column(ForeignKey("virtual_rounds.id"), nullable=True, index=True)
    
    home_team: Mapped[str] = mapped_column(String(50))
    away_team: Mapped[str] = mapped_column(String(50))
    
    scheduled_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(30), default="UPCOMING", index=True)
    
    source_timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('provider', 'provider_event_id', name='uq_virtual_event_provider_id'),
    )

    league = relationship("VirtualLeague", back_populates="events")
    round = relationship("VirtualRound", back_populates="events")
    odds_snapshots = relationship("VirtualOddsSnapshot", back_populates="event", cascade="all, delete-orphan")
    result = relationship("VirtualResult", back_populates="event", uselist=False, cascade="all, delete-orphan")
    predictions = relationship("VirtualPrediction", back_populates="event")


class VirtualOddsSnapshot(Base):
    """
    Immutable snapshot of market odds for an event.
    """
    __tablename__ = "virtual_odds_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("virtual_events.id"), index=True)
    
    market_type: Mapped[str] = mapped_column(String(50), index=True)
    market_param: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    odds_home: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_draw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_away: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    odds_over: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_under: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    odds_btts_yes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    odds_btts_no: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    observed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow, index=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)

    event = relationship("VirtualEvent", back_populates="odds_snapshots")


class VirtualResult(Base):
    """
    Settlement outcome for a concluded virtual event.
    """
    __tablename__ = "virtual_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("virtual_events.id"), unique=True, index=True)
    
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
    total_goals: Mapped[int] = mapped_column(Integer)
    
    outcome_1x2: Mapped[str] = mapped_column(String(10))
    is_btts: Mapped[bool] = mapped_column(Boolean)
    is_over_1_5: Mapped[bool] = mapped_column(Boolean)
    is_over_2_5: Mapped[bool] = mapped_column(Boolean)
    is_over_3_5: Mapped[bool] = mapped_column(Boolean)
    
    settlement_status: Mapped[str] = mapped_column(String(30), default="SETTLED", index=True)
    settled_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    event = relationship("VirtualEvent", back_populates="result")


class VirtualStrategy(Base):
    """
    Registry of trading strategies and lifecycle states.
    """
    __tablename__ = "virtual_strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    target_market: Mapped[str] = mapped_column(String(50))
    
    status: Mapped[str] = mapped_column(String(30), default="RESEARCH", index=True)
    current_version: Mapped[str] = mapped_column(String(20), default="v1.0.0")
    
    min_sample_size: Mapped[int] = mapped_column(Integer, default=1000)
    expected_win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    min_edge_threshold: Mapped[float] = mapped_column(Float, default=0.03)
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    predictions = relationship("VirtualPrediction", back_populates="strategy")


class VirtualPrediction(Base):
    """
    Audit record for every generated prediction / signal.
    """
    __tablename__ = "virtual_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("virtual_events.id"), index=True)
    strategy_id: Mapped[Optional[int]] = mapped_column(ForeignKey("virtual_strategies.id"), nullable=True, index=True)
    strategy_version: Mapped[str] = mapped_column(String(20), default="v1.0.0")
    
    market_type: Mapped[str] = mapped_column(String(50))
    selection: Mapped[str] = mapped_column(String(50))
    
    odds_at_prediction: Mapped[float] = mapped_column(Float)
    model_probability: Mapped[float] = mapped_column(Float)
    market_probability: Mapped[float] = mapped_column(Float)
    edge: Mapped[float] = mapped_column(Float)
    
    confidence: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    data_quality_score: Mapped[float] = mapped_column(Float, default=1.0)
    sample_size_at_prediction: Mapped[int] = mapped_column(Integer, default=0)
    
    signal: Mapped[str] = mapped_column(String(20), default="SKIP", index=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    status: Mapped[str] = mapped_column(String(30), default="CREATED", index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)

    event = relationship("VirtualEvent", back_populates="predictions")
    strategy = relationship("VirtualStrategy", back_populates="predictions")
    paper_bet = relationship("VirtualPaperBet", back_populates="prediction", uselist=False)


class VirtualPaperBet(Base):
    """
    Simulated trade execution record.
    """
    __tablename__ = "virtual_paper_bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("virtual_predictions.id"), unique=True, index=True)
    
    stake: Mapped[float] = mapped_column(Float)
    odds: Mapped[float] = mapped_column(Float)
    potential_return: Mapped[float] = mapped_column(Float)
    
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    profit_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    placed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    settled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    prediction = relationship("VirtualPrediction", back_populates="paper_bet")


class VirtualBankroll(Base):
    """
    Bankroll balance ledger snapshots.
    """
    __tablename__ = "virtual_bankroll"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(20), default="PAPER", index=True)
    
    starting_balance: Mapped[float] = mapped_column(Float)
    current_balance: Mapped[float] = mapped_column(Float)
    available_balance: Mapped[float] = mapped_column(Float)
    total_exposure: Mapped[float] = mapped_column(Float, default=0.0)
    
    total_bets: Mapped[int] = mapped_column(Integer, default=0)
    won_bets: Mapped[int] = mapped_column(Integer, default=0)
    lost_bets: Mapped[int] = mapped_column(Integer, default=0)
    
    daily_profit_loss: Mapped[float] = mapped_column(Float, default=0.0)
    cumulative_roi: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    consecutive_losses: Mapped[int] = mapped_column(Integer, default=0)
    
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)


class VirtualAgentLog(Base):
    """
    Structured audit event log for the virtual agent pipeline.
    """
    __tablename__ = "virtual_agent_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    worker_name: Mapped[str] = mapped_column(String(50), index=True)
    level: Mapped[str] = mapped_column(String(20), default="INFO")
    event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow, index=True)


class VirtualFrontTestSlip(Base):
    """
    Tracks automated 2-odds front-testing tickets dispatched for live validation.
    """
    __tablename__ = "virtual_fronttest_slips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    booking_code: Mapped[str] = mapped_column(String(20), index=True)
    league_name: Mapped[str] = mapped_column(String(100), index=True)  # e.g., "England Virtual", "Master Multi-League"
    round_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    target_odds: Mapped[float] = mapped_column(Float, default=2.0)
    actual_odds: Mapped[float] = mapped_column(Float)
    num_games: Mapped[int] = mapped_column(Integer)
    stake_amount: Mapped[float] = mapped_column(Float, default=1000.0)
    potential_return: Mapped[float] = mapped_column(Float)

    selections: Mapped[Any] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)  # PENDING, WON, LOST, VOID
    profit_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    telegram_dispatched: Mapped[bool] = mapped_column(Boolean, default=False)
    kickoff_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    settled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class VirtualMatchHistory(Base):
    """
    Persistent repository of concluded virtual match outcomes across all 6 leagues.
    Powers rolling team goal averages, 5-game form ratings, and H2H statistical modeling.
    """
    __tablename__ = "virtual_match_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    league_name: Mapped[str] = mapped_column(String(50), index=True)
    home_team: Mapped[str] = mapped_column(String(50), index=True)
    away_team: Mapped[str] = mapped_column(String(50), index=True)
    
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
    total_goals: Mapped[int] = mapped_column(Integer)
    
    is_over_15: Mapped[bool] = mapped_column(Boolean, default=False)
    is_over_25: Mapped[bool] = mapped_column(Boolean, default=False)
    result_1x2: Mapped[str] = mapped_column(String(10)) # '1', 'X', '2'
    
    kickoff_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=datetime.datetime.utcnow)



