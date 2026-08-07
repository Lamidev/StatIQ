# StatIQ — Quantitative System Architecture & Comprehensive Platform Guide

> **StatIQ** is an institutional-grade quantitative sports intelligence platform engineered for football match prediction, 5-Gate AI accumulator building, sub-100ms bet slip auditing, and real-time live match settlement tracking.

---

## 🧬 1. The Quantitative Brains Behind StatIQ

StatIQ does **NOT** blindly trust bookmaker odds or favor home teams by default. Instead, it processes matches through a multi-stage quantitative pipeline that combines structural team ratings, Poisson goal expectancy matrices, and bookmaker vigorish removal algorithms.

```
┌────────────────────────┐
│  Live Fixture Stream   │ (Premier League, La Liga, Serie A, Bundesliga, Ligue 1, UCL)
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Stage 1: Elo Rating    │  ΔE = (Home Elo + 40) - Away Elo
│ & Home Advantage (+40) │  Raw Win Expectancy Calculation
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Stage 2: Poisson Goal  │  Expected Goals (λ, μ) + Dixon-Coles
│ Matrix & Dixon-Coles   │  Low-Scoring Draw Adjustment (0-0, 1-1)
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Stage 3: Temperature   │  Multinomial Temperature Scaling (T = 1.8)
│ Scaling (T = 1.8)      │  Strips overconfidence & aligns win floors
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Stage 4: Overround     │  M = Σ (1 / Odds) - 1
│ Removal Algorithm      │  Strips bookmaker margin to find True Consensus
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Stage 5: Dynamic Away- │  Upgrades risky home/combo picks to safe lines:
│ Favored Line Upgrade   │  • Asian Handicap (+1.5)  • Double Chance (X2)
└────────────────────────┘
```

### Mathematical Formulation of the Engine:

#### 1. Elo Rating Model & Home Advantage (+40 Points)
The structural quality difference $\Delta E$ between Home and Away clubs is computed as:
$$\Delta E = (\text{Elo}_{\text{Home}} + 40) - \text{Elo}_{\text{Away}}$$

The base win expectancy $E_{\text{Home}}$ is given by the standard logistic distribution:
$$E_{\text{Home}} = \frac{1}{1 + 10^{-\Delta E / 400}}$$

#### 2. Poisson Goal Expectancy & Dixon-Coles Correction
Using team attack ($\alpha$) and defense ($\beta$) coefficients, expected goals $\lambda$ (Home) and $\mu$ (Away) are calculated:
$$\lambda = \text{Attack}_{\text{Home}} \times \text{Defense}_{\text{Away}} \times \gamma_{\text{Home}}$$
$$\mu = \text{Attack}_{\text{Away}} \times \text{Defense}_{\text{Home}}$$

The bivariate probability of exact score $P(X = x, Y = y)$ incorporates the Dixon-Coles dependency parameter $\tau_{\rho}(x, y)$ for low-scoring outcomes:
$$P(X=x, Y=y) = \tau_{\rho}(x, y) \frac{\lambda^x e^{-\lambda}}{x!} \frac{\mu^y e^{-\mu}}{y!}$$

#### 3. Bookmaker Vigorish / Overround Removal
When live decimal odds ($O_1, O_X, O_2$) are ingested from SportyBet, the bookmaker overround margin $M$ is stripped to calculate true fair market probabilities ($P_{\text{true}}$):
$$M = \left( \frac{1}{O_1} + \frac{1}{O_X} + \frac{1}{O_2} \right) - 1$$
$$P_{\text{true}}(i) = \frac{1 / O_i}{1 + M}$$

---

## ⚡ 2. Platform Feature Modules

### Module 1: Match Fixtures & Live AI Analytics (`GameweekFixturesTab.jsx`)
- **Vertical Grouped Sidebar**: Browse matches by region and league (England Premier League/Championship, Spain La Liga, Italy Serie A, Germany Bundesliga, France Ligue 1, Europe Champions League, South America, International).
- **"All Games" Aggregator**: Automatically aggregates top upcoming fixtures across all major leagues for any selected gameweek window.
- **Upcoming-Only Stream**: Filters out finished/past matches so you only see active, unplayed games.
- **Visual StatIQ Probability Meter**: Live 1X2 probability bars ($1, X, 2$) showing percentage distribution and Elo strength ratings.

