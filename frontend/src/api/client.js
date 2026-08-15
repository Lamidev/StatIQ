const rawBase = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").trim().replace(/\/+$/, "");
const API_BASE_URL = rawBase.endsWith("/api/v1") ? rawBase : `${rawBase}/api/v1`;



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
    console.error("Error fetching live predictions:", err);
  }
  return { total: 0, predictions: [] };
}

export async function fetchValueOpportunities(minEdge = 0.03, minEv = 0.05) {
  try {
    const res = await fetch(`${API_BASE_URL}/markets/value-opportunities?min_edge=${minEdge}&min_ev=${minEv}`);
    if (res.ok) {
      const data = await res.json();
      return data;
    }
  } catch (err) {
    console.error("Error fetching value opportunities:", err);
  }
  return { total_value_bets: 0, opportunities: [] };
}

export async function generateScenarioRequest(reqData) {
  try {
    const res = await fetch(`${API_BASE_URL}/scenarios/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reqData)
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Scenario analysis error:", err);
  }
  return { status: "ERROR", scenarios: [] };
}

export async function analyzeExternalCode(code, provider = "SPORTYBET") {
  try {
    const res = await fetch(`${API_BASE_URL}/external/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, provider })
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Analyze external code error:", err);
  }
  return { parse_status: "ERROR", total_selections: 0, items: [] };
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
  } catch (err) {
    console.error("Fetch drift report error:", err);
  }
  return null;
}

export async function fetchPipelineHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/monitoring/pipeline-health`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Fetch pipeline health error:", err);
  }
  return null;
}

export async function triggerReconciliation() {
  try {
    const res = await fetch(`${API_BASE_URL}/monitoring/reconcile`, { method: "POST" });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Trigger reconciliation error:", err);
  }
  return null;
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
 * Timeout: 20 seconds (SportyBet API can take 3-8s). Retries once on timeout.
 * Returns error object if server hangs or fails.
 */
export async function decodeBookingCode(code, provider = "SPORTYBET", countryCode = "ng", _retry = true) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-edit/decode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, provider, country_code: countryCode }),
      signal: controller.signal
    });
    clearTimeout(timer);
    if (res.ok) return await res.json();
    return { status: "HTTP_ERROR", code, http_status: res.status, total_selections: 0, selections: [] };
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") {
      console.warn("Decode timed out after 20s — retrying once...");
      if (_retry) return decodeBookingCode(code, provider, countryCode, false);
      return { status: "TIMEOUT", code, total_selections: 0, selections: [] };
    }
    console.error("Decode booking code error:", err);
  }
  return { status: "ERROR", code, total_selections: 0, selections: [] };
}

/**
 * Fetch real match statistics (corners, halftime scores) from API-Football via backend.
 * Only called for picks that cannot be verified from score data alone.
 * @param {Array} matches - [{home_team, away_team, pick, match_date}]
 * @returns {Object} - { status, stats: { "0": {found, ht_home, ht_away, home_corners, away_corners}, ... } }
 */
export async function fetchMatchStats(matches) {
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-edit/match-stats`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ matches }),
    });
    if (res.ok) return await res.json();
    return { status: "HTTP_ERROR", stats: {} };
  } catch (err) {
    console.warn("fetchMatchStats error:", err);
    return { status: "ERROR", stats: {} };
  }
}

/**
 * Run MatchIQ Statistical Ticket Re-Editor (AUDITOR, SWAP, or REMOVE mode).
 * Timeout scales with ticket size: ≤15 games = 30s, 16-30 games = 60s, 31-50 games = 90s.
 * Returns error object on server crash or timeout.
 */
