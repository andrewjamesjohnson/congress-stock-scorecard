#!/bin/bash
# The morning post with real numbers, for the last market day: new trade reports, holdings brought up to date,
# IEX's prices, everyone's estimated gain, Before the bell (the real post only: the SEC's filings since the
# close), then the slides. The timer (daily.py) runs it at 06:00 our time (the House's index updates about 07:00, so
# that morning's House filings show the next day); by hand it works any time after IEX's file for the day is out.
#
#   ./morning.sh                         the last market day, as a proof into "Real Proof MM.DD/Morning"
#   ./morning.sh --day 2026-10-28        that day
#   ./morning.sh --day 2026-10-28 --post the real post, numbered as it goes out, into "Daily Posts/MM.DD Weekday"
#
# The Senate side uses the last Senate read (data/senate-holdings.json). Reading the Senate needs its box ticked
# in the browser panel, by Andrew, so it refreshes when he does that.
set -e
cd "$(dirname "$0")"
PY=/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python
[ -x "$PY" ] || PY=/usr/bin/python3     # the system Python 3.9, as the clip factory's timers run it (launchd lets it reach the Desktop)
if [ "$1" = "--day" ]; then
  day="$2"
else
  day=$($PY -E -c "import prices, datetime; print(prices.previous_open(datetime.date.today()))")
fi
echo "== $day: new trade reports"
$PY -I pull_trades.py --day "$day"
echo "== holdings: yearly reports plus this year's trades"
$PY -I pull_holdings.py
echo "== prices and estimates"
$PY -I estimate.py --day "$day"
bell=""
if [ "$3" = "--post" ] || [ "$1" = "--post" ]; then
  post=$($PY -E -c "import prices, datetime as d; p = d.date.fromisoformat('$day'); print(next(p + d.timedelta(i) for i in range(1, 10) if prices.open_day(p + d.timedelta(i))))")
  echo "== before the bell: companies members own that reported since the close ($post)"
  if $PY -I bell.py --day "$post"; then
    bell="--bell data/bell-$post.json"
  else
    echo "   the SEC could not be read: no Before the bell slide today"
  fi
fi
echo "== slides"
# scorecard.py needs Pillow and numpy from the user's site-packages, which -I turns off: -E instead (this folder
# holds only our own code; downloads live under data/)
if [ "$3" = "--post" ] || [ "$1" = "--post" ]; then
  $PY -E scorecard.py --post "data/close-$day.json" "data/trades-$day.json" $bell
else
  $PY -E scorecard.py --close "data/close-$day.json" --trades "data/trades-$day.json"
fi