---

### Module 2: AI Ticket & Rollover Builder (`TicketBuilderTab.jsx`)
Powered by the **5-Gate Pick Engine**:

| Gate | Name | Function |
|---|---|---|
| **Gate 1** | **Elo Quality Floor** | Filters out weak/uncompetitive fixtures (Elo gap threshold). |
| **Gate 2** | **Market Volatility Filter** | Eliminates high-variance binary lines (e.g. straight 1X2 derbies). |
| **Gate 3** | **SportyBet Value Edge** | Requires implied market win probability $\ge 78\%$. |
| **Gate 4** | **Market Type Diversity Cap** | Caps any single market type to max 2 occurrences per ticket. |
| **Gate 5** | **Target Odds Calibration** | Dynamically calibrates selection odds to match target odds exactly. |

#### Builder Modes:
1. **Target Odds Accumulator Builder (2.0x to 1,000.0x+)**:
   - Select preset odds (`~2x`, `~5x`, `~10x`, `~20x`, `~50x`, `~100x`, `~500x`, `~1000x`) or type any **Custom Target Odds** (e.g. `2.5`, `7.5`, `15`, `45`, `150`).
2. **Safest Multi-Day Rollover Engine**:
   - **Weekend Rollover (3 Days: Fri $\rightarrow$ Sat $\rightarrow$ Sun)**.
   - **UCL Full Week (5 Days: Fri $\rightarrow$ Wed)**.
   - Includes real-time compounding return calculator and 1:00 AM Telegram alert triggers.

---

### Module 3: Ticket Auditor & Re-Editor (`BetSlipAuditorTab.jsx`)
Takes any raw SportyBet booking code or selection list and re-engineers it using 3 modes:

- **AUDITOR Mode**: Keeps **100% of original fixtures**, but upgrades every pick into its highest-probability market line (`Asian Handicap +1.5`, `Double Chance 1X/X2`, `Over 1.5 Goals`) to hit your target odds.
- **SWAP Mode**: Keeps safe high-confidence legs, but **swaps out risky or unpredictable matches** for safer top-tier picks from live database.
- **REMOVE Mode**: **Prunes and deletes** volatile legs to trim a long ticket down to a bulletproof short ticket.

---

### Module 4: Live Tickets & Bet History Tracker (`BetHistoryTab.jsx`)
- **Summary Metrics Bar**: Tracks both **Acca Tickets Won** (`2 Won / 9 Lost`) and **Individual Games Won** (`73 Games Won` out of 96 total matches = **76% Win Rate**).
- **15s Score Auto-Polling**: Automatically updates match scores, match clock, and leg outcomes every 15 seconds.
- **Asian Line VOID / Push Rule Support**: `Over 2` goals on 2-0 score or integer handicaps evaluate as `VOID` ($1.00\text{x}$ odds return) without marking the ticket lost.

---

### Module 5: Historical Backtest Simulator (`BacktesterTab.jsx`)
- Backtest StatIQ strategy performance on real concluded seasons (2021 to 2026).
- Audit expired booking codes or specific gameweek windows with equity curve visualization.

---

## 🛠️ Technical Stack & Architecture

```
[ Frontend: React 18 + Vite + Tailwind CSS ]
                    │
                    │ HTTP REST / JSON API
                    ▼
[ Backend: FastAPI (Python 3.11) + Asyncio + SQLite ]
         ├── Ingestion: Football-Data.org API v4
         ├── Decoder: SportyBet Live Booking API
         ├── Engine: 5-Gate Pick Engine & Dixon-Coles Model
         └── Tracker: Live Score Poller & VOID/Settlement Evaluator
```

---

## 🚀 Execution Commands

```bash
# Backend Execution
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend Execution
cd frontend
npm install
npm run dev
```

GitHub Repository: [https://github.com/Lamidev/StatIQ.git](https://github.com/Lamidev/StatIQ.git)
