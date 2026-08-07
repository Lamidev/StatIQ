/**
 * Flex Bet Calculator Utility for StatIQ
 * Evaluates SportyBet Flex Cut-N recommendations (Cut-1 through Cut-7)
 * based on empirical model win rates and user-selected Cut limits.
 */

export function calculateFlexShield(totalLegs, wonCount, totalOdds, userSelectedCut = "AUTO") {
  if (!totalLegs || totalLegs < 2) {
    return {
      eligible: false,
      reason: "Flex Bet requires at least 2 leg selections."
    };
  }

  const lossCount = Math.max(0, totalLegs - wonCount);
  const empiricalWinRate = 0.853; // 85.3% empirical leg win rate across backtest benchmarks

  let idealCut;
  if (userSelectedCut === "OFF") {
    idealCut = 0;
  } else if (userSelectedCut && userSelectedCut !== "AUTO") {
    idealCut = parseInt(userSelectedCut, 10);
  } else {
    // Auto formula based on StatIQ empirical win rate
    idealCut = Math.ceil(totalLegs * (1 - empiricalWinRate)) + 1;
    idealCut = Math.min(7, Math.max(1, idealCut));
  }

  const isFlexSettledWon = lossCount <= idealCut;

  return {
    eligible: true,
    totalLegs,
    wonCount,
    lossCount,
    recommendedCut: idealCut,
    userCutSetting: userSelectedCut,
    isFlexSettledWon,
    statusText: idealCut === 0
      ? (lossCount === 0 ? "🏆 Straight Accumulator WON (All Legs Hit!)" : `❌ Straight Accumulator LOST (${lossCount} failing legs)`)
      : (isFlexSettledWon
        ? `🛡️ Flex Cut-${idealCut} Active: TICKET SETTLED & PAID OUT AS WINNER`
        : `⚠️ Ticket lost ${lossCount} matches (Flex Cut-${idealCut} covers up to ${idealCut} losses)`),
    description: idealCut === 0
      ? "Straight accumulator mode requires 100% winning legs (0 losses allowed)."
      : (isFlexSettledWon
        ? `Even with ${lossCount} ${lossCount === 1 ? 'match' : 'matches'} lost out of ${totalLegs}, applying SportyBet Flex Cut-${idealCut} guarantees that your ticket is SETTLED AS WON!`
        : `Ticket had ${lossCount} failing legs out of ${totalLegs}. Flex Cut-${idealCut} protection covers up to ${idealCut} failing legs.`)
  };
}
