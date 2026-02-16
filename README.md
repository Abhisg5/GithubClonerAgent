# GithubClonerAgent

Keep all your GitHub repos in one folder, in sync across machines. Clone missing repos, pull existing ones, and optionally commit local changes to a `feature/YYYY-MM-DD-DEVICE` branch and open a PR to `main`. Runs on **macOS and Windows**; supports a daily 2 AM local-time job with wake/sleep automation and email summaries.

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

This clones any repos you don’t have yet, pulls the rest, and for any repo with uncommitted changes: creates `feature/YYYY-MM-DD-DEVICE`, commits, pushes, and opens a PR to `main`. Repos are placed in the **Programming** folder (parent of `GithubClonerAgent`) unless you set `-o` or `config.json`.

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
| `python clone_repos.py --setup-schedule` | Install daily 2 AM local-time task (clone + pull + commit/PR) with wake/sleep behavior. |
| `python clone_repos.py --clear-schedule` | Remove the 2 AM scheduled task (and legacy cron entry on macOS). |
| `python clone_repos.py --test-schedule-now` | Run the scheduled runner immediately (`--sync`, then request sleep). |

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
3. **Commit & PR:** For each repo with uncommitted changes, create branch `feature/YYYY-MM-DD-DEVICE` (device = hostname, sanitized), commit all changes, push, and open a PR into `main`. Repos with no changes are left alone.
4. **Email** (if configured): send a summary (cloned, pulled, committed, PR links, errors).

- **Windows:** Uses Task Scheduler with wake support where available.  
  Registers task to run whether user is logged on or not (S4U).  
  Task name: `GithubClonerAgent-daily-pull`.  
  Creates runner: `GithubClonerAgent/run_sync_windows.cmd` (runs sync, then requests sleep).
- **macOS:** Uses `launchd` at **2:00 AM local time** plus a wake timer attempt at **1:58 AM**.  
  Creates runner: `GithubClonerAgent/run_sync_mac.sh` (runs sync, then requests sleep).  
  Log: `GithubClonerAgent/sync.log`.

**Setup (once per machine):**

```bash
python clone_repos.py --setup-schedule
```

**Test immediately (without waiting for 2 AM):**

```bash
python clone_repos.py --test-schedule-now
```

**Remove:**

```bash
python clone_repos.py --clear-schedule
```

Or: **Windows** — `schtasks /delete /tn GithubClonerAgent-daily-pull /f`  
**macOS** — `launchctl unload ~/Library/LaunchAgents/com.githubcloneragent.daily-sync.plist && rm ~/Library/LaunchAgents/com.githubcloneragent.daily-sync.plist`

If wake timer was added on macOS and you want to remove it too:

```bash
sudo pmset repeat cancel
```

---

### Sleep/Wake behavior notes

- A sleeping computer cannot execute jobs until it wakes.
- **Windows:** `--setup-schedule` first tries a wake-capable task (`WakeToRun`, `StartWhenAvailable`). If that is unavailable, it falls back to basic `schtasks`.
- **macOS:** `--setup-schedule` installs a LaunchAgent and tries to set wake with `pmset repeat wakeorpoweron MTWRFSU 01:58:00`.
- If macOS wake timer setup needs privileges, run this once manually:

```bash
sudo pmset repeat wakeorpoweron MTWRFSU 01:58:00
```

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

### Setting the SMTP password environment variable

If you use **`GITHUB_CLONER_AGENT_SMTP_PASSWORD`** instead of a gist or `smtp_password` in config:

**Windows (persistent for your user; 2 AM task will see it):**

1. Open **Settings** → **System** → **About** → **Advanced system settings** → **Environment Variables**.
2. Under **User variables**, click **New**.
3. Variable name: `GITHUB_CLONER_AGENT_SMTP_PASSWORD`  
   Variable value: your app password (e.g. Gmail app password).
4. OK out. Restart any open terminals (and the 2 AM scheduled task runs as your user, so it will pick this up after next login or reboot).

**Or in PowerShell (current user, persistent):**

```powershell
[System.Environment]::SetEnvironmentVariable('GITHUB_CLONER_AGENT_SMTP_PASSWORD', 'your-app-password-here', 'User')
```

Restart the terminal (or reboot) so the 2 AM task sees the variable.

**macOS (persistent for your user; scheduler run will use this if set in your login environment):**

1. Edit your shell config (e.g. `~/.zshrc` or `~/.bash_profile`):
   ```bash
   echo 'export GITHUB_CLONER_AGENT_SMTP_PASSWORD="your-app-password-here"' >> ~/.zshrc
   ```
2. Reload: `source ~/.zshrc` (or open a new terminal).
3. If the scheduler cannot see your env var, prefer putting the SMTP password in `config.json` via `smtp_password_gist_raw_url`, or configure user-level launch environment so your 2 AM job inherits it.

**Or for the current terminal only (temporary):**

- **Windows (CMD):** `set GITHUB_CLONER_AGENT_SMTP_PASSWORD=your-app-password`
- **Windows (PowerShell):** `$env:GITHUB_CLONER_AGENT_SMTP_PASSWORD = 'your-app-password'`
- **macOS/Linux:** `export GITHUB_CLONER_AGENT_SMTP_PASSWORD='your-app-password'`

---

## Keeping the SMTP password secret (public repo)

- **Do not commit** `config.json` (it’s gitignored).
- Prefer **`smtp_password_gist_raw_url`** (secret gist) or **`GITHUB_CLONER_AGENT_SMTP_PASSWORD`** so the password is never in the repo.
- On each new machine: copy `config.example.json` to `config.json`, fill in options and (if you use it) the gist URL. For env var: set `GITHUB_CLONER_AGENT_SMTP_PASSWORD` as above so the 2 AM task can use it.

---

## Platform

- **Windows:** `python clone_repos.py` or `py clone_repos.py`
- **macOS:** `python3 clone_repos.py` or `python clone_repos.py`

Email works the same on both. Scheduler uses Task Scheduler on Windows and LaunchAgent on macOS.