export async function runTicketReEdit(selections, targetOdds, mode = "SWAP", targetMode = "ODDS", targetGames = 10, reshuffleSeed = null, strictMode = false) {
  const controller = new AbortController();
  // Adaptive timeout — larger tickets need more time due to parallel HTTP resolution
  const n = Array.isArray(selections) ? selections.length : 0;
  const timeoutMs = n > 30 ? 90000 : n > 15 ? 60000 : 30000;
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-edit/re-edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selections,
        target_odds: targetOdds,
        mode,
        target_mode: targetMode,
        target_games: targetGames,
        reshuffle_seed: reshuffleSeed || Date.now(),
        strict_mode: strictMode
      }),
      signal: controller.signal
    });
    clearTimeout(timer);
    if (res.ok) return await res.json();
    return { status: "HTTP_ERROR", http_status: res.status, mode, final_selections: [] };
  } catch (err) {
    clearTimeout(timer);
    if (err.name === "AbortError") {
      console.warn(`Re-edit timed out after ${timeoutMs / 1000}s (mode=${mode}, games=${n})`);
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
 * Phase 14: Generate 100% Verified SportyBet Booking Code with selection reconciliation.
 */
export async function generateVerifiedBookingCode(selections, ticketId = "TKT-GEN", region = "ng") {
  try {
    const res = await fetch(`${API_BASE_URL}/providers/verified-booking`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: "SPORTYBET",
        region,
        statiq_ticket_id: ticketId,
        selections
      })
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Generate verified booking error:", err);
  }
  return { status: "REJECTED", message: "Network/connection failure during booking verification." };
}


export async function verifyPasskeyApi(passkey) {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passkey }),
    });
    return await res.json();
  } catch (err) {
    return { success: false, message: "Network connection failure." };
  }
}

export async function fetchAdminPasskeys() {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/passkeys`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Fetch passkeys error:", err);
  }
  return { total: 0, passkeys: [] };
}

export async function createPasskeyApi(payload) {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/passkeys/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return await res.json();
  } catch (err) {
    return { success: false, message: "Failed to create passkey" };
  }
}

export async function togglePasskeyApi(key, isActive) {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/passkeys/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, is_active: isActive }),
    });
    return await res.json();
  } catch (err) {
    return { success: false };
  }
}

export async function deletePasskeyApi(key) {
  try {
    const res = await fetch(`${API_BASE_URL}/auth/passkeys/${encodeURIComponent(key)}`, {
      method: "DELETE",
    });
    return await res.json();
  } catch (err) {
    return { success: false };
  }
}

export function getUserProfileId() {
  if (typeof window === "undefined") return null;
  try {
    const params = new URLSearchParams(window.location.search);
    const codeParam = params.get("code") || params.get("profile") || params.get("user") || params.get("passkey");
    if (codeParam) {
      const clean = codeParam.toUpperCase().trim();
      localStorage.setItem("statiq_profile_id", clean);
      localStorage.setItem("statiq_passkey", clean);
      return clean;
    }
    return localStorage.getItem("statiq_passkey") || localStorage.getItem("statiq_profile_id") || null;
  } catch (e) {
    return null;
  }
}

export function logoutUser() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("statiq_passkey");
    localStorage.removeItem("statiq_profile_id");
    const cleanUrl = window.location.origin + window.location.pathname;
    window.history.replaceState({}, document.title, cleanUrl);
  }
}

/**
 * Ticket Tracker API Helpers
 */
export async function fetchTrackedTickets() {
  try {
    const pid = getUserProfileId();
    const res = await fetch(`${API_BASE_URL}/ticket-tracker/list?profile_id=${encodeURIComponent(pid)}`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Fetch tracked tickets error:", err);
  }
  return { tickets: [], total_tickets: 0 };
}

export async function syncLiveTrackedTickets() {
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-tracker/sync-live-api`, {
      method: "POST"
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Sync live tickets API error:", err);
  }
  return null;
}

export async function lockTrackedTicket(payload) {
  try {
    const pid = getUserProfileId();
    const fullPayload = {
      ...payload,
      profile_id: payload.profile_id || pid
    };
    const res = await fetch(`${API_BASE_URL}/ticket-tracker/lock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fullPayload)
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
    const fullPayload = { reshuffle_seed: Date.now(), ...payload };
    const res = await fetch(`${API_BASE_URL}/ai-ticket/build`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fullPayload),
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


export async function fetchNotificationsList() {

  try {
    const res = await fetch(`${API_BASE_URL}/notifications`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Fetch notifications error:", err);
  }
  return { notifications: [], unread_count: 0 };
}

export async function markNotificationRead(payload) {
  try {
    const res = await fetch(`${API_BASE_URL}/notifications/mark-read`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Mark notification read error:", err);
  }
  return null;
}

export async function clearAllNotifications() {
  try {
    const res = await fetch(`${API_BASE_URL}/notifications/clear`, {
      method: "DELETE"
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Clear notifications error:", err);
  }
  return null;
}


export async function fetchTodaysSportybetGames(day = "today") {
  try {
    const res = await fetch(`${API_BASE_URL}/fixtures/sportybet-today?day=${day}`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Fetch today's SportyBet games error:", err);
  }
  return { total_matches: 0, total_leagues: 0, leagues: [] };
}

