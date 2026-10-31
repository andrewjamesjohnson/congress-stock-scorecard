// Read the Senate's financial disclosures inside the browser panel, after Andrew has ticked the box at
// https://efdsearch.senate.gov/search/home/ himself ("I understand the prohibitions..."). Claude may not tick it.
//
// How (Claude, with the browser panel on https://efdsearch.senate.gov/search/):
//   1. Paste this file into the page (javascript_tool). It defines window.senateRead.
//   2. senateRead.annual()  -> starts reading every senator's latest yearly report (Part 3, Assets).
//      senateRead.ptrs('01/01/2026', '10/28/2026') -> starts reading every trade report in that window.
//      Both run in the page; check senateRead.progress() until done is true (one call may not outlast them).
//   3. JSON.stringify(senateRead.annualOut()) or JSON.stringify(senateRead.ptrOut(), null, 2): the result is
//      big, so the tool saves it to a file; then  python3 -I senate_import.py <that file> annual|ptr
//   4. python3 -I pull_holdings.py --senate   (rebuilds data/senate-holdings.json)
(() => {
  const tok = () => document.querySelector('input[name=csrfmiddlewaretoken]').value;
  const own = {Self: 'self', Spouse: 'SP', Joint: 'JT', Child: 'DC', 'Dependent Child': 'DC'};
  const kinds = {'Purchase': 'P', 'Sale (Full)': 'S', 'Sale (Partial)': 'S (partial)', 'Exchange': 'E'};
  const money = v => {
    const n = (v.match(/\$[\d,]+/g) || []).map(s => +s.replace(/[$,]/g, ''));
    if (!n.length) return null;
    return /Over/i.test(v) ? [n[0] + 1, null] : [n[0], n[1] || n[0]];
  };
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const state = {annual: {}, ptr: {}, picks: [], ptrs: [], done: {annual: false, ptr: false}};

  async function search(types, start, end) {          // every report of a type filed by sitting senators
    let all = [], off = 0, total = 0;
    do {
      const body = new URLSearchParams({start: String(off), length: '100', report_types: types, filer_types: '[1]',
        submitted_start_date: start + ' 00:00:00', submitted_end_date: end + ' 23:59:59', candidate_state: '',
        senator_state: '', office_id: '', first_name: '', last_name: '', csrfmiddlewaretoken: tok()});
      const r = await fetch('/search/report/data/', {method: 'POST', body, credentials: 'same-origin',
        headers: {'X-CSRFToken': tok(), 'Content-Type': 'application/x-www-form-urlencoded'}});
      const j = JSON.parse(await r.text());
      total = j.recordsTotal; all = all.concat(j.data); off += 100;
      await wait(600);
    } while (off < total);
    return all.map(x => ({first: x[0], last: x[1], href: (x[3].match(/href="([^"]+)"/) || [])[1],
                          title: x[3].replace(/<[^>]+>/g, '').trim(), filed: x[4]}));
  }

  async function annual(year = '2025') {               // the latest yearly (or new filer) report per senator
    const reports = await search('[7]', '01/01/' + (+year + 1), '12/31/' + (+year + 1));
    const pick = {};
    for (const p of reports) {
      const cy = p.title.includes('CY ' + year), nf = /New Filer/.test(p.title);
      if ((!cy && !nf) || p.href.includes('/paper/')) continue;
      const score = (cy ? 2e9 : 1e9) + +(p.filed.slice(6) + p.filed.slice(0, 2) + p.filed.slice(3, 5));
      const k = p.first + '|' + p.last;
      if (!pick[k] || score > pick[k].score) pick[k] = {...p, score};
    }
    state.picks = Object.values(pick);
    for (const p of state.picks) {
      const doc = new DOMParser().parseFromString(await (await fetch(p.href, {credentials: 'same-origin'})).text(), 'text/html');
      const t = [...doc.querySelectorAll('table')].find(x =>
        [...x.querySelectorAll('thead th')].map(h => h.innerText.trim()).join('|') === '|Asset|Asset Type|Owner|Value|Income Type|Income');
      const held = [];
      if (t) for (const tr of t.querySelectorAll('tbody tr')) {
        const c = [...tr.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim());
        const m = c.length > 4 && c[1].match(/^([A-Z][A-Z.\-]{0,6}) - /), v = c.length > 4 && money(c[4]);
        if (!m || !v) continue;
        const kind = /Stock/.test(c[2]) ? 'S' : /Exchange Traded/i.test(c[2]) ? 'E' : /Mutual/i.test(c[2]) ? 'M' : 'O';
        held.push([m[1], own[c[3]] || c[3], v[0], v[1], kind, c[1].slice(m[0].length, m[0].length + 36)]);
      }
      state.annual[p.first + '|' + p.last] = [p.first, p.last, p.filed, p.title, held];
      await wait(250);
    }
    state.done.annual = true;
  }

  async function ptrs(start, end) {                    // every trade in every electronic trade report
    state.ptrs = (await search('[11]', start, end)).filter(p => !p.href.includes('/paper/'));
    for (const p of state.ptrs) {
      const doc = new DOMParser().parseFromString(await (await fetch(p.href, {credentials: 'same-origin'})).text(), 'text/html');
      const trades = [];
      for (const tr of doc.querySelectorAll('table tbody tr')) {
        const c = [...tr.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim());
        if (c.length < 8 || !/^\d\d\/\d\d\/\d{4}$/.test(c[1])) continue;
        const [, date, owner, ticker, asset, kind, type, amount] = c, v = money(amount);
        if (ticker === '--' || !v) continue;
        trades.push([date.slice(6) + '-' + date.slice(0, 2) + '-' + date.slice(3, 5), own[owner] || owner, ticker,
                     kind === 'Stock Option' ? 'OP' : kind === 'Stock' ? 'ST' : 'O', kinds[type] || type, v[0], v[1],
                     asset.slice(0, 40)]);
      }
      state.ptr[p.href] = {first: p.first, last: p.last, filed: p.filed, trades};
      await wait(250);
    }
    state.done.ptr = true;
  }

  window.senateRead = {
    annual: (y) => { annual(y); return 'started'; },
    ptrs: (s, e) => { ptrs(s, e); return 'started'; },
    progress: () => ({annual: Object.keys(state.annual).length + '/' + state.picks.length,
                      ptrs: Object.keys(state.ptr).length + '/' + state.ptrs.length, done: state.done}),
    annualOut: () => Object.values(state.annual),
    ptrOut: () => Object.values(state.ptr),
  };
  return 'senateRead ready';
})();
