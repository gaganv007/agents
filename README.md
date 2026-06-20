# Gagan's Command Center

A set of **local** agents that handle day-to-day chores. No cloud, no
subscriptions, no API keys — except Gmail, which uses *your own* Google
credentials and never sends data anywhere but Google.

Everything runs on your Mac with Python 3. Each agent works standalone, or
you can launch them all from one menu.

## Quick start

```bash
cd ~/Desktop/agents
./cc                 # interactive menu (the Command Center)
```

Or run one agent directly:

```bash
./cc system          # system health report
./cc news            # world headlines
./cc files           # preview sorting Downloads
./cc briefing        # full morning summary
```

(`./cc` is a shortcut for `python3 command_center.py`.)

Or open the **web dashboard** — live system gauges, one-click agents with
streamed output, a **Reports** tab (browse the auto-generated HTML digests),
news, and the auto-run log:

```bash
./dashboard          # http://127.0.0.1:8765  (local only)
```

## The agents

| # | Agent | What it does | Changes things? |
|---|-------|--------------|-----------------|
| 1 | **Daily Briefing** | System health + news + file status in one shot | No |
| 2 | **System Analysis** | CPU, memory, disk, battery, top processes, health verdict | No |
| 3 | **Weather** | Current conditions + today's range (auto-located, no key) | No |
| 4 | **World News** | Top headlines from BBC, NPR, Al Jazeera, Reuters, Hacker News | No |
| 5 | **Health Check** | Alerts (with cooldown) on low disk / battery / memory | No |
| 6 | **File Sorter** | Organizes Downloads into Images/PDFs/Documents/… folders | Yes* |
| 7 | **Screenshot Organizer** | Moves screenshots into `~/Pictures/Screenshots/YYYY-MM` | Yes* |
| 8 | **Junk / Cache Cleaner** | Reclaims disk from caches, `node_modules`, `__pycache__` | Yes* (manual only) |
| 9 | **Disk Analyzer** | Finds your biggest files and folders | No |
| 10 | **Gmail AI Agent** | AI **triage**: sorts new mail + drafts replies (Claude) | Yes* (your inbox) |
| 11 | **Report** | Writes an HTML digest to `reports/` (auto every run) | No |
|   | **Auto Run** | Tidies files, triages Gmail, checks health, writes report — every 30 min | Yes |

\* **Safe by default.** Every changing agent runs a **preview first** and asks
for confirmation when run by hand. From the command line, add `--apply` to make
changes (e.g. `python3 tools/file_sorter.py --apply`).

### Gmail AI Agent (`./cc gmail`)

Powered by Claude (needs your Anthropic key — see below). On each run it looks
at **new unread mail only** (your existing backlog is ignored) and, for each
email, asks Claude to classify it and decide if a reply is genuinely expected:

- **spam / ads** → moved to **Spam**
- **orders** → **Orders** label (archived)
- **receipts / newsletters / social / notifications** → their own labels
- **recruiter / hiring / a real person asking something** → a **review-ready
  reply draft** is written by Claude and left in your Drafts. **Drafts are never
  sent** — you read and send them. Newsletters, ads, and automated mail never
  get a draft.

Category → action mapping is fully editable in `config.json`
(`gmail_sorter.triage.categories`).

Modes (`./cc gmail` menu, or `python3 tools/gmail_sorter.py <mode>`):
- **triage** — the above (what the scheduler runs every 30 min)
- **search** — any Gmail query, e.g. `... gmail_sorter.py search "from:amazon"`
- **test on last 24h** — triage recent real mail so you can see it work now
- **reset** — set "now" as the new starting point (re-ignore the backlog)

