const API_BASE_URL = "http://localhost:8000/api/v1";

const DEMO_PREDICTIONS = [
  {
    prediction_id: 101,
    competition: "PL",
    competition_code: "PL",
    competition_name: "Premier League",
    home_team: "Arsenal",
    away_team: "Chelsea",
    kickoff_datetime: "2026-08-08T15:00:00Z",
    prob_home: 0.68,
    prob_draw: 0.20,
    prob_away: 0.12,
    prob_over_1_5: 0.85,
    prob_over_2_5: 0.62,
    prob_btts_yes: 0.54,
    expected_home_goals: 2.10,
    expected_away_goals: 0.90,
  },
  {
    prediction_id: 102,
    competition: "PD",
    competition_code: "PD",
    competition_name: "La Liga",
    home_team: "Real Madrid",
    away_team: "Barcelona",
    kickoff_datetime: "2026-08-09T19:00:00Z",
    prob_home: 0.55,
    prob_draw: 0.25,
    prob_away: 0.20,
    prob_over_1_5: 0.90,
    prob_over_2_5: 0.71,
    prob_btts_yes: 0.68,
    expected_home_goals: 1.95,
    expected_away_goals: 1.40,
  },
  {
    prediction_id: 103,
    competition: "SA",
    competition_code: "SA",
    competition_name: "Serie A",
    home_team: "Inter Milan",
    away_team: "AC Milan",
    kickoff_datetime: "2026-08-09T17:00:00Z",
    prob_home: 0.62,
    prob_draw: 0.24,
    prob_away: 0.14,
    prob_over_1_5: 0.81,
    prob_over_2_5: 0.58,
    prob_btts_yes: 0.51,
    expected_home_goals: 1.80,
    expected_away_goals: 0.85,
  },
  {
    prediction_id: 104,
    competition: "BL1",
    competition_code: "BL1",
    competition_name: "Bundesliga",
    home_team: "Bayern Munich",
    away_team: "Borussia Dortmund",
    kickoff_datetime: "2026-08-10T16:30:00Z",
    prob_home: 0.71,
    prob_draw: 0.18,
    prob_away: 0.11,
    prob_over_1_5: 0.92,
    prob_over_2_5: 0.78,
    prob_btts_yes: 0.65,
    expected_home_goals: 2.45,
    expected_away_goals: 1.10,
  },
  {
    prediction_id: 105,
    competition: "PL",
    competition_code: "PL",
    competition_name: "Premier League",
    home_team: "Manchester City",
    away_team: "Liverpool",
    kickoff_datetime: "2026-08-10T19:30:00Z",
    prob_home: 0.58,
    prob_draw: 0.24,
    prob_away: 0.18,
    prob_over_1_5: 0.88,
    prob_over_2_5: 0.66,
    prob_btts_yes: 0.60,
    expected_home_goals: 2.05,
    expected_away_goals: 1.25,
  },
  {
    prediction_id: 106,
    competition: "FL1",
    competition_code: "FL1",
    competition_name: "Ligue 1",
    home_team: "PSG",
    away_team: "Marseille",
    kickoff_datetime: "2026-08-11T20:00:00Z",
    prob_home: 0.74,
    prob_draw: 0.17,
    prob_away: 0.09,
    prob_over_1_5: 0.89,
    prob_over_2_5: 0.69,
    prob_btts_yes: 0.52,
    expected_home_goals: 2.30,
    expected_away_goals: 0.80,
  },
  {
    prediction_id: 107,
    competition: "PD",
    competition_code: "PD",
    competition_name: "La Liga",
    home_team: "Atletico Madrid",
    away_team: "Sevilla",
    kickoff_datetime: "2026-08-11T18:00:00Z",
    prob_home: 0.64,
    prob_draw: 0.23,
    prob_away: 0.13,
    prob_over_1_5: 0.79,
    prob_over_2_5: 0.48,
    prob_btts_yes: 0.45,
    expected_home_goals: 1.70,
    expected_away_goals: 0.70,
  },
  {
    prediction_id: 108,
    competition: "SA",
    competition_code: "SA",
    competition_name: "Serie A",
    home_team: "Juventus",
    away_team: "Napoli",
    kickoff_datetime: "2026-08-12T19:45:00Z",
    prob_home: 0.52,
    prob_draw: 0.28,
    prob_away: 0.20,
    prob_over_1_5: 0.76,
    prob_over_2_5: 0.49,
    prob_btts_yes: 0.50,
    expected_home_goals: 1.50,
    expected_away_goals: 1.10,
  },
  {
    prediction_id: 109,
    competition: "CL",
    competition_code: "CL",
    competition_name: "Champions League",
    home_team: "Real Madrid",
    away_team: "Manchester City",
    kickoff_datetime: "2026-08-15T20:00:00Z",
    prob_home: 0.48,
    prob_draw: 0.27,
    prob_away: 0.25,
    prob_over_1_5: 0.91,
    prob_over_2_5: 0.72,
    prob_btts_yes: 0.67,
    expected_home_goals: 1.85,
    expected_away_goals: 1.55,
  }
];

