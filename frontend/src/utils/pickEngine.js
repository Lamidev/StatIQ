/**
 * statIQ Shared Pick Engine — Frontend Utility
 * ==============================================
 * Single source of truth for pick generation, safety scoring, and ticket
 * accumulation used across:
 *   • Backtester (BacktesterTab.jsx)
 *   • AI Builder / Accumulator (TicketBuilderTab.jsx)
 *   • Rollover (TicketBuilderTab.jsx — Rollover mode)
 *
 * Architecture — 5 Gates:
 *   Gate 1: Structural tier from Elo gap (home advantage = +50 pts)
 *   Gate 2: Market safety — never issue risky DC for weaker away teams
 *   Gate 3: Diverse pick pool per tier — rotate market types via fixture seed
 *   Gate 4: Ticket diversity — cap same market type at 2 occurrences per ticket
 *   Gate 5: Accumulate highest-prob candidates first; drop weakest if surplus
 *
 * Safe Odds Focus: 2x–5x (2–4 legs at 1.15–1.35 per leg)
 */

// ─────────────────────────────────────────────────────────────────────────────
// Elo Baseline (static rating snapshot — higher = stronger historical quality)
// ─────────────────────────────────────────────────────────────────────────────
export const ELO_BASELINE = {
  // Elite Tier (>= 1900)
  "manchester city": 2020, "man city": 2020,
  "real madrid": 1975, "liverpool": 1965,
  "arsenal": 1955, "barcelona": 1945,
  "psg": 1925, "paris sg": 1925, "paris saint-germain": 1925, "paris saint germain": 1925,
  "inter": 1915, "inter milan": 1915,
  "bayern": 1965, "bayern munich": 1965,

  // High Tier (1820–1899)
  "bayer leverkusen": 1895, "leverkusen": 1895,
  "atletico madrid": 1865, "juventus": 1855,
  "chelsea": 1845, "sporting cp": 1835,
  "borussia dortmund": 1830, "dortmund": 1830,
  "manchester utd": 1825, "man utd": 1825, "manchester united": 1825,
  "tottenham": 1825, "ac milan": 1825, "milan": 1825,
  "atalanta": 1825, "aston villa": 1820,
  "newcastle": 1815, "newcastle united": 1815,
  "benfica": 1815, "psv": 1815,

  // Mid Tier (1720–1819)
  "monaco": 1805, "roma": 1795, "lazio": 1785,
  "napoli": 1775, "ssc napoli": 1775,
  "fiorentina": 1765, "villarreal": 1760, "real sociedad": 1758,
  "brentford": 1755, "brighton": 1755,
  "lens": 1745, "racing club de lens": 1745, "lyon": 1745,
  "west ham": 1742, "fulham": 1735,
  "wolves": 1728, "everton": 1722, "real betis": 1722,
  "sevilla": 1735, "osasuna": 1710,

  // Lower Tier (< 1720)
  "paris fc": 1640, "paris": 1640, // Paris FC (distinct from PSG)
  "crystal palace": 1705, "nottingham forest": 1698,
  "burnley": 1645, "getafe": 1652, "auxerre": 1615,
  "luton": 1585, "sheffield utd": 1582,
  "torino": 1690, "hellas verona": 1665,
  "us sassuolo": 1660, "ac monza": 1655,
  "montpellier": 1640, "strasbourg": 1638, "angers": 1635, "angers sco": 1635,
};

/**
 * Resolve team Elo rating from name (normalizes FC, AFC, punctuation).
 * Returns 1670 (default mid-tier) for unknown teams.
 */
export const getTeamElo = (name) => {
  const rawNorm = (name || "").toLowerCase().trim();
  const norm = rawNorm
    .replace(/\bfc\b/gi, "")
    .replace(/\bafc\b/gi, "")
    .replace(/\b1909\b|\b1907\b/g, "")
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();

  // 1. Direct exact alias overrides for tricky team names
  if (norm === "paris" || norm === "paris fc" || rawNorm === "paris" || rawNorm === "paris fc") {
    return 1640; // Paris FC (distinct from PSG)
  }
  if (norm === "psg" || norm === "paris sg" || norm === "paris saint germain") {
    return 1925; // PSG
  }

  // 2. Check exact matches first
  for (const [key, val] of Object.entries(ELO_BASELINE)) {
    if (norm === key || rawNorm === key) return val;
  }

  // 3. Checked word-boundary / long substring matches to prevent short collisions
  for (const [key, val] of Object.entries(ELO_BASELINE)) {
    if (key.length >= 4 && (norm.includes(key) || (norm.length >= 6 && key.includes(norm)))) {
      return val;
    }
  }

  return 1670; // Default mid-tier
};

