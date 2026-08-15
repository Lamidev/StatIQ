"""
MatchIQ Leg-to-Odds Dynamic Calculator
=======================================
Calculates realistic, dynamically fitted leg counts and target per-leg odds ranges
for any total target odds (e.g. 2.0 to 1000.0+).

Prevents unrealistic forcing of fixed game counts (e.g., 7 legs for 500 odds)
by maintaining safe individual leg odds (1.18 - 1.45).
"""

import math
from typing import Dict, Any, Tuple

# Baseline safe target odds per individual leg
SAFE_MIN_LEG_ODDS = 1.18
SAFE_MAX_LEG_ODDS = 1.45
SAFE_DEFAULT_AVG_LEG_ODDS = 1.32

def calculate_dynamic_leg_config(target_total_odds: float) -> Dict[str, Any]:
    """
    Returns optimal leg count range and recommended per-leg target odds
    given a target total accumulator odds value.
    """
    target_total_odds = max(1.10, float(target_total_odds))

    if target_total_odds <= 1.50:
        return {
            "target_total_odds": target_total_odds,
            "min_legs": 1,
            "max_legs": 2,
            "ideal_legs": 1,
            "per_leg_target_odds": target_total_odds,
            "min_probability_threshold": 0.85,
            "description": "Single / Low Multi"
        }
    
    # Calculate ideal leg count based on natural log scaling with safe average leg odds (~1.32)
    calculated_legs = math.ceil(math.log(target_total_odds) / math.log(SAFE_DEFAULT_AVG_LEG_ODDS))
    
    # Bound leg counts safely
    if target_total_odds <= 3.0:
        min_legs, max_legs = 2, 3
    elif target_total_odds <= 7.0:
        min_legs, max_legs = 4, 6
    elif target_total_odds <= 15.0:
        min_legs, max_legs = 6, 8
    elif target_total_odds <= 35.0:
        min_legs, max_legs = 8, 11
    elif target_total_odds <= 75.0:
        min_legs, max_legs = 11, 14
    elif target_total_odds <= 200.0:
        min_legs, max_legs = 13, 17
    elif target_total_odds <= 600.0:
        min_legs, max_legs = 17, 23
    else:
        min_legs, max_legs = 20, 26

    # Determine strict minimum model probability threshold for 9/10 accuracy target
    if target_total_odds <= 3.0:
        min_prob_threshold = 0.85  # Ultra safe / Rollover (85%+ per leg)
    elif target_total_odds <= 7.0:
        min_prob_threshold = 0.80  # High confidence
    elif target_total_odds <= 20.0:
        min_prob_threshold = 0.75  # Solid confidence
    else:
        min_prob_threshold = 0.68  # Standard balanced

    ideal_legs = max(min_legs, min(max_legs, calculated_legs))
    per_leg_target = round(target_total_odds ** (1.0 / ideal_legs), 3)

    return {
        "target_total_odds": target_total_odds,
        "min_legs": min_legs,
        "max_legs": max_legs,
        "ideal_legs": ideal_legs,
        "per_leg_target_odds": per_leg_target,
        "min_probability_threshold": min_prob_threshold,
        "description": f"{ideal_legs}-Leg Accumulator (~{per_leg_target} odds/leg, min {int(min_prob_threshold*100)}% confidence/leg)"
    }
