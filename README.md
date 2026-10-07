# Grove

Grove is a daily home page for Ole Miss students and fans. It shows a campus photo of the day, a big greeting with your name, Rebels game day, your next class, what's open for dining, what's on tonight in Oxford, weather by the hour, countdowns, campus news and quick links. It's inspired by Princeton's [Today](https://github.com/TigerAppsOrg/Today).

- Click the name in the greeting to change it.
- **Settings** turns widgets on and off and switches between 2 and 3 columns. **Arrange** lets you drag widgets around. Phones always show one column.
- **Study mode** hides everything except a big clock and a focus timer (25 min, 50 min or a 5 min break).
- The name and layout are saved only in the visitor's browser.

## How it works

- **Pipelines** (`grove/pipelines/`) fetch each source and save the result in the database. `grove/refresh.py` runs each one on its own schedule (weather every 30 min, news every hour).
- **Widgets** (`grove/widgets.py`) only read the database, so a slow or broken source never slows down the page. If a fetch fails, the last good data stays up, and the widget says so once it's more than a few hours old.
- **The page** (`grove/templates/dashboard.html`, `grove/static/app.js`) loads everything from `/api/widgets` and draws it in the browser. The same JSON will feed the Chrome new-tab extension later.

## Run it locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

python -m grove.refresh --once                  # fetch every source once
python -m flask --app grove.web run --debug     # http://127.0.0.1:5000
```

Without `DATABASE_URL`, data goes into a local SQLite file, `grove.db`. Copy `.env.example` to `.env` to set the semester dates (for "Week N of the semester") or the news feeds.

## Game day

The **Game Day** card shows the next Rebels game with a countdown and TV channel, plus the next few games across the sports you add. On a football game day, the page switches to game-day mode: a red "It's game day! Ole Miss vs. LSU · 6:30 PM" banner under the greeting and a red stripe across the top. During game week, a "Game week: at Georgia on Saturday" pill shows instead.

Schedules come from **ESPN's public team schedule feeds** by default (football, men's and women's basketball, baseball), so game day works with no setup. To use the athletics site's own calendar links instead, the "Add to calendar" or "Sync to calendar" option on each schedule page, set them in Railway as sport=url pairs (change any `webcal://` to `https://`):
```
GAMEDAY_CALENDARS=football=https://.../football.ics baseball=https://.../baseball.ics basketball=https://.../mbb.ics
```
The refresher reads them every 3 hours, so time changes (like "TBA" becoming a kickoff time) show up the same day. The card stays hidden until a schedule loads.

Within 5 days of a home kickoff, the card shows the **kickoff forecast** ("Kickoff: 72° · Partly cloudy · 20% rain") from the hourly Oxford forecast. During home football game week, it also lists the links in `grove/data/gameday_info.json`, such as parking and shuttles or the clear bag policy (see below).

**Live scores** for football, men's and women's basketball, and baseball come from ESPN's public college scoreboard feeds. It needs no key, but it's unofficial and could change without notice, so it fails soft: if it breaks, the card simply shows the schedule.
- **During a game:** the card shows a live scoreboard ("Basketball · LIVE · 2nd 10:21 · Ole Miss 52 – 48 Kentucky"), and open pages refresh every minute. Live football and basketball games also show in the banner under the greeting; baseball stays on the card, since there are games most days in the spring.
- **After a game:** the final ("W 31–24 vs. LSU") stays on the card for 36 hours. A football win gets a red "Rebels win!" banner.
- **How often ESPN is checked:** only from an hour before each game on the schedule until it's final, once a minute on the server, shared by every visitor. Nothing is fetched otherwise. In a baseball doubleheader, Grove follows the game closest to the scheduled time.
- **Which sports:** scores follow the sport names you use in `GAMEDAY_CALENDARS`: `football`, `basketball` (or `mbb`) for men's basketball, `womens-basketball` (or `wbb`), and `baseball`. Other sports still show on the schedule, just without live scores.
- **Team:** Grove looks for ESPN team id `145` (Ole Miss), or any team whose name contains "Ole Miss". Set `SCORES_TEAM_ID` if the id is ever different.

Live scores need each sport's schedule in `GAMEDAY_CALENDARS` to know when games are.

## Tonight in Oxford

The **Tonight in Oxford** card lists what's still on today (tonight's events first), then the next three days. Events whose title or description mention food (pizza, snacks, cookout, refreshments…) get a **Free food** tag, and a filter button shows only those.