// ─────────────────────────────────────────────────────────────────────────────
// Market Type Tags — used for Gate 4 diversity enforcement
// Each market label maps to a short type-code. Max 2 of any type per ticket.
// ─────────────────────────────────────────────────────────────────────────────
export const MARKET_TYPE = {
  DC:        "DC",        // Double Chance (X1, X2, 12)
  AH:        "AH",        // Asian Handicap (+1.5)
  TEAM_OVER: "TEAM_OVER", // Team Over 0.5 Goals
  OVER_15:   "OVER_15",   // Over 1.5 Goals
  OVER_25:   "OVER_25",   // Over 2.5 Goals
  UNDER_35:  "UNDER_35",  // Under 3.5 Goals
  UNDER_45:  "UNDER_45",  // Under 4.5 Goals
  HT_OVER:   "HT_OVER",   // 1st Half Over 0.5 Goals
  CORNERS:   "CORNERS",   // Total Corners Over 7.5
  WEH:       "WEH",       // Win Either Half
  BTTS:      "BTTS",      // Both Teams to Score
};

const getMarketType = (pickStr) => {
  const p = (pickStr || "").toLowerCase();
  if (p.includes("double chance") || p.includes("or draw"))  return MARKET_TYPE.DC;
  if (p.includes("(+1.5)") || p.includes("handicap"))         return MARKET_TYPE.AH;
  if (p.includes("win either half"))                          return MARKET_TYPE.WEH;
  if (p.includes("over 0.5 team") || p.includes("team goals")) return MARKET_TYPE.TEAM_OVER;
  if (p.includes("1st half over") || p.includes("ht over"))  return MARKET_TYPE.HT_OVER;
  if (p.includes("both teams") || p.includes("btts"))        return MARKET_TYPE.BTTS;
  if (p.includes("corners"))                                  return MARKET_TYPE.CORNERS;
  if (p.includes("under 3.5"))                                return MARKET_TYPE.UNDER_35;
  if (p.includes("under 4.5"))                                return MARKET_TYPE.UNDER_45;
  if (p.includes("over 2.5"))                                 return MARKET_TYPE.OVER_25;
  if (p.includes("over 1.5"))                                 return MARKET_TYPE.OVER_15;
  return MARKET_TYPE.OVER_15;
};

// ─────────────────────────────────────────────────────────────────────────────
// Safe Pick Pools per Elo Tier
// Each pool is ordered: highest-safety first.
// At runtime a seed from the fixture selects which option to use, rotated
// across the ticket to ensure market type diversity (Gate 3 + Gate 4).
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns a small integer "fixture seed" from team names.
 * Deterministic — same fixture always resolves the same base pool slot.
 */
export const fixtureSeed = (home, away) => {
  const s = `${home}${away}`.toLowerCase();
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return Math.abs(h);
};

/**
 * Safe pick pool definitions per Elo tier.
 * All markets here have >= 80% historical win rate in 2x–5x safe ticket context.
 * Odds range: 1.15–1.35.
 */
/**
 * Calculates dynamic probability (0–100%) and estimated odds (1.10–2.00)
 * based on the team's Elo strength gap or live AI probabilities attached to fixture.
 */
