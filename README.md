# GithubClonerAgent

Keep all your GitHub repos in one folder, in sync across machines. Clone missing repos, pull existing ones, and optionally commit local changes to a `feature/YYYY-MM-DD` branch and open a PR to `main`. Runs on **macOS and Windows**; supports a daily 2 AM EST job and email summaries.

**All commands operate only on repos from your GitHub account** (via `gh repo list`). Other folders in the output directory (e.g. local-only projects) are ignored.

---

## Requirements

- **Python 3.8+**
- **Git**
- **GitHub CLI (`gh`)** — [cli.github.com](https://cli.github.com/)  
  The script will prompt you to install or log in if needed.

---

## Quick start

```bash
cd GithubClonerAgent
python clone_repos.py --sync
```

This clones any repos you don’t have yet, pulls the rest, and for any repo with uncommitted changes: creates `feature/YYYY-MM-DD`, commits, pushes, and opens a PR to `main`. Repos are placed in the **Programming** folder (parent of `GithubClonerAgent`) unless you set `-o` or `config.json`.

---

## Commands

| Command | What it does |
|--------|----------------|
| `python clone_repos.py --sync` | Clone missing repos, pull existing, then commit local changes to `feature/date` and open PRs. Same as the 2 AM job. |
| `python clone_repos.py` | Clone-only: fetch repo list and clone any missing (no pull, no commit/PR). |
| `python clone_repos.py --pull-only` | Pull only in repos that are in your GitHub list (no clone, no commit/PR). |
| `python clone_repos.py --status` | Show branch, ahead/behind, and dirty state for each repo in your GitHub list. |
| `python clone_repos.py --list` | Print repo names from GitHub (with your filters). No disk changes. |
| `python clone_repos.py --dry-run` | Show what would be cloned; no clone/pull/commit. |
| `python clone_repos.py --setup-schedule` | Install daily 2 AM EST task (clone + pull + commit/PR). |
| `python clone_repos.py --clear-schedule` | Remove the 2 AM scheduled task or cron job. |

---

## Options

| Option | Description |
|--------|-------------|
| `-o`, `--output-dir PATH` | Where to clone/pull (default: parent of `GithubClonerAgent`, or `config.json`). |
| `--owner USER` | List repos for this user/org (default: you). |
| `-n`, `--limit N` | Max repos to consider (default: 1000). |
| `--no-archived` | Skip archived repos. |
| `--exclude PATTERNS` | Comma-separated globs to exclude (e.g. `old-*,deprecated-*`). |
| `--only PATTERNS` | Comma-separated globs to include only (e.g. `my-*`). |
| `--shallow` | Clone with `--depth 1`. |
| `--jobs N` | Parallel clone/pull jobs (default: 1). |
| `--require-branch BRANCH` | In `--status`, warn when repo is not on this branch (e.g. `main`). |
| `--ssh` | Use SSH clone URLs. |

---

## 2 AM scheduled job

The scheduled run does a **full sync**:

1. **Clone** any repos you don’t have locally.
2. **Pull** all existing repos from your GitHub list.
3. **Commit & PR:** For each repo with uncommitted changes, create branch `feature/YYYY-MM-DD`, commit all changes, push, and open a PR into `main`. Repos with no changes are left alone.
4. **Email** (if configured): send a summary (cloned, pulled, committed, PR links, errors).

- **Windows:** Task runs at **2:00 AM** local time. Set timezone to Eastern for 2 AM EST.  
  Task name: `GithubClonerAgent-daily-pull`.
- **macOS:** Cron at **7:00 UTC** (= 2 AM Eastern). Log: `GithubClonerAgent/sync.log`.

**Setup (once per machine):**

```bash
python clone_repos.py --setup-schedule
```

**Remove:**

```bash
python clone_repos.py --clear-schedule
```

Or: **Windows** — `schtasks /delete /tn GithubClonerAgent-daily-pull /f`  
**macOS** — `crontab -e` and delete the line with `clone_repos.py --sync`.

---

## Config file

Copy `config.example.json` to `config.json` in the `GithubClonerAgent` folder. CLI flags override config.

| Key | Description |
|-----|-------------|
| `output_dir` | Default clone/pull directory (empty = parent of `GithubClonerAgent`). |
| `limit` | Max repos (default 1000). |
| `no_archived` | Skip archived repos. |
| `exclude` | Comma-separated globs to exclude. |
| `only` | Comma-separated globs to include only. |
| `shallow` | Use shallow clone. |
| `jobs` | Parallel clone/pull jobs. |
| `require_branch` | Branch to warn about in `--status` (e.g. `main`). |
| `notify_email` | Email address to receive run summaries. |
| `smtp_host`, `smtp_port`, `smtp_user` | SMTP server (e.g. Gmail: `smtp.gmail.com`, 587). |
| `smtp_from` | From address (default: `smtp_user`). |
| `smtp_password` | Leave empty if using env or gist (see below). |
| `smtp_password_gist_raw_url` | Raw URL of a **secret gist** whose only content is the SMTP app password; script fetches it at runtime. |

`config.json` is in `.gitignore` and is never committed.

---

## Email notification

After a **sync** or **pull-only** run, the script can send one email with:

- Device (hostname, OS, user)
- Time (UTC)
- Output directory
- Counts: cloned, pulled, committed, PRs created, failed
- Lists: repos cloned, pulled, committed, PR URLs, pull/commit errors

**Setup:**

1. In `config.json`: set `notify_email`, `smtp_host`, `smtp_port`, `smtp_user`.
2. For the password, use **one** of:
   - **Gist:** Put the app password in a **secret gist** (one file, content = password). Set `smtp_password_gist_raw_url` to that gist’s **Raw** URL. The script fetches it when it runs. Keep the URL only in `config.json` (do not commit).
   - **Env var:** Set `GITHUB_CLONER_AGENT_SMTP_PASSWORD` in the environment. No password in any file.
   - **File:** Set `smtp_password` in `config.json` (not recommended if the repo is public).

**Gmail:** Use an [App Password](https://support.google.com/accounts/answer/185833) with 2FA. `smtp_host`: `smtp.gmail.com`, `smtp_port`: `587`.

---

## Keeping the SMTP password secret (public repo)

- **Do not commit** `config.json` (it’s gitignored).
- Prefer **`smtp_password_gist_raw_url`** (secret gist) or **`GITHUB_CLONER_AGENT_SMTP_PASSWORD`** so the password is never in the repo.
- On each new machine: copy `config.example.json` to `config.json`, fill in options and (if you use it) the gist URL. For env var: set `GITHUB_CLONER_AGENT_SMTP_PASSWORD` in the system/user environment so the 2 AM task can use it.

---

## Platform

- **Windows:** `python clone_repos.py` or `py clone_repos.py`
- **macOS:** `python3 clone_repos.py` or `python clone_repos.py`

Schedule and email work the same on both; only the 2 AM trigger differs (Task Scheduler vs cron).