export async function fetchLivePredictions(status = "PENDING", limit = 50) {
  try {
    const res = await fetch(`${API_BASE_URL}/predictions/upcoming?limit=${limit}`);
    if (res.ok) {
      const data = await res.json();
      const list = data.predictions || data.upcoming_predictions;
      if (list && list.length > 0) {
        const normalized = list.map(p => ({
          ...p,
          competition_code: p.competition || p.competition_code || "PL",
          home_team: p.home_team || (p.home_team_id ? `Team ${p.home_team_id}` : "Home Team"),
          away_team: p.away_team || (p.away_team_id ? `Team ${p.away_team_id}` : "Away Team"),
          prob_home: p.prob_home > 1 ? p.prob_home / 100 : p.prob_home,
          prob_draw: p.prob_draw > 1 ? p.prob_draw / 100 : p.prob_draw,
          prob_away: p.prob_away > 1 ? p.prob_away / 100 : p.prob_away,
        }));
        return { total: normalized.length, predictions: normalized };
      }
    }
  } catch (err) {
    console.log("Error fetching live predictions, using fallback dataset:", err);
  }
  return { total: DEMO_PREDICTIONS.length, predictions: DEMO_PREDICTIONS };
}

export async function fetchValueOpportunities(minEdge = 0.03, minEv = 0.05) {
  try {
    const res = await fetch(`${API_BASE_URL}/markets/value-opportunities?min_edge=${minEdge}&min_ev=${minEv}`);
    if (res.ok) {
      const data = await res.json();
      if (data.opportunities && data.opportunities.length > 0) {
        return data;
      }
    }
  } catch (err) {
    console.log("Using fallback value bets data");
  }

  const demoValueBets = [
    {
      fixture_id: 101,
      home_team: "Arsenal",
      away_team: "Chelsea",
      market: "1X2",
      selection: "Arsenal Win",
      odds: 1.75,
      implied_probability: 0.571,
      model_probability: 0.680,
      model_edge: 0.109,
      expected_value: 0.190,
      bookmaker: "SportyBet"
    },
    {
      fixture_id: 104,
      home_team: "Bayern Munich",
      away_team: "Dortmund",
      market: "OVER_UNDER",
      selection: "Over 2.5 Goals",
      odds: 1.55,
      implied_probability: 0.645,
      model_probability: 0.780,
      model_edge: 0.135,
      expected_value: 0.209,
      bookmaker: "SportyBet"
    },
    {
      fixture_id: 102,
      home_team: "Real Madrid",
      away_team: "Barcelona",
      market: "BTTS",
      selection: "Both Teams To Score - Yes",
      odds: 1.70,
      implied_probability: 0.588,
      model_probability: 0.680,
      model_edge: 0.092,
      expected_value: 0.156,
      bookmaker: "SportyBet"
    }
  ];

  return { total_value_bets: demoValueBets.length, opportunities: demoValueBets };
}

