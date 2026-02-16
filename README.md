# GithubClonerAgent

Clone and sync all your GitHub repositories into one folder (default: **Programming**, parent of `GithubClonerAgent`). Cross-platform (macOS and Windows). The scheduled job runs a **full sync** at 2 AM EST: clone any new repos and pull existing ones so everything stays updated across machines.

## Requirements

- **Python 3.8+** (usually pre-installed on macOS; on Windows install from [python.org](https://www.python.org/downloads/))
- **GitHub CLI (`gh`)** — [Install guide](https://cli.github.com/) (script will prompt to install or log in)
- **Git** — [Install guide](https://git-scm.com/)

## Usage

```bash
cd GithubClonerAgent

# Sync: clone any missing repos + pull existing (what the 2 AM job runs)
python clone_repos.py --sync

# First-time clone only (no pull)
python clone_repos.py

# List repos from GitHub (with your filters), no clone
python clone_repos.py --list

# Status: branch, ahead/behind, dirty for each repo
python clone_repos.py --status

# Dry run: show what would be cloned
python clone_repos.py --dry-run

# Set up daily 2 AM EST sync (clone new + pull existing)
python clone_repos.py --setup-schedule

# Remove the scheduled task or cron job
python clone_repos.py --clear-schedule

# Pull only (no new clones, no gh needed)
python clone_repos.py --pull-only
```

**Default location:** Repos go in the **Programming** folder. Override with `-o path` or a `config.json` (see below).

### Options

| Option | Description |
|--------|-------------|
| `--sync` | Clone missing repos and pull existing (default for scheduled job) |
| `--list` | List repo names from GitHub (with filters); no clone/pull |
| `--status` | Show branch, ahead/behind, dirty for each repo in output dir |
| `--dry-run` | Show what would be cloned; no `git clone` |
| `--pull-only` | Only `git pull` in existing repos (no clone, no gh) |
| `--setup-schedule` | Install daily 2 AM EST **sync** (clone new + pull) |
| `--clear-schedule` | Remove the scheduled task or cron job |
| `-o`, `--output-dir` | Clone/sync directory (default: config or Programming folder) |
| `--owner USER` | List repos for this user/org |
| `-n`, `--limit N` | Max repos to fetch (default: 1000) |
| `--no-archived` | Skip archived repositories |
| `--exclude PATTERNS` | Comma-separated globs to exclude (e.g. `old-*,deprecated-*`) |
| `--only PATTERNS` | Comma-separated globs to include only (e.g. `my-*`) |
| `--shallow` | Clone with `--depth 1` for faster first clone |
| `--jobs N` | Parallel clone jobs (default: 1) |
| `--require-branch BRANCH` | In `--status`, warn when repo is not on this branch (e.g. `main`) |
| `--ssh` | Use SSH clone URLs |

## Email notification (Mac and Windows)

When the 2 AM sync (or a manual `--sync` / `--pull-only`) finishes, you can get an email with a short summary (e.g. *"Cloned: 2, Pulled: 15"*). Same behavior on **macOS and Windows**.

1. Copy `config.example.json` to `config.json`.
2. Set **notify_email**, **smtp_host**, **smtp_port**, **smtp_user**. For the password, use one of: **smtp_password** in the file, env var **GITHUB_CLONER_AGENT_SMTP_PASSWORD**, or **smtp_password_gist_raw_url** (see below) so the script fetches it from a secret gist at runtime.
3. Run `--setup-schedule` as usual. The scheduled job reads `config.json`; when it finishes, it sends the email if SMTP is configured.

**Example (Gmail):** Use an [App Password](https://support.google.com/accounts/answer/185833) (not your normal password). In `config.json`: `smtp_host`: `smtp.gmail.com`, `smtp_port`: `587`, `smtp_user`: your Gmail, `notify_email`: the address to receive the summary (can be the same), and put the app password in `smtp_password` or in `GITHUB_CLONER_AGENT_SMTP_PASSWORD`.

## Config file

Optional `config.json` in the `GithubClonerAgent` folder sets defaults (CLI flags still override):

```json
{
  "output_dir": "/path/to/repos",
  "limit": 1000,
  "no_archived": true,
  "exclude": "old-*,deprecated-*",
  "only": "",
  "shallow": false,
  "jobs": 2,
  "require_branch": "main",
  "notify_email": "you@example.com",
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "your@gmail.com",
  "smtp_from": "",
  "smtp_password": "",
  "smtp_password_gist_raw_url": ""
}
```

- **smtp_password:** Leave empty if you use the env var or gist.
- **GITHUB_CLONER_AGENT_SMTP_PASSWORD:** Set in the environment to supply the password without putting it in the file.
- **smtp_password_gist_raw_url:** Optional. The **Raw** URL of a secret gist whose only content is the app password (e.g. `https://gist.githubusercontent.com/USER/GIST_ID/raw/gistfile1.txt`). The script fetches it at runtime so you don’t set the env var on each machine. Keep this URL only in `config.json` (never commit it). Copy `config.example.json` to `config.json` and edit.

### Keeping the SMTP password secret (public repo + multiple computers)

The repo can stay **public** and your app password stays **private**:

1. **Never commit the password.**  
   `config.json` is in `.gitignore`, so it never gets pushed. In `config.json`, leave `smtp_password` empty (`""`).

2. **Use the environment variable.**  
   Set your app password in **GITHUB_CLONER_AGENT_SMTP_PASSWORD** (not in any file). The script reads it at runtime.

3. **Store the password and use it on each computer:**
   - **Option A – Gist (auto-fetch):** Put the app password in a **secret gist** (one file, content = password only). In `config.json` set **smtp_password_gist_raw_url** to that gist’s **Raw** URL (e.g. `https://gist.githubusercontent.com/USER/GIST_ID/raw/filename.txt`). The script will fetch the password from the gist when it runs. No env var needed. Keep the URL only in `config.json` (gitignored); never commit it.
   - **Option B – Env var:** Set **GITHUB_CLONER_AGENT_SMTP_PASSWORD** on each machine. Store the password in a password manager or a private gist and copy it when setting up a new computer.

4. **Set the env var on each machine** so the script (and the 2 AM scheduled task) can use it:
   - **Windows:**  
     `System Properties` → `Advanced` → `Environment Variables` → under “User variables” add `GITHUB_CLONER_AGENT_SMTP_PASSWORD` = your app password.  
     Or in PowerShell (current user, persistent):  
     `[System.Environment]::SetEnvironmentVariable('GITHUB_CLONER_AGENT_SMTP_PASSWORD', 'your-app-password', 'User')`  
     Restart the terminal (and ensure the scheduled task runs as the same user so it sees the variable).
   - **macOS:**  
     Add to `~/.zshrc` or `~/.bash_profile`:  
     `export GITHUB_CLONER_AGENT_SMTP_PASSWORD='your-app-password'`  
     Then `source ~/.zshrc` (or reopen the terminal). Cron runs with your user, so it will see this if you use a login shell or set it in your profile.

After that you can push the repo to GitHub as public; the app password only exists in your env and in your private gist or password manager.

## Scheduled sync (2 AM EST)

The scheduled job runs **full sync**: clone any new repos and pull all existing ones so everything is up to date when you switch computers.

- **Windows:** Task runs daily at **2:00 AM** local time. Set timezone to Eastern for 2 AM EST.
- **macOS:** Cron runs at **7:00 UTC** (= 2 AM Eastern). Log: `GithubClonerAgent/sync.log`.

Setup once per machine:

```bash
python clone_repos.py --setup-schedule
```

- **Windows:** Task name `GithubClonerAgent-daily-pull`. Remove: `python clone_repos.py --clear-schedule` or `schtasks /delete /tn GithubClonerAgent-daily-pull /f`
- **macOS:** Remove: `python clone_repos.py --clear-schedule` or `crontab -e`

## Mac vs Windows

- **macOS:** `python3 clone_repos.py` (or `python` if Python 3).
- **Windows:** `python clone_repos.py` or `py clone_repos.py`.

Existing repos are skipped when cloning; `--sync` updates them with `git pull`.
