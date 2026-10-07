# Grove

Grove is a daily home page for Ole Miss students and fans. It shows a campus photo of the day, a big greeting with your name, Oxford weather by the hour, campus news and quick links. Deadlines, dining, Rebels games, events and an "Ask the Grove" chat are coming next. It's inspired by Princeton's [Today](https://github.com/TigerAppsOrg/Today).

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

python -m grove.refresh --once                  # fetch weather and news once
python -m flask --app grove.web run --debug     # http://127.0.0.1:5000
```

Without `DATABASE_URL`, data goes into a local SQLite file, `grove.db`. Copy `.env.example` to `.env` to set the semester dates (for "Week N of the semester") or the news feeds.

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

1. ~~Dashboard, weather, news, quick links~~
2. Deadlines countdown, dining, Rebels athletics, events with a free-food tag, a RebelSnatch widget
3. "Ask the Grove" chat (OpenAI, with answers that cite their sources)
4. ~~Chrome new-tab extension~~; home-screen app, building hours, buses
