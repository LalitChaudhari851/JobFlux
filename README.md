# AI/ML Internship Scraper (Pune/PCMC)

Scrapes AI/ML/GenAI internship listings from public job portals, normalizes
relative post times ("6 hours ago", "1 week ago", etc.), finds publicly
listed company emails, validates them, and exports everything to a single
Excel file — sorted newest-first, with the most trustworthy emails on top.

## What it does

1. Searches Internshala, Naukri, and Wellfound for your keywords
2. Converts messy posted-time text ("6 hours ago" / "1 week ago" / "Just now")
   into real datetimes, and flags each listing as **Today / This Week / Older**
3. Visits each company's official website (`/careers`, `/contact`, `/about`)
   and pulls any email that's **already publicly displayed** — never guesses
   formats like `firstname.lastname@company.com`
4. Validates every email found:
   - Syntax check
   - MX record check (does the domain actually accept mail — catches dead/typo domains)
   - Domain-match check (flags an email whose domain doesn't match the company's real website — often a stale or wrong address)
5. Exports to `output/internship_leads.xlsx` with 3 sheets:
   - **Job Listings** — sorted newest-first
   - **Company Contacts** — only emails that passed MX validation
   - **Rejected_Unverified** — emails that failed a check, kept separately so you can manually double-check rather than losing them entirely

## Setup

```bash
cd ai_ml_internship_scraper
pip install -r requirements.txt
playwright install chromium
```

## Configure

Edit `config.json`:

- `search_keywords` — what to search for on each portal
- `seed_companies` — **important**: add companies here with their real website.
  The scraper only checks websites you give it (or that it can confidently
  infer) — it will not guess a company's domain from its name.
- `recency_window_days` — only keep listings posted within the last N days (default 7)
- `portals` — toggle which sites to scrape

## Run

```bash
python main.py
```

Results land in `output/internship_leads.xlsx`. Logs go to `output/scrape_log.txt`.

## Important notes

- **Selectors will need occasional updates.** Job portals change their HTML
  markup every few months. If a scraper suddenly returns 0 results, open the
  site in a real browser, inspect a listing card, and update the CSS
  selectors in the relevant file under `scrapers/`.
- **LinkedIn is intentionally excluded.** Scraping it violates their Terms
  of Service and gets IPs blocked quickly. Stick to Internshala/Naukri/Wellfound
  plus direct company sites.
- **robots.txt is respected automatically.** If a site's robots.txt disallows
  a page, the scraper skips it and logs a warning instead of proceeding.
- **No SMTP verification is performed.** Directly pinging a mail server to
  "confirm" an inbox exists is unreliable and can get your IP flagged as a
  spammer, so this tool stops at MX-record validation, which confirms the
  domain can receive mail without confirming the exact inbox.
- **Rate limiting is built in** (2-5s random delay between requests, capped
  requests per domain) — don't remove this, it's what keeps you from getting
  IP-blocked.
- The first time you run it, `tldextract` downloads a public suffix list
  over the network. If your environment blocks that specific request, it
  silently falls back to a bundled snapshot — results are unaffected.

## Extending

- Add more portals by creating a new file in `scrapers/` following the
  pattern in `internshala.py`, then registering it in `main.py`'s `portal_map`.
- Add more companies to `config.json`'s `seed_companies` list any time you
  find a new one worth tracking — the company-site email scraper will pick
  it up on the next run.

## Ethical use

This tool only collects information companies have already made public.
Please use it responsibly:
- Don't remove the rate-limiting/delay logic
- Don't scrape at high volume against any single company's site
- Use the emails only for genuine, relevant outreach (e.g. an internship
  application), not bulk/spam messaging