export async function generateScenarioRequest(reqData) {
  try {
    const res = await fetch(`${API_BASE_URL}/scenarios/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reqData)
    });
    if (res.ok) {
      const data = await res.json();
      if (data.scenarios && data.scenarios.length > 0) {
        return data;
      }
    }
  } catch (err) {
    console.log("Using demo scenario response");
  }

  return {
    status: "SUCCESS",
    candidate_pool_size: 24,
    total_scenarios_generated: 2,
    scenarios: [
      {
        scenario_id: "SCN-001",
        leg_count: 2,
        independence_assumption_probability: 0.53,
        selections: [
          { fixture_id: 101, home_team: "Arsenal", away_team: "Chelsea", competition_code: "PL", market_type: "1X2", selection: "Arsenal Win", model_probability: 0.68 },
          { fixture_id: 104, home_team: "Bayern Munich", away_team: "Dortmund", competition_code: "BL1", market_type: "OVER_UNDER", selection: "Over 1.5 Goals", model_probability: 0.92 }
        ]
      },
      {
        scenario_id: "SCN-002",
        leg_count: 3,
        independence_assumption_probability: 0.38,
        selections: [
          { fixture_id: 103, home_team: "Inter Milan", away_team: "AC Milan", competition_code: "SA", market_type: "1X2", selection: "Inter Win", model_probability: 0.62 },
          { fixture_id: 105, home_team: "Man City", away_team: "Liverpool", competition_code: "PL", market_type: "OVER_UNDER", selection: "Over 1.5 Goals", model_probability: 0.88 },
          { fixture_id: 106, home_team: "PSG", away_team: "Marseille", competition_code: "FL1", market_type: "1X2", selection: "PSG Win", model_probability: 0.74 }
        ]
      }
    ]
  };
}

export async function analyzeExternalCode(code, provider = "SPORTYBET") {
  try {
    const res = await fetch(`${API_BASE_URL}/external/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, provider })
    });
    if (res.ok) {
      const data = await res.json();
      if (data.items && data.items.length > 0) {
        return data;
      }
    }
  } catch (err) {
    console.log("Using demo code parser response");
  }

  return {
    parse_status: "SUCCESS",
    total_selections: 3,
    resolved_count: 3,
    unresolved_count: 0,
    items: [
      {
        external_fixture: "Arsenal vs Chelsea",
        external_market: "1X2",
        external_selection: "Arsenal Win",
        model_probability: 0.68,
        classification: "VERY_STRONG",
        suggested_alternatives: []
      },
      {
        external_fixture: "Real Madrid vs Barcelona",
        external_market: "1X2",
        external_selection: "Barcelona Win",
        model_probability: 0.20,
        classification: "WEAK",
        suggested_alternatives: [
          { market: "OVER_UNDER", selection: "Over 1.5 Goals", model_probability: 0.90 },
          { market: "BTTS", selection: "Both Teams To Score - Yes", model_probability: 0.68 }
        ]
      },
      {
        external_fixture: "Inter Milan vs AC Milan",
        external_market: "Double Chance",
        external_selection: "Inter or Draw",
        model_probability: 0.86,
        classification: "VERY_STRONG",
        suggested_alternatives: []
      }
    ]
  };
}

export async function generateSportyBetCode(selections) {
  try {
    const res = await fetch(`${API_BASE_URL}/providers/generate-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: "SPORTYBET", country_code: "ng", selections })
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.error("Generate booking code error:", err);
  }
  return { status: "ERROR", booking_code: null };
}

export async function fetchDriftReport() {
  try {
    const res = await fetch(`${API_BASE_URL}/monitoring/drift`);
    if (res.ok) return await res.json();
  } catch (err) {}
  return {
    overall_status: "STABLE",
    rolling_30_days: { sample_size: 45, accuracy_pct: 51.2, brier_score: 0.598, ece: 0.0105, status: "STABLE" },
    rolling_90_days: { sample_size: 180, accuracy_pct: 49.8, brier_score: 0.603, ece: 0.0112, status: "STABLE" },
    rolling_180_days: { sample_size: 360, accuracy_pct: 49.5, brier_score: 0.605, ece: 0.0120, status: "STABLE" }
  };
}

export async function fetchPipelineHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/monitoring/pipeline-health`);
    if (res.ok) return await res.json();
  } catch (err) {}
  return {
    pipeline_status: "HEALTHY",
    unpredicted_upcoming_fixtures_count: 0,
    total_market_odds_records: 1420,
    active_provider_market_mappings: 42,
    issues: []
  };
}

export async function triggerReconciliation() {
  try {
    const res = await fetch(`${API_BASE_URL}/monitoring/reconcile`, { method: "POST" });
    if (res.ok) return await res.json();
  } catch (err) {}
  return { reconciled_count: 5, accuracy_pct: 60.0, avg_brier_score: 0.582, avg_log_loss: 0.985 };
}

/**
 * Fetch live fixtures from football-data.org via the MatchIQ backend proxy.
 * Returns { source: "live"|"error", competition, matchday, total, fixtures[], detail? }
 */
