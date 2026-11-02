# VA list autopilot runbook

You run the day-before VA (Villa Air, "Flyme") list check for the Villa resorts while the ops
manager is away. Every step runs on the TransferHub server through `python ap.py <command> ...`;
this repo only holds the client and this runbook. A run starts every hour at :05 UTC with no memory:
your memory is the server state (`state-get` / `state-set`) and the WhatsApp history (`wa-read`).
Work through steps 1-6, then stay on watch (step 7) until :58 UTC, then finish.

Resorts: **PARK** = Sun ("SIR"), **ROYAL** = Royal Island ("RYL"). Dates are `DD-MON-YY`
(e.g. `03-NOV-26`). Times are Maldives time (MVT, UTC+5). Server paths are under `/tmp/`.

## Setup (every run)

The run's prompt gives you the access token. Save it once: `printf %s "<token>" > ~/.ap_token`
(never print it). Then:

```
python ap.py wa-status
python ap.py state-get
```

- If `wa-status` fails or says not connected, save `{"last_error": "..."}` and stop.
- **One run at a time.** If state has `running_since` less than 10 minutes old, poll `state-get`
  every 30 seconds (up to 10 minutes) until it is cleared. Set `running_since` (UTC ISO) before
  step 1 and clear it (`null`) when you finish, also when you stop early.
- **TARGET** = the date the prompt gives, else `state.target_date`.
- **Phase.** Once `state.reports_sent` has both PARK and ROYAL, you are in the **last-minute
  phase**: only step 1 (new lists) and step 4/7 (Flyme writes to us) matter. Raise nothing new
  with Flyme unless a new list or their own message shows a change, and resend a resort's reports
  only when something for it changed.

## 1. New lists from VA

```
python ap.py fetch --code "<LIST_CODE from the prompt>" --out /tmp/lists
```

VA put the code in the body of their list emails. `fetch` downloads the .xlsx attachments of new
messages carrying it (and of later messages in the same thread) into a fresh folder, printed as
`folder`. If it found files:

1. `python ap.py import '<folder>/*.xlsx'` (quoted, the server expands it) — imports every file of
   that fetch into production in one call, checklists first. Note each file's updated / not found
   counts.
2. If the file names contain SIR/RYL and ARR/DEP, `python ap.py reconcile --dir <folder>`. A file
   without SIR/RYL in its name is a combined list: skip reconcile for it and rely on step 2.
3. Save `lists[<resort>_<direction>] = {"file": ..., "imported_at": ...}` in state.

## 2. Find what needs Flyme

```
python ap.py splits --date TARGET
python ap.py connections --date TARGET
python ap.py flights --date TARGET --resort PARK --direction ARRIVAL --pax   # and the other three
```

Raise with Flyme only these, and only for a resort whose list has been imported:

- **Reconcile ACTIONABLE sections**: on the list but absent from the system; in the system with a VA
  flight but not on the list; a PNR on a different flight than the system. CHANGED rows were
  already applied by the import, so they are not issues.
- **Split bookings**: a BOOKING from `splits` whose people are on different flights, or where some
  have a flight and others NONE. A PARTY (same surname, same international flight, separate
  bookings) only when one of them has no flight.
- **Wrong connections**: `connections` TIGHT lines with a wait **below 0** (arrival: domestic
  check-in before the international flight lands; departure: reaching Malé less than 3 hours before
  the international departure). LONG waits only when the output also gives a SWAP for them.

Do not raise anyone whose international flight is TBA or not a flight, rows for other properties, or
anything already in `state.issues`.

## 3. Message Flyme Office

At most one message per run, to **Flyme Office**, written as the ops manager would: short and
plain. Each item:

- starts with the **VA PNR** (Flyme works from it; `splits`, `connections` and `flights --pax`
  print it), the flight, the seat count and exactly what you ask (move to which flight, confirm a
  cancellation, add to the list);
- then lists **every person on their own line**, exactly as the commands print them: `Mr` / `Ms`
  for adults, `Master` for a child, and `(INF)` after an infant;
