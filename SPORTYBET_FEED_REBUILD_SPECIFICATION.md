# StatIQ SportyBet Feed Ingestion Service Rebuild Specification
**Document Version:** 1.0.0  
**Target:** StatIQ Football Ingestion & Mirroring Architecture  
**Author / Maintained by:** StatIQ Core Engineering  
**Date:** September 26, 2026  

---

## 1. Executive Summary & Objective

This document serves as the authoritative blueprint and safeguard reference for refactoring the StatIQ SportyBet data layer. 

The goal of this rebuild is to transition StatIQ from an **ephemeral in-memory proxy model** (which only fetched a fixed subset of matches and markets on demand) into a **permanent, autonomous SportyBet Feed Ingestion Service** backed by a **local SQLite mirror database**.

SportyBet is established as the sole authoritative source of truth for fixtures, event IDs, market IDs, outcome IDs, and live odds.

---

## 2. Rebuild Breakdown: What We Are Adding, Removing, and Keeping

```
┌────────────────────────────────────────────────────────────────────────┐
│                          REBUILD SCOPE OVERVIEW                        │
├──────────────────────────┬──────────────────────┬──────────────────────┤
│       KEEPING (✅)       │     REMOVING (❌)    │      ADDING (🚀)     │
├──────────────────────────┼──────────────────────┼──────────────────────┤
│ • Validated HTTP headers │ • In-memory _cache   │ • 5 Mirror DB Tables │
│ • Endpoint definitions   │ • Hardcoded leagues  │ • Modulated Package  │
│ • Canonical identity     │ • Fixed page caps    │ • Dynamic Discovery  │
│ • Booking verification   │ • Hardcoded markets  │ • Odds Snapshots     │
│ • AI Pick & Edge logic   │ • Random fallbacks   │ • Tiered Polling     │
│ • Virtual trader system  │ • Frontend scraping  │ • Feed Health Status │
└──────────────────────────┴──────────────────────┴──────────────────────┘
```

---

### A. What We Are KEEPING (✅ No Breaking Changes)

1. **Reverse-Engineered SportyBet API Endpoints**:
   - `https://www.sportybet.com/api/ng/factsCenter/wapConfigurableEventsByOrder`
   - `https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents`
   - `https://www.sportybet.com/api/ng/factsCenter/pcEventDetails` & `/eventDetail`
   - `https://www.sportybet.com/api/ng/factsCenter/h2h/{eventId}`
   - Header spoofing and bypass parameters (`withTwoUpMarket`, `withOneUpMarket`, `sportId: sr:sport:1`).

2. **StatIQ Core Domain & Value Prediction Layer**:
   - The Poisson, Dixon-Coles, Elo rating, and Ensemble prediction engines (`backend/app/models/`).
   - The value bet identification logic, probability calculations, Kelly staking, and edge detection in `backend/app/services/pick_engine.py`.

3. **Booking Verification & Audit Trail**:
   - The `SportyBetVerificationEngine` verification loop and `BookingAuditRecord`.
   - Ticket locking, settlement evaluation, flex cut calculation, and post-match audit tracking.

4. **Canonical Fixture & Identity Mapping**:
   - `canonical_fixtures` and `canonical_fixture_provider_ids` for preserving multi-provider mapping and historical accuracy.

5. **Virtual Football Subsystem**:
   - The entire virtual football engine (`virtual/`, `virtual.db`) remains completely untouched and isolated.

---

### B. What We Are REMOVING (❌ Deprecations & Cleanups)

1. **Ephemeral In-Memory Cache (`_cache` Dict)**:
   - **Reason:** In-memory caching caused data loss upon service restarts and prevented historical backtesting of odds changes.
   - **Action:** Replaced by permanent SQLite mirror tables.

2. **Hardcoded Competition Lists (`TOP_TOURNAMENTS`)**:
   - **Reason:** Restricting discovery to ~22 hardcoded IDs caused StatIQ to miss international breaks, cup matches, lower domestic divisions, and newly scheduled tournaments.
   - **Action:** Discovery will dynamically crawl all categories/tournaments returned by SportyBet.

3. **Fixed Pagination Limits (15 Today Pages, 8 Tomorrow Pages)**:
   - **Reason:** Hardcoded page loops truncated large weekend match boards.
   - **Action:** Implemented dynamic pagination loops that continue until the feed indicates page/cursor exhaustion (`records_received < pageSize` or `total` reached).

4. **Fixed Hardcoded Market Filtering in Ingestion**:
   - **Reason:** Ingestion discarded unfamiliar markets.
   - **Action:** The ingestion layer now stores **all** markets and outcomes generically. Filtering is strictly delegated to the downstream prediction engine.

5. **Fuzzy/Random Fallback Matches in Ticket Generation**:
   - **Reason:** If an event or market lookup failed, fallback logic could pick an arbitrary fixture.
   - **Action:** Strict fail-closed policy: unverified events or markets return `NO_BET` / `VALIDATION_FAILED`.

---

### C. What We Are ADDING (🚀 New Architecture Components)

#### 1. Five (5) Dedicated SportyBet Mirror Database Tables

