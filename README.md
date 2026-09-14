# GST & Income Tax — Daily Notification Fetcher

Scrapes CBIC (GST) and CBDT (Income Tax) notification/circular listing pages once a day
and keeps a running JSON dataset + a static HTML digest page, entirely unattended —
**but only once you host it**. Neither GitHub nor this repo runs anything by itself
until you push it to your own GitHub account.

## What this is / isn't

- **Is:** a scheduled scraper + static site, running for free on GitHub Actions +
  GitHub Pages, no server to maintain.
- **Isn't:** an official feed. Neither CBIC nor the Income Tax Department publish a
  public API or RSS feed (checked — none exists as of Sep 2026). This reads their
  public HTML listing pages, which can and does break when those sites redesign.

## Setup (10 minutes, one-time)

1. Create a new **public GitHub repository** and push these files to it (`git init`,
   `git add .`, `git commit`, `git remote add origin ...`, `git push`).
2. In the repo, go to **Settings → Actions → General → Workflow permissions** and set
   it to "Read and write permissions" (needed so the workflow can commit updated data).
3. (Optional) Go to **Settings → Pages**, set source to the `docs/` folder on the
   `main` branch — this gives you a public URL like
   `https://<your-username>.github.io/<repo-name>/` showing the always-current digest.
4. That's it. The workflow in `.github/workflows/daily-fetch.yml` runs automatically
   every day at 03:00 UTC (08:30 IST). You can also trigger it manually anytime from
   the repo's **Actions** tab → "Daily GST & Income Tax notification fetch" → **Run workflow**.

## Files

| File | Purpose |
|---|---|
| `fetch_notifications.py` | The scraper. Fetches each URL in `SOURCES`, extracts rows, diffs against the previous run. |
| `notifications.json` | Full current dataset (all items scraped so far), machine-readable. |
| `new_today.json` | Only the items that are new since the last run — the file to check/alert on. |
| `docs/index.html` | Static digest page, published via GitHub Pages if you enable it. |
| `.github/workflows/daily-fetch.yml` | The GitHub Actions cron job. |

## Turning on email alerts (optional)

The workflow file has a commented-out step that emails you when `new_today.json` is
non-empty. To enable it: uncomment that block, and add three repo secrets under
**Settings → Secrets and variables → Actions**: `EMAIL_USERNAME`, `EMAIL_PASSWORD`
(use a Gmail **App Password**, not your normal password), and `EMAIL_TO`.

## Maintenance you should expect

- **Selectors will break eventually.** Government sites get redesigned without
  notice. If `docs/index.html` stops updating or `notifications.json` goes empty,
  open the source URL in a browser, inspect the table markup, and update the
  `row_selector` / parsing logic in `fetch_notifications.py` accordingly. The
  script prints a `[warn]` line when a source returns zero items, so check the
  Actions run logs first.
- **This is a best-effort extraction**, not a structured API — the parser guesses
  which cell is a date and which is the subject line. Spot-check `notifications.json`
  after setup and after any selector update.
- **Always verify against the primary source** before relying on any item for a
  filing or compliance position — treat this as an alerting/awareness tool, not
  a source of legal record.

## Adding more sources

Add an entry to the `SOURCES` list in `fetch_notifications.py` with an `id`,
`category` ("GST" or "Income Tax"), `label`, `url`, and `row_selector` (a CSS
selector for the table rows on that page). The generic row parser should handle
most plain-HTML government tables without further changes.