Events come from calendar (.ics) links, the same way as game day. Campus event calendars and many Oxford venues and city calendars offer an "Export", "Subscribe" or "iCal" link. Set them as label=url pairs:
```
EVENTS_CALENDARS=campus=https://.../events.ics oxford=https://.../calendar.ics
```
The same event appearing in two feeds is shown once. The card stays hidden until at least one feed has events.

## My Classes

Students type their CRNs in **Settings → Your classes**. The **My Classes** card then shows their next class with a countdown and room ("CSCI 211 · 1:00 PM · Weir Hall 106"), the rest of today's classes, and a "Next:" line under the greeting. CRNs are saved only in the student's browser. `/api/classes` looks them up without storing anything.

Once a day the refresher reads every subject for the term from Ole Miss's public Banner class search, the same source RebelSnatch uses, and stores each section's days, times and room. Turn it on in Railway:
```
GROVE_TERM=202710        # Fall 2026; codes are YYYYTT: 10 Fall, 30 Spring, 50 Summer
```
The first run takes a few minutes, because requests are spaced a second apart to be polite to Banner. Change `GROVE_TERM` when a new semester starts. The card stays hidden until a term is set.

## Content you edit (grove/data)

Some cards are driven by small JSON files in `grove/data/`. Edit them on GitHub and Railway redeploys. A missing or broken file just counts as empty, so a typo can't take the site down. Cards with nothing in them stay hidden.

| File | What it's for | Example entry |
|---|---|---|
| `dining.json` | **Dining Open Now**: open now, "Closes in 20 min", when closed places reopen | `{"name": "Rebel Market", "menu_url": "https://…", "hours": {"mon": ["07:00-10:00", "11:00-20:00"], "sat": ["20:00-02:00"]}, "closed": ["2026-11-26"], "special": {"2026-11-25": ["07:00-14:00"]}}` |
| `academic_calendar.json` | **Countdowns** for students (shows dates in the next 120 days) | `{"name": "Last day to drop with a W", "date": "2026-10-30"}` |
| `moments.json` | Banner under the greeting for a date range; `"mode": "finals"` makes the study mode button pulse | `{"start": "2026-10-19", "end": "2026-10-24", "message": "It's Homecoming week!"}` |
| `trivia.json` | "Did you know?" line, one fact per day | `{"text": "The Lyceum, finished in 1848, is the oldest building on campus."}` |
| `gameday_info.json` | **Game-day info** on the Game Day card during home football game week (parking, shuttles, bag policy), plus a note for a specific game date. This file is an object, not a list. | `{"tips": [{"title": "Parking & shuttles", "text": "…", "url": "https://…"}], "notes": {"2026-10-10": "Homecoming game: arrive early."}}` |
| `square.json` | **On the Square**: one local business featured per week | `{"name": "…", "blurb": "…", "deal": "10% off with student ID", "url": "https://…"}` |

Each file except `gameday_info.json` holds a list (`[ … ]`) of entries like these. Dining hours use 24-hour `HH:MM-HH:MM` ranges in Oxford time. A range that ends before it starts, like `20:00-02:00`, runs past midnight. Days are `mon`–`sun`. `closed` lists dates with no service, and `special` replaces the usual hours on a date.

**Check every date, hour and fact against an official source before adding it.** The trivia facts that ship with Grove are well known, but confirm them too before launch.

## Campus photos

The background is a **photo of the day**. Everyone sees the same photo, and it changes at midnight in Oxford. Until any photos are added, the page uses a navy and cardinal gradient.

To add photos:
1. Put the image in `grove/static/photos/`. Use a landscape JPG about 2400px wide and under about 600 KB.
2. List it in `grove/static/photos/photos.json`:
   ```json
   [
     {"file": "grove-fall.jpg", "place": "The Grove", "credit": "Cody Chen"},
     {"file": "stadium.jpg", "place": "Vaught-Hemingway Stadium", "credit": "Jane Doe",
      "source_url": "https://www.flickr.com/photos/...", "license": "CC BY 2.0",
      "license_url": "https://creativecommons.org/licenses/by/2.0/", "resized": true}
   ]
   ```
   `place`, the credit and the license show in the corner of the page:
   - `credit_url` links the photographer's name to their page. Without it, the name links to `source_url`, the photo's own page.
   - For openly licensed photos (Creative Commons), always fill in `source_url`, `license` and `license_url`; the license requires them. Set `"resized": true` if you shrank the photo.

