const resolveApiBase = () => {
  const envUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL;
  if (envUrl) {
    const custom = envUrl.trim().replace(/\/+$/, "");
    return custom.endsWith("/api/v1") ? custom : `${custom}/api/v1`;
  }
  // If running locally, connect to local backend server
  if (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")) {
    return "http://localhost:8000/api/v1";
  }
  // Default to live 24/7 Contabo VPS Backend
  return "https://statiq-api.duckdns.org/api/v1";
};

const API_BASE_URL = resolveApiBase();



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
 * Run MatchIQ Statistical Ticket Re-Editor (AUDITOR or REMOVE mode).
 * Timeout scales with ticket size: ≤15 games = 30s, 16-30 games = 60s, 31-50 games = 90s.
 * Returns error object on server crash or timeout.
 */
export async function runTicketReEdit(selections, targetOdds, mode = "AUDITOR", targetMode = "ODDS", targetGames = 10, reshuffleSeed = null, strictMode = false) {
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
 * Ticket Tracker API Helpers (with offline/localStorage hybrid persistence)
 */
function getTicketKey(t) {
  if (t.code && t.code !== "CUSTOM" && t.code !== "AI-BUILDER-TICKET" && !String(t.code).startsWith("STATIQ-ACC-INT")) {
    return `CODE_${String(t.code).toUpperCase().trim()}`;
  }
  return `ID_${String(t.id || t.code).trim()}`;
}

export async function fetchTrackedTickets() {
  try {
    const rawPid = getUserProfileId();
    const pid = rawPid && rawPid !== "null" && rawPid !== "undefined" ? String(rawPid).trim() : "";
    const url = pid ? `${API_BASE_URL}/ticket-tracker/list?profile_id=${encodeURIComponent(pid)}` : `${API_BASE_URL}/ticket-tracker/list`;
    const res = await fetch(url);
    if (res.ok) {
      const data = await res.json();
      const serverTickets = Array.isArray(data) ? data : data.tickets || [];
      // Server is the single source of truth — keep local storage in sync
      try {
        localStorage.setItem("statiq_local_tracked_tickets", JSON.stringify(serverTickets));
      } catch (e) {}
      return serverTickets;
    }
  } catch (err) {
    console.warn("Backend unreachable, serving local cached tickets:", err);
  }

  // Fallback to local cache only if network is offline
  try {
    const raw = localStorage.getItem("statiq_local_tracked_tickets");
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}


export async function syncLiveTrackedTickets() {
  try {
    const res = await fetch(`${API_BASE_URL}/ticket-tracker/sync-live-api`, {
      method: "POST"
    });
    if (res.ok) return await res.json();
  } catch (err) {
    // Silent on offline/standalone Vercel
  }
  return null;
}

export async function lockTrackedTicket(payload) {
  const pid = getUserProfileId() || "DEFAULT";
  const now = new Date();
  const dateStr = now.toISOString().replace("T", " ").split(".")[0];

  const localTicket = {
    id: `TICK-${Date.now()}`,
    code: payload.code || "CUSTOM",
    profile_id: payload.profile_id || pid,
    mode: payload.mode || "SWAP",
    target_odds: Number(payload.target_odds || payload.total_odds || 1.5),
    total_odds: Number(payload.total_odds || 1.5),
    stake: Number(payload.stake || 1000),
    potential_win: Math.round(Number(payload.stake || 1000) * Number(payload.total_odds || 1.5) * 100) / 100,
    status: "RUNNING",
    created_at: dateStr,
    selections: payload.selections || [],
    ...payload
  };

  try {
    const fullPayload = {
      ...payload,
      profile_id: payload.profile_id || pid
    };
    const res = await fetch(`${API_BASE_URL}/ticket-tracker/lock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fullPayload)
    });
    if (res.ok) {
      const serverTicket = await res.json();
      try {
        const raw = localStorage.getItem("statiq_local_tracked_tickets");
        const existing = raw ? JSON.parse(raw) : [];
        const ticketToSave = serverTicket.id ? serverTicket : localTicket;
        const key = getTicketKey(ticketToSave);
        const updated = [ticketToSave, ...existing.filter(t => getTicketKey(t) !== key)];
        localStorage.setItem("statiq_local_tracked_tickets", JSON.stringify(updated));
      } catch (e) {}
      return serverTicket;
    }
  } catch (err) {
    console.warn("Backend lock failed, ticket saved locally:", err);
  }

  try {
    const raw = localStorage.getItem("statiq_local_tracked_tickets");
    const existing = raw ? JSON.parse(raw) : [];
    const key = getTicketKey(localTicket);
    const updated = [localTicket, ...existing.filter(t => getTicketKey(t) !== key)];
    localStorage.setItem("statiq_local_tracked_tickets", JSON.stringify(updated));
  } catch (e) {}

  return localTicket;
}

export async function deleteTrackedTicket(ticketId) {
  if (!ticketId) return { status: "ERROR" };
  
  try {
    const raw = localStorage.getItem("statiq_local_tracked_tickets");
    if (raw) {
      const list = JSON.parse(raw);
      const filtered = list.filter(t => t.id !== ticketId && t.id !== `TICK-${ticketId}`);
      localStorage.setItem("statiq_local_tracked_tickets", JSON.stringify(filtered));
    }
  } catch (e) {}

  try {
    await fetch(`${API_BASE_URL}/ticket-tracker/${encodeURIComponent(ticketId)}`, {
      method: "DELETE"
    });
  } catch (err) {
    console.warn("Backend delete unreachable, deleted locally:", err);
  }
  return { status: "SUCCESS" };
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