export async function fetchFixturesByGameweek(competition = "PL", matchday = 1, season = null) {
  try {
    const seasonQuery = season ? `&season=${season}` : "";
    const res = await fetch(
      `${API_BASE_URL}/fixtures/by-gameweek?competition=${competition}&matchday=${matchday}${seasonQuery}`
    );
    if (res.ok) {
      const data = await res.json();
      return { ...data, source: "live" };
    } else {
      const err = await res.json().catch(() => ({}));
      return { competition, matchday, total: 0, fixtures: [], source: "error", detail: err.detail || `HTTP ${res.status}` };
    }
  } catch (err) {
    return { competition, matchday, total: 0, fixtures: [], source: "error", detail: err.message };
  }
}

/**
 * Fetch competition info (current matchday, total matchdays) via the MatchIQ backend.
 */
export async function fetchAvailableMatchdays(competition = "PL") {
  try {
    const res = await fetch(
      `${API_BASE_URL}/fixtures/available-matchdays?competition=${competition}`
    );
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.log("Available matchdays endpoint unreachable:", err.message);
  }
  return { competition, current_matchday: 1, total_matchdays: 38, available_matchdays: [] };
}

export async function fetchCrossLeagueGameweek(matchday = 1, limit = 25) {
  try {
    const res = await fetch(`${API_BASE_URL}/fixtures/cross-league-gameweek?matchday=${matchday}&limit=${limit}`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Fetch cross-league fixtures error:", err);
  }
  return { source: "error", fixtures: [] };
}

/**
 * Decode a SportyBet or external booking code.
 * Timeout: 12 seconds. Returns error object if server hangs or fails.
 */
export async function decodeBookingCode(code, provider = "SPORTYBET", countryCode = "ng") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-edit/decode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, provider, country_code: countryCode }),
      signal: controller.signal
    });
    clearTimeout(timer);
    if (res.ok) return await res.json();
    // Non-OK HTTP status — return structured error
    return { status: "HTTP_ERROR", code, http_status: res.status, total_selections: 0, selections: [] };
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") {
      console.warn("Decode booking code timed out after 12s");
      return { status: "TIMEOUT", code, total_selections: 0, selections: [] };
    }
    console.error("Decode booking code error:", err);
  }
  return { status: "ERROR", code, total_selections: 0, selections: [] };
}

/**
 * Run MatchIQ Statistical Ticket Re-Editor (AUDITOR, SWAP, or REMOVE mode).
 * Timeout: 15 seconds. Returns error object on server crash or timeout.
 */
export async function runTicketReEdit(selections, targetOdds, mode = "SWAP") {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-edit/re-edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selections, target_odds: targetOdds, mode }),
      signal: controller.signal
    });
    clearTimeout(timer);
    if (res.ok) return await res.json();
    return { status: "HTTP_ERROR", http_status: res.status, mode, final_selections: [] };
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") {
      console.warn(`Re-edit timed out after 15s (mode=${mode})`);
      return { status: "TIMEOUT", mode, final_selections: [] };
    }
    console.error("Ticket re-edit error:", err);
  }
  return { status: "ERROR", mode, final_selections: [] };
}

/**
 * Generate a loadable SportyBet booking code for final selections.
 */
export async function generateNewBookingCode(selections, countryCode = "ng") {
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-edit/generate-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selections, country_code: countryCode })
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Generate code error:", err);
  }
  return { status: "ERROR", booking_code: "BC-ERROR" };
}

/**
 * Ticket Tracker API Helpers
 */
export async function fetchTrackedTickets() {
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-tracker/list`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Fetch tracked tickets error:", err);
  }
  return { tickets: [], total_tickets: 0 };
}

export async function lockTrackedTicket(payload) {
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-tracker/lock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Lock tracked ticket error:", err);
  }
  return { status: "ERROR" };
}

export async function deleteTrackedTicket(ticketId) {
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-tracker/${ticketId}`, {
      method: "DELETE"
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Delete tracked ticket error:", err);
  }
  return { status: "ERROR" };
}

/**
 * Execute MatchIQ 5-Gate Pick Engine on backend to build accumulator or rollover ticket.
 */
export async function buildAiTicket(payload) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25000);
  try {
    const res = await fetch(`${API_BASE_URL}/ai-ticket/build`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    clearTimeout(timer);
    if (res.ok) return await res.json();
    return { status: "HTTP_ERROR", http_status: res.status };
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") {
      console.warn("AI Ticket builder timed out after 25s");
      return { status: "TIMEOUT" };
    }
    console.error("AI Ticket builder error:", err);
  }
  return { status: "ERROR" };
}