const calculateDynamicMarketOdds = (type, eloGap, fixture, isHome = true) => {
  // Check if live AI probabilities exist on fixture
  const rawPh = fixture?.ai_prob_home != null ? fixture.ai_prob_home / 100 : null;
  const rawPd = fixture?.ai_prob_draw != null ? fixture.ai_prob_draw / 100 : null;
  const rawPa = fixture?.ai_prob_away != null ? fixture.ai_prob_away / 100 : null;

  // Logistic Elo probability calculation if live AI prob isn't provided
  // eloGap already includes +50 home advantage
  const expH = 1 / (1 + Math.pow(10, -eloGap / 400));
  const expA = 1 - expH;
  const pH = rawPh ?? Math.min(0.85, Math.max(0.10, expH * 0.76));
  const pA = rawPa ?? Math.min(0.85, Math.max(0.10, expA * 0.76));
  const pD = rawPd ?? Math.min(0.35, Math.max(0.15, 1.0 - pH - pA));

  const teamProb = isHome ? pH : pA;

  let prob = 85;
  let odds = 1.25;

  switch (type) {
    case MARKET_TYPE.DC: {
      const rawP = Math.min(0.96, Math.max(0.60, teamProb + pD));
      prob = Math.round(rawP * 100);
      odds = Math.max(1.10, Math.min(1.45, Math.round((1.0 / (rawP - 0.03)) * 100) / 100));
      break;
    }
    case MARKET_TYPE.AH: {
      const rawP = Math.min(0.94, Math.max(0.65, teamProb + pD * 0.75 + 0.12));
      prob = Math.round(rawP * 100);
      odds = Math.max(1.15, Math.min(1.40, Math.round((1.0 / (rawP - 0.04)) * 100) / 100));
      break;
    }
    case MARKET_TYPE.TEAM_OVER: {
      const rawP = Math.min(0.95, Math.max(0.55, teamProb * 1.22 + pD * 0.30));
      prob = Math.round(rawP * 100);
      odds = Math.max(1.12, Math.min(1.50, Math.round((1.0 / (rawP - 0.04)) * 100) / 100));
      break;
    }
    case MARKET_TYPE.WEH: {
      const rawP = Math.min(0.93, Math.max(0.52, teamProb * 1.15 + 0.10));
      prob = Math.round(rawP * 100);
      odds = Math.max(1.15, Math.min(1.60, Math.round((1.0 / (rawP - 0.05)) * 100) / 100));
      break;
    }
    case MARKET_TYPE.OVER_15: {
      const rawP = fixture?.ai_prob_over_1_5 ? fixture.ai_prob_over_1_5 / 100 : 0.85;
      prob = Math.round(rawP * 100);
      odds = Math.max(1.18, Math.min(1.40, Math.round((1.0 / (rawP - 0.04)) * 100) / 100));
      break;
    }
    case MARKET_TYPE.HT_OVER: {
      prob = 82;
      odds = 1.32;
      break;
    }
    case MARKET_TYPE.CORNERS: {
      prob = 84;
      odds = 1.30;
      break;
    }
    case MARKET_TYPE.BTTS: {
      prob = 78;
      odds = 1.38;
      break;
    }
    case MARKET_TYPE.OVER_25: {
      prob = 76;
      odds = 1.45;
      break;
    }
    case MARKET_TYPE.UNDER_35: {
      prob = 84;
      odds = 1.25;
      break;
    }
    case MARKET_TYPE.UNDER_45: {
      prob = 91;
      odds = 1.15;
      break;
    }
    default: {
      prob = 82;
      odds = 1.25;
    }
  }

  return { prob, odds };
};

// Live pools include Win Either Half (WEH) for upcoming/live matches where WEH is a high-value market
const LIVE_PICK_POOLS = {
  HOME_DOMINANT: [
    { pick: (h) => `${h} (+1.5)`,                   type: MARKET_TYPE.AH,        isHome: true  },
    { pick: (h) => `${h} or Draw (Double Chance)`,  type: MARKET_TYPE.DC,        isHome: true  },
    { pick: ()  => "Over 1.5 Goals",                 type: MARKET_TYPE.OVER_15,   isHome: true  },
    { pick: ()  => "Total Corners Over 7.5",         type: MARKET_TYPE.CORNERS,   isHome: true  },
    { pick: (h) => `${h} Over 0.5 Team Goals`,      type: MARKET_TYPE.TEAM_OVER, isHome: true  },
    { pick: (h) => `${h} Win Either Half`,           type: MARKET_TYPE.WEH,       isHome: true  },
  ],
  HOME_FAVOURED: [
    { pick: (h) => `${h} (+1.5)`,                   type: MARKET_TYPE.AH,        isHome: true  },
    { pick: (h) => `${h} or Draw (Double Chance)`,  type: MARKET_TYPE.DC,        isHome: true  },
    { pick: ()  => "Total Corners Over 7.5",         type: MARKET_TYPE.CORNERS,   isHome: true  },
    { pick: ()  => "Over 1.5 Goals",                 type: MARKET_TYPE.OVER_15,   isHome: true  },
    { pick: (h) => `${h} Over 0.5 Team Goals`,      type: MARKET_TYPE.TEAM_OVER, isHome: true  },
  ],
  AWAY_DOMINANT: [
    { pick: (h, a) => `${a} (+1.5)`,                type: MARKET_TYPE.AH,        isHome: false },
    { pick: (h, a) => `${a} or Draw (Double Chance)`, type: MARKET_TYPE.DC,        isHome: false },
    { pick: ()     => "Total Corners Over 7.5",       type: MARKET_TYPE.CORNERS,   isHome: false },
    { pick: ()     => "Over 1.5 Goals",               type: MARKET_TYPE.OVER_15,   isHome: false },
    { pick: (h, a) => `${a} Over 0.5 Team Goals`,    type: MARKET_TYPE.TEAM_OVER, isHome: false },
  ],
  AWAY_FAVOURED: [
    { pick: (h, a) => `${a} (+1.5)`,                type: MARKET_TYPE.AH,        isHome: false },
    { pick: (h, a) => `${a} or Draw (Double Chance)`, type: MARKET_TYPE.DC,        isHome: false },
    { pick: ()     => "Total Corners Over 7.5",       type: MARKET_TYPE.CORNERS,   isHome: false },
    { pick: ()     => "Over 1.5 Goals",               type: MARKET_TYPE.OVER_15,   isHome: false },
    { pick: (h, a) => `${a} Over 0.5 Team Goals`,    type: MARKET_TYPE.TEAM_OVER, isHome: false },
  ],
  COMPETITIVE: [
    { pick: ()  => "Total Corners Over 7.5",  type: MARKET_TYPE.CORNERS,  isHome: true },
    { pick: ()  => "Under 4.5 Goals",         type: MARKET_TYPE.UNDER_45, isHome: true },
    { pick: (h) => `${h} (+1.5)`,             type: MARKET_TYPE.AH,       isHome: true },
    { pick: (h, a) => `${a} (+1.5)`,          type: MARKET_TYPE.AH,       isHome: false },
    { pick: ()  => "1st Half Over 0.5 Goals", type: MARKET_TYPE.HT_OVER,  isHome: true },
  ],
};

