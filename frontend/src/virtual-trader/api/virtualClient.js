/**
 * Dedicated API Client for Standalone StatIQ Virtual Trader Service.
 * Connects to the standalone virtual microservice (Port 8001).
 */

const VIRTUAL_API_BASE =
  import.meta.env.VITE_VIRTUAL_API_URL ||
  (typeof window !== "undefined" && window.location.hostname === "localhost"
    ? "http://localhost:8000"
    : "");


export async function fetchVirtualDashboard() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/dashboard`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchVirtualDashboard error:", err);
    return null;
  }
}

export async function fetchVirtualEvents(limit = 50, leagueId = null) {
  try {
    let url = `${VIRTUAL_API_BASE}/api/v1/virtual-trader/events?limit=${limit}`;
    if (leagueId) url += `&league_id=${leagueId}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchVirtualEvents error:", err);
    return { count: 0, events: [] };
  }
}

export async function fetchVirtualLeagues() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/leagues`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchVirtualLeagues error:", err);
    return { leagues: [] };
  }
}

export async function fetchLeagueFrequencies(leagueId = null) {
  try {
    let url = `${VIRTUAL_API_BASE}/api/v1/virtual-trader/research/frequencies`;
    if (leagueId) url += `?league_id=${leagueId}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchLeagueFrequencies error:", err);
    return null;
  }
}

export async function fetchSequenceAnalysis(leagueId = null) {
  try {
    let url = `${VIRTUAL_API_BASE}/api/v1/virtual-trader/research/sequences`;
    if (leagueId) url += `?league_id=${leagueId}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchSequenceAnalysis error:", err);
    return null;
  }
}

export async function fetchOddsCalibration() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/research/odds-calibration`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchOddsCalibration error:", err);
    return { calibration_brackets: [] };
  }
}

export async function fetchVirtualPredictions(signalFilter = null) {
  try {
    let url = `${VIRTUAL_API_BASE}/api/v1/virtual-trader/predictions`;
    if (signalFilter) url += `?signal=${signalFilter}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchVirtualPredictions error:", err);
    return { count: 0, summary: {}, predictions: [] };
  }
}

export async function fetchVirtualStrategies() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/predictions/strategies`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchVirtualStrategies error:", err);
    return { strategies: [] };
  }
}

export async function fetchBacktestDataAvailability() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/backtesting/data-availability`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchBacktestDataAvailability error:", err);
    return null;
  }
}

export async function runBacktest(params = {}) {
  try {
    const searchParams = new URLSearchParams();
    if (params.leagueId) searchParams.set("league_id", params.leagueId);
    if (params.startDate) searchParams.set("start_date", params.startDate);
    if (params.endDate) searchParams.set("end_date", params.endDate);
    if (params.stakePerBet != null) searchParams.set("stake_per_bet", params.stakePerBet);
    if (params.startingBankroll != null) searchParams.set("starting_bankroll", params.startingBankroll);
    if (params.minEdge != null) searchParams.set("min_edge", params.minEdge);
    if (params.minModelProb != null) searchParams.set("min_model_prob", params.minModelProb);
    if (params.minOdds != null) searchParams.set("min_odds", params.minOdds);

    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/backtesting/run?${searchParams.toString()}`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] runBacktest error:", err);
    return null;
  }
}

export async function runWalkForward(params = {}) {
  try {
    const searchParams = new URLSearchParams();
    if (params.leagueId) searchParams.set("league_id", params.leagueId);
    if (params.nWindows != null) searchParams.set("n_windows", params.nWindows);
    if (params.stakePerBet != null) searchParams.set("stake_per_bet", params.stakePerBet);
    if (params.startingBankroll != null) searchParams.set("starting_bankroll", params.startingBankroll);
    if (params.minEdge != null) searchParams.set("min_edge", params.minEdge);
    if (params.minModelProb != null) searchParams.set("min_model_prob", params.minModelProb);
    if (params.minOdds != null) searchParams.set("min_odds", params.minOdds);

    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/backtesting/walk-forward?${searchParams.toString()}`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] runWalkForward error:", err);
    return null;
  }
}

export async function fetchBacktestLeagues() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/backtesting/leagues`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchBacktestLeagues error:", err);
    return { leagues: [] };
  }
}

// ── Paper Trading ────────────────────────────────────────────────────────────