```sql
-- 1. SportyBet Competitions
CREATE TABLE sportybet_competitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sporty_competition_id VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    country VARCHAR(100),
    category VARCHAR(100),
    status VARCHAR(30) DEFAULT 'ACTIVE',
    raw_payload JSON,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. SportyBet Events
CREATE TABLE sportybet_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sporty_event_id VARCHAR(100) UNIQUE NOT NULL,
    sporty_game_id VARCHAR(50),
    competition_id INTEGER REFERENCES sportybet_competitions(id),
    home_team VARCHAR(150) NOT NULL,
    away_team VARCHAR(150) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    start_time_ms BIGINT NOT NULL,
    status VARCHAR(30) DEFAULT 'SCHEDULED', -- SCHEDULED, LIVE, FINISHED, CANCELLED
    event_state VARCHAR(30) DEFAULT 'NOT_STARTED',
    raw_payload JSON,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. SportyBet Markets
CREATE TABLE sportybet_markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sporty_market_id VARCHAR(50) NOT NULL,
    event_id INTEGER REFERENCES sportybet_events(id) ON DELETE CASCADE,
    market_type VARCHAR(100) NOT NULL,
    market_name VARCHAR(150) NOT NULL,
    line VARCHAR(50),
    specifier VARCHAR(200),
    status VARCHAR(30) DEFAULT 'ACTIVE',
    raw_payload JSON,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, sporty_market_id, specifier)
);

-- 4. SportyBet Market Outcomes
CREATE TABLE sportybet_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id INTEGER REFERENCES sportybet_markets(id) ON DELETE CASCADE,
    sporty_outcome_id VARCHAR(50) NOT NULL,
    label VARCHAR(100) NOT NULL,
    selection VARCHAR(100) NOT NULL,
    odds REAL NOT NULL,
    probability REAL,
    status VARCHAR(30) DEFAULT 'ACTIVE',
    raw_payload JSON,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(market_id, sporty_outcome_id)
);

-- 5. Append-Only Historical Odds Snapshots
CREATE TABLE sportybet_odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER REFERENCES sportybet_events(id) ON DELETE CASCADE,
    market_id INTEGER REFERENCES sportybet_markets(id) ON DELETE CASCADE,
    outcome_id INTEGER REFERENCES sportybet_outcomes(id) ON DELETE CASCADE,
    odds REAL NOT NULL,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_timestamp BIGINT
);
CREATE INDEX idx_odds_snapshot_event_mkt ON sportybet_odds_snapshots(event_id, market_id, captured_at);
```

#### 2. Modular Ingestion Package (`backend/app/integrations/sportybet/`)

```text
backend/app/integrations/sportybet/
├── __init__.py
├── client.py          # HTTP Client, connection pools, retry & rate limit handling
├── discovery.py       # Full-catalogue tree & competition discovery
├── events.py          # Complete event synchronization with exhaustive pagination
├── markets.py         # Dynamic market & outcome parser
├── normalizer.py      # Standardized payload translation & schema validation
├── models.py          # SQLAlchemy mirror database models
├── validators.py      # Pre-ticket submission verification & odds drift checks
└── scheduler.py       # Tiered background synchronization daemon
```

#### 3. Tiered Polling Frequency Engine
* **Catalogue / Competitions**: Discovered every **2–5 minutes**.
* **Upcoming Matches (> 6 hours)**: Refreshed every **2 minutes**.
* **Matches (1–6 hours)**: Refreshed every **30–60 seconds**.
* **Imminent Kickoff (< 1 hour)**: Refreshed every **10–20 seconds**.
* **Immediate (< 5 minutes)**: Verified prior to ticket generation.

#### 4. StatIQ Local Mirror REST API Endpoints
* `GET /api/v1/sportybet/competitions`
* `GET /api/v1/sportybet/events?date=today&competition_id=...`
* `GET /api/v1/sportybet/events/{eventId}`
* `GET /api/v1/sportybet/events/{eventId}/markets`
* `GET /api/v1/sportybet/feed/health` (Sync cycles, error rates, odds updates)

---

## 3. Data Protection & Reversion Safeguards

### Database Safety Guarantees
1. **Zero Impact on Existing MatchIQ Tables**:
   The 5 new mirror tables (`sportybet_*`) operate in the same database (`matchiq.db`) without altering or dropping any existing tables (`fixtures`, `predictions`, `tracked_tickets`, `booking_audit_records`).
2. **Safe Fallback Wrapper**:
   The existing `SportyBetIngestionService` and `SportyBetVerificationEngine` interfaces will be preserved as backward-compatible wrapper facades. If anything fails in the new engine, the legacy direct fetch can be toggled via a single environment flag:
   ```env
   SPORTYBET_MIRROR_MODE=ENABLED   # Set to DISABLED to immediately fall back to legacy proxy
   ```

---

## 4. Acceptance Criteria & Validation Matrix

| # | Validation Check | Pass Condition |
| :--- | :--- | :--- |
| **AC-1** | Multi-Competition Discovery | Discovers all active competitions (domestic, international, tier-2, cups) without manual ID entry. |
| **AC-2** | Full Pagination | Exhausts all available pages until 100% of fixtures are ingested. |
| **AC-3** | Generic Market Parsing | Stores all offered markets and outcome IDs directly from SportyBet. |
| **AC-4** | Odds Drift Tracking | Price changes create new records in `sportybet_odds_snapshots`. |
| **AC-5** | Ticket Isolation | Missing or altered selections trigger `VALIDATION_FAILED` (no random fallbacks). |
| **AC-6** | Zero Data Loss Rollback | Can revert to legacy in-memory pipeline without database drops. |