**Your Anthropic key** (required for triage). Put it in a git-ignored `.env`
file so the scheduled run can read it (launchd doesn't see your shell env):
```bash
cp .env.example .env        # then edit .env and paste your key
# or:  echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
```

## Configuration

All behavior is driven by [`config.json`](config.json) — edit it to change:

- Which folder File Sorter targets, and the category → extension mapping
- Which news feeds to pull (add/remove any RSS URL)
- Which cache/junk folders the cleaner scans
- Gmail triage: category → action map (label / archive / spam), signature, model

## Gmail setup (one time, ~5 minutes)

The Gmail Sorter needs an OAuth client so it can act on *your* account locally.

1. **Install libraries** (already done on this machine):
   ```bash
   pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
   ```
2. Go to <https://console.cloud.google.com/> → create a project (any name).
3. **APIs & Services → Library** → search "**Gmail API**" → **Enable**.
4. **APIs & Services → OAuth consent screen** → choose **External** → fill in
   app name + your email → add yourself under **Test users**.
5. **APIs & Services → Credentials → Create Credentials → OAuth client ID** →
   application type **Desktop app** → Create → **Download JSON**.
6. Save that file as `~/Desktop/agents/credentials.json`.
7. Run the agent:
   ```bash
   ./cc gmail
   ```
   The first `--apply` run opens a browser for sign-in, then caches a
   `token.json` so you won't sign in again.

After setup, add yourself under **Test users** on the OAuth consent screen and,
on first sign-in, click through **Advanced → Go to … (unsafe) → Allow** (normal
for a personal app using your own credentials).

`credentials.json`, `token.json`, and `.env` stay on your machine only — they're
git-ignored; never commit or share them.

## Automatic run, every 30 minutes (already set up)

A macOS `launchd` job runs the **Auto Run every 30 minutes** and notifies you
**only when it actually did something** (a quiet inbox stays quiet). Output is
logged to `briefing.log`.

The auto run does, unattended (`./cc auto` to run it by hand):

1. **File Sorter** — auto-organizes new Downloads
2. **Screenshot Organizer** — auto-files new screenshots
3. **Gmail AI triage** — sorts new mail (spam/ads → Spam, orders → Orders, …)
   and creates reply drafts where a reply is expected

**The Junk / Cache Cleaner is intentionally excluded** from automation — it
deletes data, so you always run it by hand (`./cc junk`). System Analysis and
World News are also on-demand only (`./cc system`, `./cc news`, or the dashboard).

The job is defined in:
`~/Library/LaunchAgents/com.gagan.commandcenter.briefing.plist`

**One-time permission (required):** macOS protects the Desktop folder, so the
scheduled job needs Full Disk Access for Python:

1. Open **System Settings → Privacy & Security → Full Disk Access**.
2. Click the **+** button (authenticate if asked).
3. In the file dialog press **Cmd+Shift+G**, paste:
   `/opt/anaconda3/bin/python3.12`  → Go → **Open**.
4. Make sure its toggle is **ON**. (No restart needed.)

Verify it works after granting access:
```bash
launchctl kickstart -k gui/$(id -u)/com.gagan.commandcenter.briefing
sleep 6 && tail -20 ~/Desktop/agents/briefing.log
```

Manage the schedule:
```bash
# change the interval: edit the plist's StartInterval (seconds), then reload:
launchctl bootout   gui/$(id -u) ~/Library/LaunchAgents/com.gagan.commandcenter.briefing.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gagan.commandcenter.briefing.plist

# turn the auto run off:
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.gagan.commandcenter.briefing.plist
```

## Files

```
agents/
├── cc                     # CLI launcher shortcut
├── dashboard              # web dashboard launcher
├── command_center.py      # the menu / dispatcher
├── server.py              # Flask web dashboard (http://127.0.0.1:8765)
├── common.py              # shared helpers (colors, config, secrets)
├── config.json            # all settings & rules
├── .env.example           # copy to .env and add your ANTHROPIC_API_KEY
├── requirements.txt
├── web/
│   └── index.html         # dashboard frontend
└── tools/
    ├── daily_auto.py         # the every-30-min routine
    ├── daily_briefing.py
    ├── system_analysis.py
    ├── world_news.py
    ├── file_sorter.py
    ├── screenshot_organizer.py
    ├── junk_cleaner.py
    ├── disk_analyzer.py
    └── gmail_sorter.py        # Gmail AI triage / search
```