**Where to find photos:** [Openverse](https://openverse.org) with the "Use commercially" filter turned on. It searches Flickr and Wikimedia Commons and only shows photos you're allowed to use. Search "University of Mississippi", "Ole Miss", "Lyceum" or "Oxford Mississippi". Download the original file, not a screenshot.

**Only use photos you took or have written permission to use.** Most photos online, including the university's own, are copyrighted. Also avoid photos where the university's logos are the main subject. To collect photos from the community, make a form (for example a Google Form with a file upload and a "this is my photo" checkbox) and set `PHOTO_SUBMIT_URL` to its link. The About page then shows a **Submit a photo** button.

## Tests

```bash
python -m pytest -q
```

To also run the database tests against Postgres, set `TEST_DATABASE_URL` (for example `postgresql://localhost/grove_test`).

## Deploy on Railway

1. **New Project → Deploy from GitHub repo**, and pick `grove`.
2. In the same project, **+ New → Database → PostgreSQL**.
3. In the Grove service's **Variables**, add:
   ```
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   SEMESTER_START=2026-08-24
   SEMESTER_END=2026-12-11
   PHOTO_SUBMIT_URL=https://forms.gle/...   # optional
   ```
   Check the dates against the registrar's academic calendar.
4. `railway.json` runs `start.sh`, which starts the refresher in the background and the website with gunicorn. Railway health-checks `/healthz`.
5. **Settings → Networking**: generate a Railway domain, or add your own.

After a few minutes, the deploy logs should show `weather: updated` and `news: updated`.

If a widget stays on "Loading for the first time", look for a `! news failed:` line in the logs. The news feed URL is a guess until it's checked live; change it with `NEWS_FEEDS` (space-separated RSS or Atom URLs) without redeploying code.

## Chrome extension (new tab)

`extension/` is a small Chrome extension that makes Grove your new tab page. It shows the live site full-screen, so updates to the site reach everyone without a new extension release. Its only permission is `search`: the search bar uses the person's own default search engine through Chrome's `chrome.search` API. On the plain website, the search bar goes to Google. If the site can't be reached, the tab shows a clock and a "Try again" link instead of an error.

**Try it locally**
1. Run the site (`python -m flask --app grove.web run`). `extension/config.js` points at `http://127.0.0.1:5000` by default.
2. In Chrome, open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and pick the `extension` folder.
3. Open a new tab. Chrome asks once whether to keep the new tab change; choose **Keep it**.

**Publish it on the Chrome Web Store**
1. Deploy the site first. Then set `GROVE_URL` in `extension/config.js` to the live address, such as `https://grove.up.railway.app`.
2. Run `sh extension/build.sh`. It refuses to build while `config.js` still points at your own computer, and writes `grove-extension-<version>.zip`.
3. Register at the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole) (one-time $5 fee), click **New item**, and upload the zip.
4. Fill in the listing:
   - **Description:** "Your Ole Miss day on every new tab…"
   - **Category:** Productivity
   - **Screenshots:** at least one, 1280×800
   - **Privacy policy:** `https://<your site>/privacy`
   - **Data use:** check that it collects no user data.
5. Submit for review. It usually takes a few days.

For later releases, bump `version` in `manifest.json`, rebuild, and upload. You only need a new release when the extension itself changes, not the site.

## Adding a widget

1. Write `grove/pipelines/<name>.py` with a `fetch()` that returns JSON-friendly data. Keep the parsing in a separate `parse()` and test it against a saved sample in `tests/fixtures/`.
2. Register it in `PIPELINES` in `grove/refresh.py` with its refresh interval.
3. Add it to `WIDGETS` in `grove/widgets.py` (and `STALE_AFTER` if needed).
4. Add a renderer to `render` and an icon to `ICONS` in `grove/static/app.js`.

## Roadmap

Done: dashboard, photo of the day, weather, news, quick links, search, study mode, Chrome extension, Student/Fan/Alum mode, game day (schedule, game-day mode, kickoff forecast, game-day info, live scores), My Classes, Dining Open Now, Tonight in Oxford, countdowns, campus moments, trivia, snow day, On the Square.

Next:
1. Data sources to confirm and plug in: athletics `.ics` links, event calendars, dining hours, academic dates
2. O.U.T. bus arrivals (needs a public feed)
3. Dining menus (needs the dining provider's menu source)
4. "Ask the Grove" chat (OpenAI, with answers that cite their sources)
5. Home-screen app (PWA) and a photo-of-the-week vote
