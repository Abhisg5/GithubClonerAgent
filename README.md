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
  "require_branch": "main"
}
```

Copy `config.example.json` to `config.json` and edit.

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