export async function fetchPaperBankroll() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/paper/bankroll`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchPaperBankroll error:", err);
    return null;
  }
}

export async function fetchOpenBets(limit = 50) {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/paper/open-bets?limit=${limit}`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchOpenBets error:", err);
    return { count: 0, bets: [] };
  }
}

export async function fetchBetHistory(limit = 100) {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/paper/history?limit=${limit}`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchBetHistory error:", err);
    return { count: 0, bets: [], wins: 0, losses: 0, total_profit_loss: 0 };
  }
}

export async function fetchPaperSessionStats() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/paper/session-stats`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchPaperSessionStats error:", err);
    return null;
  }
}

export async function manualFireBets() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/paper/manual/fire-bets`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] manualFireBets error:", err);
    return null;
  }
}

export async function manualSettle() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/paper/manual/settle`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] manualSettle error:", err);
    return null;
  }
}

export async function resetBankroll() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/paper/bankroll/reset`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] resetBankroll error:", err);
    return null;
  }
}

export async function resetFrontTestLedger() {
  try {
    let res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/fronttest/reset-ledger`, { method: "POST" });
    if (!res.ok) {
      res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/reset-ledger`, { method: "POST" });
    }
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] resetFrontTestLedger error:", err);
    return null;
  }
}



// ── Agent Controller & Live SportyBet Fixture Stream ─────────────────────────

export async function fetchAgentState() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/state`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchAgentState error:", err);
    return null;
  }
}

export async function updateAgentConfig(config) {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] updateAgentConfig error:", err);
    return null;
  }
}

export async function manualGenerateTicket(params = {}) {
  try {
    const sp = new URLSearchParams();
    if (params.targetOdds) sp.set("target_odds", params.targetOdds);
    if (params.numGames) sp.set("num_games", params.numGames);
    if (params.stakeAmount) sp.set("stake_amount", params.stakeAmount);

    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/generate-ticket?${sp.toString()}`, {
      method: "POST"
    });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] manualGenerateTicket error:", err);
    return null;
  }
}

/**
 * Fetch LIVE vFootball fixtures directly from SportyBet API.
 * Returns real teams, real odds, real gameIds — no seeded data.
 */
export async function fetchLiveVFootball(league = null) {
  try {
    let url = `${VIRTUAL_API_BASE}/api/v1/virtual-trader/vfootball/live`;
    if (league) url += `?league=${league}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchLiveVFootball error:", err);
    return { total: 0, leagues: {}, fixtures: [] };
  }
}

/**
 * Generate a betting ticket from LIVE vFootball fixtures.
 */
export async function generateLiveTicket(params = {}) {
  try {
    const sp = new URLSearchParams();
    if (params.targetOdds) sp.set("target_odds", params.targetOdds);
    if (params.numGames) sp.set("num_games", params.numGames);
    if (params.stakeAmount) sp.set("stake_amount", params.stakeAmount);
    if (params.market) sp.set("market", params.market);

    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/generate-ticket?${sp.toString()}`, {
      method: "POST"
    });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] generateLiveTicket error:", err);
    return null;
  }
}

// Keep old function for backward compat
export async function fetchSportyBetFixtures(leagueCode = null, limit = 20) {
  return fetchLiveVFootball(leagueCode);
}

/**
 * =================================================================
 * vFootball Front-Testing & Telegram Signal Dispatcher API
 * =================================================================
 */

export async function fetchFrontTestStatus() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/fronttest/status`);
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] fetchFrontTestStatus error:", err);
    return null;
  }
}

export async function toggleFrontTestAutomation(enabled) {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/fronttest/toggle?enabled=${enabled}`, {
      method: "POST"
    });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] toggleFrontTestAutomation error:", err);
    return null;
  }
}

export async function updateFrontTestConfig(config) {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/fronttest/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] updateFrontTestConfig error:", err);
    return null;
  }
}

export async function triggerImmediateFrontTestScan() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/fronttest/trigger-now`, {
      method: "POST"
    });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] triggerImmediateFrontTestScan error:", err);
    return null;
  }
}

export async function sendTelegramTestPing() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/fronttest/telegram-test`, {
      method: "POST"
    });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error("[VirtualClient] sendTelegramTestPing error:", err);
    return null;
  }
}



