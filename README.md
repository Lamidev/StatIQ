# StatIQ — AI Football Prediction & Quantitative Bet Slip Engine

**StatIQ** is a state-of-the-art quantitative intelligence platform for football match predictions, 5-Gate AI accumulator building, and sub-100ms bet slip auditing. Designed with calibrated Elo models, Poisson goal matrices, and overround-stripped bookmaker consensus algorithms.

---

## 🚀 Core Platform Features

1. **Match Fixtures & Live AI Analytics**:
   - Real-time fixtures across Premier League, La Liga, Serie A, Bundesliga, Ligue 1, and UEFA Champions League.
   - Dynamic 1X2 probability meters ($1, X, 2$) calibrated with Dixon-Coles dependency scaling and temperature-smoothed odds margins.

2. **AI Ticket & Rollover Builder (5-Gate Engine)**:
   - **Target Odds Accumulator Builder (2.0x to 1,000.0x+)**: Custom target odds input with automatic leg count calibration.
   - **Safest Multi-Day Rollover Engine**: 3-day (Weekend) and 5-day (UCL Week) compounding rollover strategies with automated 1:00 AM Telegram alerts.
   - **One-Click SportyBet Code Generator**: Generates shareable SportyBet booking codes directly from built tickets.

3. **Ticket Auditor & Re-Editor Engine**:
   - **Sub-100ms Booking Code Decoding**: Decodes raw SportyBet booking codes instantly into structured match selections.
   - **AUDITOR Mode**: Re-engineers 100% of original ticket fixtures into safer high-probability statistical market lines.
   - **SWAP Mode**: Replaces risky/volatile selections with safer top-tier match picks from our live database.
   - **REMOVE Mode**: Prunes low-confidence legs to leave a bulletproof short ticket.

4. **Live Bet Tracker & History**:
   - Real-time match clock and score auto-polling every 15s.
   - Full ticket-level settlement tracking with support for Asian Goal Line / Integer Handicap `VOID` (push) rules.

5. **Historical Backtest Simulator**:
   - Backtest StatIQ strategy performance on real finished seasons (2021 to 2026).

---

## 🛠️ Technology Stack

- **Frontend**: React 18, Vite, Tailwind CSS, Lucide Icons.
- **Backend**: Python 3.11, FastAPI, Asyncio, SQLite / SQLAlchemy.
- **Data Integrations**: Live `football-data.org` API v4, SportyBet Live Booking Decoder API.

---

## ⚙️ Quick Start

### 1. Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 📜 License
MIT License. Developed for quantitative sports betting research and algorithmic ticket optimization.