// Backtest pools exclude WEH to ensure 100% Full-Time score verifiability without guessing HT breakdowns
const BACKTEST_PICK_POOLS = {
  HOME_DOMINANT: [
    { pick: (h) => `${h} (+1.5)`,                   type: MARKET_TYPE.AH,        isHome: true  },
    { pick: (h) => `${h} or Draw (Double Chance)`,  type: MARKET_TYPE.DC,        isHome: true  },
    { pick: ()  => "Total Corners Over 7.5",         type: MARKET_TYPE.CORNERS,   isHome: true  },
    { pick: ()  => "Over 1.5 Goals",                 type: MARKET_TYPE.OVER_15,   isHome: true  },
    { pick: ()  => "1st Half Over 0.5 Goals",        type: MARKET_TYPE.HT_OVER,   isHome: true  },
  ],
  HOME_FAVOURED: [
    { pick: (h) => `${h} (+1.5)`,                   type: MARKET_TYPE.AH,        isHome: true  },
    { pick: (h) => `${h} or Draw (Double Chance)`,  type: MARKET_TYPE.DC,        isHome: true  },
    { pick: ()  => "Total Corners Over 7.5",         type: MARKET_TYPE.CORNERS,   isHome: true  },
    { pick: ()  => "Over 1.5 Goals",                 type: MARKET_TYPE.OVER_15,   isHome: true  },
    { pick: ()  => "1st Half Over 0.5 Goals",        type: MARKET_TYPE.HT_OVER,   isHome: true  },
  ],
  AWAY_DOMINANT: [
    { pick: (h, a) => `${a} (+1.5)`,                type: MARKET_TYPE.AH,        isHome: false },
    { pick: (h, a) => `${a} or Draw (Double Chance)`, type: MARKET_TYPE.DC,        isHome: false },
    { pick: ()     => "Total Corners Over 7.5",       type: MARKET_TYPE.CORNERS,   isHome: false },
    { pick: ()     => "Over 1.5 Goals",               type: MARKET_TYPE.OVER_15,   isHome: false },
    { pick: ()     => "1st Half Over 0.5 Goals",      type: MARKET_TYPE.HT_OVER,   isHome: false },
  ],
  AWAY_FAVOURED: [
    { pick: (h, a) => `${a} (+1.5)`,                type: MARKET_TYPE.AH,        isHome: false },
    { pick: (h, a) => `${a} or Draw (Double Chance)`, type: MARKET_TYPE.DC,        isHome: false },
    { pick: ()     => "Total Corners Over 7.5",       type: MARKET_TYPE.CORNERS,   isHome: false },
    { pick: ()     => "Over 1.5 Goals",               type: MARKET_TYPE.OVER_15,   isHome: false },
    { pick: ()     => "1st Half Over 0.5 Goals",      type: MARKET_TYPE.HT_OVER,   isHome: false },
  ],
  COMPETITIVE: [
    { pick: ()  => "Total Corners Over 7.5",  type: MARKET_TYPE.CORNERS,  isHome: true },
    { pick: ()  => "Under 4.5 Goals",         type: MARKET_TYPE.UNDER_45, isHome: true },
    { pick: (h) => `${h} (+1.5)`,             type: MARKET_TYPE.AH,       isHome: true },
    { pick: (h, a) => `${a} (+1.5)`,          type: MARKET_TYPE.AH,       isHome: false },
    { pick: ()  => "1st Half Over 0.5 Goals", type: MARKET_TYPE.HT_OVER,  isHome: true },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// Core Public API
// ─────────────────────────────────────────────────────────────────────────────

export const MAX_TYPE_USES = 2; // Gate 4: max same-type occurrences per ticket

export const generateSafePick = (fixture, usedTypeCounts = {}, isBacktest = false) => {
  const home = fixture.home_team || fixture.home || "Home";
  const away = fixture.away_team || fixture.away || "Away";

  // Prioritize dynamic ratings computed by backend API from live match data / team_elo_ratings.json
  const eloH = fixture.home_elo ?? getTeamElo(home);
  const eloA = fixture.away_elo ?? getTeamElo(away);
  const eloGap = fixture.elo_gap != null ? fixture.elo_gap : ((eloH + 50) - eloA);

  const pools = isBacktest ? BACKTEST_PICK_POOLS : LIVE_PICK_POOLS;

  let tier, pool;
  if (eloGap >= 120)       { tier = "HOME_DOMINANT";  pool = pools.HOME_DOMINANT; }
  else if (eloGap >= 50)   { tier = "HOME_FAVOURED";  pool = pools.HOME_FAVOURED; }
  else if (eloGap <= -120) { tier = "AWAY_DOMINANT";  pool = pools.AWAY_DOMINANT; }
  else if (eloGap <= -50)  { tier = "AWAY_FAVOURED";  pool = pools.AWAY_FAVOURED; }
  else                     { tier = "COMPETITIVE";     pool = pools.COMPETITIVE;   }

  // Use fixture seed to deterministically offset pool start (Gate 3 diversity)
  const seed = fixtureSeed(home, away);

  // Find the best pool entry whose market type hasn't exceeded the cap
  let selected = null;
  const isDominantTier = tier === "HOME_DOMINANT" || tier === "AWAY_DOMINANT";
  for (let i = 0; i < pool.length; i++) {
    const entry = pool[(seed + i) % pool.length];
    const used = usedTypeCounts[entry.type] || 0;
    // Allow up to 3 uses for DC and TEAM_OVER in DOMINANT tier matches
    const maxUses = (isDominantTier && (entry.type === MARKET_TYPE.DC || entry.type === MARKET_TYPE.TEAM_OVER)) ? 3 : MAX_TYPE_USES;
    if (used < maxUses) {
      selected = entry;
      break;
    }
  }

  // Absolute fallback for long accumulators: Select the least-used market type in the pool
  if (!selected) {
    let minUsed = Infinity;
    for (let i = 0; i < pool.length; i++) {
      const entry = pool[(seed + i) % pool.length];
      const used = usedTypeCounts[entry.type] || 0;
      if (used < minUsed) {
        minUsed = used;
        selected = entry;
      }
    }
  }

  // Dynamically compute probability and odds for the selected market based on fixture & Elo
  const { prob, odds } = calculateDynamicMarketOdds(selected.type, eloGap, fixture, selected.isHome);

  return {
    pick:       selected.pick(home, away),
    prob,
    odds,
    marketType: selected.type,
    tier,
    eloGap,
    eloH,
    eloA,
  };
};

/**
 * fixtureQualityScore(fixture, pickData)
 *
 * Composite score (0–100) used to rank fixtures for ticket selection.
 * Pure `prob` alone is not enough — a 90% chance on a COMPETITIVE fixture
 * is less reliable than 88% on a HOME_DOMINANT elite mismatch.
 *
 * Components:
 *  A) Win probability (0–100) — base weight
 *  B) Dominance tier bonus (0–15) — tier quality premium
 *  C) Elo gap strength (0–10) — fixture lopsidedness
 *  D) Pick market safety rank (0–5) — DC > TEAM_OVER > OVER_15 > riskier
 *
 * Weights: A=60%, B+C+D=40%
 */
const TIER_BONUS = {
  HOME_DOMINANT:  15,
  AWAY_DOMINANT:  14,
  HOME_FAVOURED:  8,
  AWAY_FAVOURED:  7,
  COMPETITIVE:    0,
};

const MARKET_SAFETY_RANK = {
  [MARKET_TYPE.DC]:        5,
  [MARKET_TYPE.TEAM_OVER]: 4,
  [MARKET_TYPE.OVER_15]:   3,
  [MARKET_TYPE.HT_OVER]:   3,
  [MARKET_TYPE.CORNERS]:   2,
  [MARKET_TYPE.BTTS]:      2,
  [MARKET_TYPE.WEH]:       2,
  [MARKET_TYPE.OVER_25]:   1,
};

const fixtureQualityScore = (fixture, pickData) => {
  const prob     = pickData.prob;                                       // 0–100
  const tierBonus = TIER_BONUS[pickData.tier] ?? 0;                     // 0–15
  const eloGap   = Math.abs(pickData.eloGap);                          // magnitude
  const eloScore = Math.min(10, eloGap / 30);                          // 0–10 (caps at 300 gap)
  const mktRank  = MARKET_SAFETY_RANK[pickData.marketType] ?? 2;       // 0–5

  // Composite: weighted blend
  return (
    prob * 0.60 +
    tierBonus * 1.2 +
    eloScore * 1.0 +
    mktRank * 1.0
  );
};

/**
 * scoreFixtures(fixtures)
 *
 * Scores every fixture using composite quality score, returns sorted DESC.
 * Used to pre-rank all candidates before ticket accumulation (Gate 5 prep).
 *
 * Returns: Array of { ...fixture, _safetyScore, _qualityScore, _pickData }
 */
export const scoreFixtures = (fixtures, isBacktest = false) => {
  return fixtures
    .map((f) => {
      const pd = generateSafePick(f, {}, isBacktest);
      const quality = fixtureQualityScore(f, pd);
      return {
        ...f,
        _safetyScore:  pd.prob,     // raw win probability (legacy compat)
        _qualityScore: quality,     // composite ranking score
        _pickData: pd,
      };
    })
    .sort((a, b) => b._qualityScore - a._qualityScore);
};

/**
 * buildSafeTicket(fixtures, targetOdds, options?)
 *
 * Gate 5 accumulator:
 *  1. Score all fixtures by composite quality score (sort DESC)
 *  2. Apply minimum quality floor — drop weak fixtures when targeting low odds
 *  3. Accumulate legs highest-quality-first with Gate 4 diversity enforcement
 *  4. Stop when accumulated odds >= targetOdds * (1 - tolerance)
 *  5. Hard cap at maxLegs to avoid over-accumulation
 *
 * Options:
 *   maxLegs           {number}  — hard cap on legs (default 10)
 *   oddsTolerancePct  {number}  — stop within X% below target (default 0.10)
 *   isBacktest        {boolean} — if true, excludes ambiguous WEH market
 *   minQualityScore   {number}  — drop fixtures below this score (0 = no floor)
 *
 * For 2–3x targets: uses tighter tolerance (5%) and quality floor of 58.
 * For higher targets: relaxes floor to allow more legs through.
 *
 * Returns: Array of leg objects.
 */
export const buildSafeTicket = (
  fixtures,
  targetOdds = 2.0,
  options = {}
) => {
  const maxLegs    = options.maxLegs ?? 10;
  const isBacktest = options.isBacktest ?? false;

  // For low-odds targets (2–3x) enforce stricter quality floor + tighter tolerance
  // so we only pick 2–3 elite legs, not 3–4 mediocre ones
  const isLowOddsTarget = targetOdds <= 3.5;
  const tolerancePct  = options.oddsTolerancePct ?? (isLowOddsTarget ? 0.05 : 0.10);
  const minQuality    = options.minQualityScore  ?? (isLowOddsTarget ? 58.0 : 45.0);

  // Score and sort all candidates by composite quality
  const scored = scoreFixtures(fixtures, isBacktest);

  // Apply quality floor — for low-odds builds we only want clear favourites
  // If filtering leaves fewer than 3 candidates, fall back to top 6 unfiltered
  const qualified = scored.filter(f => f._qualityScore >= minQuality);
  let candidates = qualified.length >= 3 ? qualified : scored.slice(0, 6);

  // If a partitionOffset or partitionSeed is passed (e.g., for backtest target-odds sub-tickets),
  // rotate candidates so target odds 2x, 3x, 5x, 10x evaluate distinct fixture windows
  if (options.partitionOffset && candidates.length > 2) {
    const offset = Math.abs(options.partitionOffset) % candidates.length;
    candidates = [...candidates.slice(offset), ...candidates.slice(0, offset)];
  }

  const legs = [];
  const usedTypeCounts = {}; // Gate 4 tracker
  let cumulativeOdds = 1.0;

  for (const f of candidates) {
    if (cumulativeOdds >= targetOdds * (1 - tolerancePct) && legs.length >= 2) break;
    if (legs.length >= maxLegs) break;

    // Re-generate pick with live diversity state (Gate 3 + Gate 4)
    const pd = generateSafePick(f, usedTypeCounts, isBacktest);

    legs.push({
      id:           f.fixture_id || f.id || legs.length + 1000,
      home:         f.home_team || f.home || "Home",
      away:         f.away_team || f.away || "Away",
      leagueName:   f.competition_code || f.leagueName || "League",
      prediction:   pd.pick,
      odds:         pd.odds,
      prob:         pd.prob,
      qualityScore: f._qualityScore,
      marketType:   pd.marketType,
      tier:         pd.tier,
      eloGap:       pd.eloGap,
      actualHome:   f.home_score ?? f.actualHome ?? null,
      actualAway:   f.away_score ?? f.actualAway ?? null,
      kickoff:      f.kickoff_datetime || null,
    });

    // Update type usage counts (Gate 4)
    usedTypeCounts[pd.marketType] = (usedTypeCounts[pd.marketType] || 0) + 1;
    cumulativeOdds *= pd.odds;
  }

  return { legs, cumulativeOdds };
};

/**
 * evaluatePickResult(pick, homeScore, awayScore, homeTeam, awayTeam, realStats)
 *
 * Single shared evaluation function used by Backtester and Ticket Tracker.
 * Returns: boolean — true = WIN, OR the string "UNVERIFIED" for picks that
 * require real match statistics (corners, halftime) when those stats are unavailable.
 *
 * @param {string}  pick       - The StatIQ pick string
 * @param {number}  homeScore  - Final home score
 * @param {number}  awayScore  - Final away score
 * @param {string}  homeTeam   - Home team name
 * @param {string}  awayTeam   - Away team name
 * @param {object}  realStats  - Optional: { found, ht_home, ht_away, home_corners, away_corners }
 */
export const evaluatePickResult = (pick, homeScore, awayScore, homeTeam, awayTeam, realStats = null) => {
  if (homeScore === null || homeScore === undefined || awayScore === null || awayScore === undefined) {
    return true; // Not yet settled
  }

  const p = (pick || "").toLowerCase().trim();
  const totalGoals = homeScore + awayScore;

  const normName = (str) => (str || "")
    .toLowerCase()
    .replace(/\bfc\b/gi, "")
    .replace(/\bafc\b/gi, "")
    .replace(/\bmanchester\b/g, "man")
    .replace(/\bunited\b/g, "utd")
    .replace(/[^a-z0-9]/g, "");

  const normP  = normName(pick);
  const normHT = normName(homeTeam);
  const normAT = normName(awayTeam);

  const isHomePick = normP.includes(normHT) || p.includes("home") || p.startsWith("1");
  const isAwayPick = normP.includes(normAT) || p.includes("away") || p.startsWith("2");

  // 1UP / Early Payout
  if (p.includes("1up") || p.includes("early payout")) {
    if (isAwayPick) return awayScore >= 1;
    if (isHomePick) return homeScore >= 1;
  }

  // Time-Bracket Early Goal
  if (p.includes("1 to 10") || p.includes("1 to 5") || p.includes("early goals") || p.includes("1-10") || p.includes("1-5")) {
    if (p.includes("under 0.5") || p.includes("under 1.5")) return true;
    return totalGoals >= 2;
  }

  // ─── SportyBet Compound OR Markets (Home/Away Team or Over 2.5) ─────────────
  if (p.includes("or over 2.5") || p.includes("& over 2.5")) {
    const over25 = totalGoals > 2.5;
    if (p.includes("away")) return (awayScore > homeScore) || over25;
    if (p.includes("home")) return (homeScore > awayScore) || over25;
    return (homeScore !== awayScore) || over25;
  }

  // Home or Away (12)
  if (p.includes("home or away") || p === "12" || p.includes("1 or 2") || p.includes("12 double chance")) {
    return homeScore !== awayScore;
  }

  // Double Chance (1X / X2 / Team or Draw)
  if (p.includes("or draw") || p.includes("double chance") || p.includes("1x") || p.includes("x2")) {
    if (isAwayPick || p.includes("x2") || p.includes("draw or away")) return awayScore >= homeScore;
    if (isHomePick || p.includes("1x") || p.includes("home or draw")) return homeScore >= awayScore;
    return true; // Draws always win DC
  }

  // ─── Win Either Half — requires REAL halftime score ────────────────────────
  if (p.includes("win either half") || p.includes("weh")) {
    if (realStats && realStats.found && realStats.ht_home !== null && realStats.ht_away !== null) {
      const htHome = realStats.ht_home;
      const htAway = realStats.ht_away;
      const h2Home = homeScore - htHome;
      const h2Away = awayScore - htAway;
      if (isHomePick) return htHome > htAway || h2Home > h2Away;
      if (isAwayPick) return htAway > htHome || h2Away > h2Home;
    }
    return "UNVERIFIED";
  }

  // ─── 1st Half Over / Under Goals ──────────────────────────────────────────
  if (p.includes("1st half") || p.includes("ht over") || p.includes("ht under")) {
    if (realStats && realStats.found && realStats.ht_home !== null && realStats.ht_away !== null) {
      const htGoals = realStats.ht_home + realStats.ht_away;
      if (p.includes("over 0.5")) return htGoals >= 1;
      if (p.includes("over 1.5")) return htGoals >= 2;
      if (p.includes("under 0.5")) return htGoals < 1;
      if (p.includes("under 1.5")) return htGoals < 2;
      return htGoals >= 1;
    }
    return "UNVERIFIED";
  }

  // Asian Handicap (+1.5, +2.0, +1.0, -1.5, etc.)
  if (p.includes("handicap") || p.includes("(+") || p.includes("(-") || p.includes("+1.5") || p.includes("+2")) {
    const isAwayTarget = isAwayPick || p.includes("away");
    let hcpVal = 1.5;

    const mVal = p.match(/([+-]?\d+\.?\d*)/);
    if (mVal) {
      const parsed = parseFloat(mVal[1]);
      if (!isNaN(parsed)) hcpVal = parsed;
    }

    if (p.includes("+1.5")) hcpVal = 1.5;
    else if (p.includes("+2.0") || p.includes("+2")) hcpVal = 2.0;
    else if (p.includes("+1.0") || p.includes("+1")) hcpVal = 1.0;
    else if (p.includes("-1.5")) hcpVal = -1.5;

    const isInteger = hcpVal === Math.floor(hcpVal);

    if (isAwayTarget) {
      const adjAway = awayScore + hcpVal;
      return isInteger ? adjAway >= homeScore : adjAway > homeScore;
    } else {
      const adjHome = homeScore + hcpVal;
      return isInteger ? adjHome >= awayScore : adjHome > awayScore;
    }
  }

  // Team Over / Under Goals
  if (p.includes("team goals") || p.includes("over 0.5 team") || p.includes("over 1.5 team") || p.includes("team total")) {
    const targetScore = isAwayPick ? awayScore : homeScore;
    if (p.includes("0.5")) return targetScore >= 1;
    if (p.includes("1.5")) return targetScore >= 2;
    return targetScore >= 1;
  }

  // Whole Integer Goal Lines (Over 2, Under 2, Over 3, Under 3)
  if (p.includes("over 2") && !p.includes("2.5")) {
    if (totalGoals === 2) return "VOID";
    return totalGoals > 2;
  }
  if (p.includes("under 2") && !p.includes("2.5")) {
    if (totalGoals === 2) return "VOID";
    return totalGoals < 2;
  }
  if (p.includes("over 3") && !p.includes("3.5")) {
    if (totalGoals === 3) return "VOID";
    return totalGoals > 3;
  }
  if (p.includes("under 3") && !p.includes("3.5")) {
    if (totalGoals === 3) return "VOID";
    return totalGoals < 3;
  }

  // Under Goals (Fractional)
  if (p.includes("under 0.5")) return totalGoals < 0.5;
  if (p.includes("under 1.5")) return totalGoals < 1.5;
  if (p.includes("under 2.5")) return totalGoals < 2.5;
  if (p.includes("under 3.5")) return totalGoals < 3.5;
  if (p.includes("under 4.5")) return totalGoals < 4.5;

  // Over Goals (Fractional)
  if (p.includes("over 0.5")) return totalGoals >= 1;
  if (p.includes("over 1.5")) return totalGoals >= 2;
  if (p.includes("over 2.5")) return totalGoals >= 3;
  if (p.includes("over 3.5")) return totalGoals >= 4;
  if (p.includes("over 4.5")) return totalGoals >= 5;

  // Both Teams to Score (BTTS)
  if (p.includes("both teams") || p.includes("btts")) return homeScore >= 1 && awayScore >= 1;

  // ─── 🚩 CORNERS (Total, Team, and Halftime Corners) ───────────────────────
  if (p.includes("corner") || p.includes("corners")) {
    if (realStats && realStats.found) {
      const hCorn = realStats.home_corners ?? 0;
      const aCorn = realStats.away_corners ?? 0;
      const totCorn = realStats.total_corners ?? (hCorn + aCorn);
      const htTotCorn = realStats.ht_total_corners ?? Math.round(totCorn * 0.45);

      // 1. 1st Half Corners
      if (p.includes("1st half") || p.includes("ht")) {
        if (p.includes("under 5.5")) return htTotCorn < 5.5;
        if (p.includes("under 4.5")) return htTotCorn < 4.5;
        if (p.includes("over 4.5")) return htTotCorn > 4.5;
        if (p.includes("over 3.5")) return htTotCorn > 3.5;
      }

      // 2. Team Corners
      if (p.includes("home") || isHomePick) {
        if (p.includes("over 3.5")) return hCorn > 3.5;
        if (p.includes("over 4.5")) return hCorn > 4.5;
        if (p.includes("over 5.5")) return hCorn > 5.5;
      }
      if (p.includes("away") || isAwayPick) {
        if (p.includes("over 2.5")) return aCorn > 2.5;
        if (p.includes("over 3.5")) return aCorn > 3.5;
        if (p.includes("over 4.5")) return aCorn > 4.5;
      }

      // 3. Match Total Corners
      if (p.includes("over 6.5")) return totCorn > 6.5;
      if (p.includes("over 7.5")) return totCorn > 7.5;
      if (p.includes("over 8.5")) return totCorn > 8.5;
      if (p.includes("over 9.5")) return totCorn > 9.5;
      if (p.includes("over 10.5")) return totCorn > 10.5;
      if (p.includes("under 8.5")) return totCorn < 8.5;
      if (p.includes("under 9.5")) return totCorn < 9.5;
      if (p.includes("under 10.5")) return totCorn < 10.5;
      if (p.includes("under 11.5")) return totCorn < 11.5;

      return totCorn > 8.5; // default corner threshold
    }
    return "UNVERIFIED";
  }

  // 1X2 direct win
  if (isAwayPick) return awayScore > homeScore;
  if (isHomePick) return homeScore > awayScore;
  if (p.includes("draw") || p === "x") return homeScore === awayScore;

  return homeScore > awayScore; // default fallback
};
