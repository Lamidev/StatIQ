# MatchIQ — System Architecture & Engineering Documentation

**Project**: MatchIQ — AI-Assisted Football Prediction & Intelligence Platform  
**Repository Location**: `c:\Users\user\Desktop\My-Projects\Active-projects\matchiq`  
**Current Milestone**: **Phases 1–13 Backend Completed + Google AI Studio Gemini Service + React Frontend Dashboard Operational**.

---

## 1. System Purpose & 5-Layer Architecture Philosophy

MatchIQ is an advanced quantitative football prediction platform designed to calculate **market-independent probability distributions** ($P_{\text{Home}}, P_{\text{Draw}}, P_{\text{Away}}, P_{\text{Over}}, P_{\text{BTTS}}$) across multiple markets using zero-lookahead temporal feature engineering, calibrated statistical models, machine learning, weighted ensembles, and natural language AI intelligence.

### **5-Layer Architecture Separation**

```
┌─────────────────────────────────────────────┐
│             1. PROBABILITY INTELLIGENCE     │
│ Ingestion → Features → Models → Calibration │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│             2. MARKET INTELLIGENCE          │
│ Odds → Implied Probability → Edge → EV      │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│            3. SELECTION INTELLIGENCE        │
│ Scenario Builder → External Code Audit      │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│            4. PROVIDER ABSTRACTION          │
│ Canonical Mapping → Provider Capabilities   │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│             5. RELIABILITY LAYER            │
│ Match Reconciliation → Performance Ledger   │
│ Drift Monitoring → Pipeline Health Check    │
└─────────────────────────────────────────────┘
```

---

## 2. System Maturity Assessment Matrix

| Area | Status | Assessment |
| :--- | :--- | :--- |
| **Historical Model Validation** | ✅ | **Strongly Validated** (2023–2025 OOS, 7,010 matches: 49.84% Acc, 0.6038 Brier, 1.0115 Log Loss, 0.0110 ECE) |
| **Software Implementation & Testing** | ✅ | **Phases 1–13 & Gemini AI Service Completed** (All engines, adapters, AI service, and unit test suites passing) |
| **Frontend Web Application** | ✅ | **Completed** (React + Tailwind v4 + Lucide dark-mode dashboard built in `frontend/`) |
| **Real-World Live Operational Validation** | 🟡 | **Accumulating Evidence** (2026 live pre-kickoff predictions progressive reconciliation as matches conclude) |

---

## 3. Google AI Studio (Gemini 1.5/2.0 API) Service

MatchIQ integrates Google AI Studio Gemini API (`GEMINI_API_KEY`) as MatchIQ's **Read-Only AI Analyst & Match Narrator**:

- **Strict Boundary Rule**: Gemini **never** calculates or modifies quantitative probabilities ($P_{\text{Home}}, P_{\text{Draw}}, P_{\text{Away}}$). It ingests model numbers as read-only data.
- **REST Endpoints** (`/api/v1/ai/`):
  - `POST /explain-match`: Generates natural language tactical match previews.
  - `POST /audit-slip`: Generates natural language bet slip risk audit reports.
  - `POST /chat`: Interactive "Ask MatchIQ" AI assistant.

---

## 4. Frontend Web Dashboard (`frontend/`)

- Built with Vite, React, Tailwind CSS v4, Lucide React icons, and glassmorphic UI elements.
- **Tabs**:
  1. ⚽ **Live Predictions**: Upcoming 2026 pre-kickoff predictions with probability meters and expected goals.
  2. 💎 **Value Bets (Edge & EV)**: +EV value bet finder with model edge %, implied odds, and filter sliders.
  3. 🎯 **Target Odds Builder**: Bounded beam search multi-leg ticket builder under target odds (~3.0, ~5.0, ~10.0, ~20.0) with **1-click SportyBet booking code generation**.
  4. 🔍 **Bet Slip Auditor**: Paste any SportyBet or external booking code (e.g., `BC7F49A`) for instant weakness classification (`VERY_STRONG`, `STRONG`, `MODERATE`, `WEAK`) and AI replacement options.
  5. 🧪 **Walk-Forward Backtester**: Interactive OOS time-travel backtesting simulator for past seasons (e.g., 2024 Premier League).
  6. 📊 **System Reliability**: Phase 13 pipeline health audit, rolling 30/90/180-day drift metrics, and 1-click match outcome reconciliation trigger.

---

## 5. Developer Setup & Commands

```bash
# Run FastAPI Backend Web Server
uv run uvicorn app.main:app --reload

# Launch React Frontend Development Server
cd frontend
npm run dev

# Run Production Build Test
cd frontend
npm run build
```
