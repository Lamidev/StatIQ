const https = require('https');

function testCode(code) {
  const url = `https://www.sportybet.com/api/ng/orders/share/${code}`;

  const req = https.get(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      'Accept': 'application/json, text/plain, */*',
      'Referer': 'https://www.sportybet.com/ng/',
      'Origin': 'https://www.sportybet.com'
    }
  }, (res) => {
    let body = '';
    res.on('data', chunk => body += chunk);
    res.on('end', () => {
      const json = JSON.parse(body);
      const data = json.data || {};
      const outcomes = data.outcomes || [];

      console.log(`=== TOP LEVEL TICKET DATA ===`);
      console.log(`Total Odds from API: ${data.totalOdds}`);
      console.log(`Stake: ${data.totalStake}`);
      console.log(`Outcomes Count: ${outcomes.length}`);
      console.log('');

      outcomes.forEach((out, idx) => {
        const markets = out.markets || [];
        const mkt = markets[0] || {};
        const mktOutcomes = mkt.outcomes || [];
        const sel = mktOutcomes[0] || {};

        const startMs = out.estimateStartTime || 0;
        const nowMs = Date.now();
        const startDate = startMs ? new Date(startMs).toLocaleString('en-NG', { timeZone: 'Africa/Lagos' }) : 'N/A';

        console.log(`--- Outcome [${idx+1}] ---`);
        console.log(`  Home: ${out.homeTeamName}`);
        console.log(`  Away: ${out.awayTeamName}`);
        console.log(`  Game ID (outer): ${out.gameId}`);
        console.log(`  Event ID: ${out.eventId}`);
        console.log(`  Start Time (ms): ${startMs}`);
        console.log(`  Start Time (local): ${startDate}`);
        console.log(`  out.status: ${out.status}`);
        console.log(`  out.matchStatus: ${out.matchStatus}`);
        console.log(`  out.playedSeconds: ${out.playedSeconds}`);
        console.log(`  out.setScore: ${out.setScore}`);
        console.log(`  out.productStatus: ${out.productStatus}`);
        console.log(`  Market Desc: ${mkt.desc}`);
        console.log(`  Market Status: ${mkt.status}`);
        console.log(`  Selection Desc: ${sel.desc}`);
        console.log(`  Selection Odds: ${sel.odds}`);
        console.log(`  Selection isActive: ${sel.isActive}`);
        console.log(`  Selection isWinning: ${sel.isWinning}`);
        console.log('');
      });
    });
  });
  req.on('error', err => console.error("Error:", err.message));
}

testCode("LYTXQL");
