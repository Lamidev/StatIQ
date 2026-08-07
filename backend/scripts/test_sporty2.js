const https = require('https');

function testCode(code) {
  const url = `https://www.sportybet.com/api/ng/orders/share/${code}`;

  const req = https.get(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      'Accept': 'application/json, text/plain, */*',
      'Referer': 'https://www.sportybet.com/ng/',
      'Origin': 'https://www.sportybet.com'
    },
    timeout: 5000
  }, (res) => {
    let body = '';
    res.on('data', chunk => body += chunk);
    res.on('end', () => {
      const json = JSON.parse(body);
      const outcomes = (json.data && json.data.outcomes) || [];
      console.log(`Total Outcomes: ${outcomes.length}`);

      let totalOdds = 1.0;
      outcomes.forEach((out, idx) => {
        const home = out.homeTeamName || "Home";
        const away = out.awayTeamName || "Away";
        const markets = out.markets || [];
        let mktName = "1X2";
        let selName = "1";
        let oddsVal = 1.0;

        if (markets.length > 0) {
          mktName = markets[0].desc || markets[0].name || "1X2";
          const mktOutcomes = markets[0].outcomes || [];
          if (mktOutcomes.length > 0) {
            selName = mktOutcomes[0].desc || mktOutcomes[0].name || "1";
            oddsVal = parseFloat(mktOutcomes[0].odds) || 1.0;
          }
        }

        totalOdds *= oddsVal;
        console.log(`[${idx+1}] ${home} vs ${away} | ${mktName} -> ${selName} | ${oddsVal}x`);
      });

      console.log(`\nCalculated Total Combined Odds: ${totalOdds.toFixed(2)}x`);
    });
  });
}

testCode("LYTXQL");