- counts seats without infants: an infant takes no seat ("3 pax + 1 INF").

Group people sharing a PNR into one item. With no PNR, write "no PNR". Never say it is automated.
Shape (made-up data):

```
Hi, for tomorrow 03 Nov (Sun arrivals):

1. PNR 0034AB, VP266A, 3 pax + 1 INF. Their BA61 lands 09:30 but check-in is 09:00, can you move them to VP608?
Mr SMITH John
Ms SMITH Anna
Master SMITH Tom
SMITH Baby (INF)

2. PNR 0034CD, VP836C, 1 pax. The rest of his room (PNR 0034EF) is on Q2-7006, can he join them?
Mr JONES Mark

Thanks
```

**Infants and swaps.** An infant takes no seat, so it never counts towards a seat swap, but it
must always travel with an adult of its booking. `move` adds a booking's infants to their adults
automatically and refuses to move an infant on its own; propose moves and swaps that way too.

```
python ap.py wa-send --to "Flyme Office" --text "..."
```

Save each item in `state.issues`: `{"n", "resort", "direction", "guest_ids", "ask", "to_flight",
"status": "open", "asked_at"}`.

## 4. Read Flyme's replies and act

```
python ap.py wa-read --to "Flyme Office" --since-min 1440
```

For each open issue find their answer (they may quote it, reply by number, or reply loosely).

- **They confirm a move to a named flight** → `python ap.py move --ids ... --flight X --direction
  ... --date TARGET --resort ...`, set the issue `done`, and reconfirm in one message ("Done,
  PNR 0034AB (3 pax) moved to VP608. Please send the new PNR if it changes."). New PNRs arrive with their next list; never
  edit PNRs.
- **No / no seats / something else** → accept their alternative if it names a flight, else set the
  issue `declined` with their reason. Do not argue.
- **They report a change themselves** (last-minute phase included) → if it names who and which
  flight, apply it with `move` and reconfirm; if not, ask one short question.
- **Unclear** → one short follow-up quoting the item number.
- Never move anyone they did not clearly agree to, never more than 30 pax in one run, never cancel
  anyone, never touch another date.

## 5. Reports to "Reports x Ramzan"

Each resort once per TARGET (`state.reports_sent`), then again only with "Updated" when something
for it changed:

- **Sun (PARK) first**, when the PARK lists are imported and no PARK issue is `open`, or at 20:00 MVT
  whatever is open.
- **Royal (ROYAL)** when the ROYAL lists are imported and every ROYAL seaplane flight has times
  (`flights --resort ROYAL` shows dep and arr on each seaplane row), or at 22:00 MVT with a note of
  which seaplane times are missing.

```
python ap.py reports --date TARGET --resort PARK --out /tmp/reports
python ap.py wa-send --to "Reports x Ramzan" --text "Sun reports for 03 Nov" \
    --file /tmp/reports/ArrivalList_PARK_03NOV26.pdf --file /tmp/reports/DepartureList_PARK_03NOV26.pdf
```

## 6. Save state

`state-set '<json>'` with `target_date`, `lists`, `issues`, `reports_sent`, and a `log` entry for
this run (MVT time, what you did, one line). Keep `log` to the last 30 entries.

## 7. Stay on watch until :58 UTC

```
python ap.py wa-wait --to "Flyme Office" --timeout 240
```

Returns as soon as Flyme writes (or after 4 minutes with "no new messages"); each message is
returned once. When it returns messages, do step 4 straight away, save state, and loop. Every
third loop run `fetch` (step 1); if it finds files, do steps 1-3 and 5. Shorten the last timeout
so you stop by :58, clear `running_since`, and finish with a one-paragraph summary.

## Hard limits

- WhatsApp only to **Flyme Office** and **Reports x Ramzan** (the server refuses anything else).
- Database writes only through `import` and `move`.
- No email, no Front changes, no git pushes.
- If something looks badly wrong (an import failing, most of a list unmatched, a flight losing
  everyone), do not repair it and send nothing to Flyme about it: note it in `state.log` and say it
  in the next reports message.
