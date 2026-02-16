# GithubClonerAgent

Clone all your GitHub repositories into the **Programming** folder (parent of `GithubClonerAgent`) and keep them updated. Cross-platform (macOS and Windows), with **dry run** and a **scheduled daily pull** at 2 AM EST.

## Requirements

- **Python 3.8+** (usually pre-installed on macOS; on Windows install from [python.org](https://www.python.org/downloads/))
- **GitHub CLI (`gh`)** — [Install guide](https://cli.github.com/) (script will prompt to install or log in)
- **Git** — [Install guide](https://git-scm.com/)

## Usage

```bash
cd GithubClonerAgent

# First time: clone all your repos into the Programming folder (script will prompt for gh install/login)
python clone_repos.py

# Dry run: show what would be cloned, no actual clones
python clone_repos.py --dry-run

# Set up a daily scheduled task: git pull all repos at 2 AM EST (run once per machine)
python clone_repos.py --setup-schedule

# Remove the scheduled task or cron job
python clone_repos.py --clear-schedule

# Manually pull all repos now (no gh needed)
python clone_repos.py --pull-only
```

**Default clone location:** Repos are cloned into the **Programming** folder (the parent of `GithubClonerAgent`). Use `-o path` to override.

### Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Only list repos that would be cloned; no `git clone` runs |
| `--pull-only` | Run `git pull` in every repo under the output dir (no clone, no gh) |
| `--setup-schedule` | Install daily 2 AM EST job to pull all repos (Windows: Task Scheduler; Mac: cron) |
| `--clear-schedule` | Remove the daily pull scheduled task or cron job |
| `-o`, `--output-dir` | Directory to clone/pull (default: Programming folder) |
| `--owner USER` | List repos for this user/org (default: authenticated user) |
| `-n`, `--limit N` | Max repos to fetch (default: 1000) |
| `--ssh` | Use SSH clone URLs instead of HTTPS |

## Scheduled pull (2 AM EST)

Keeps all cloned repos up to date so they're ready when you switch computers.

- **Windows:** Creates a scheduled task that runs daily at **2:00 AM** in your **system's local time**. Set your Windows timezone to **Eastern (EST/EDT)** for 2 AM EST.
- **macOS:** Adds a **cron** job that runs at **7:00 UTC** (= 2 AM Eastern).

Run once per machine after cloning:

```bash
python clone_repos.py --setup-schedule
```

- **Windows:** Task name: `GithubClonerAgent-daily-pull`. To remove:  
  `python clone_repos.py --clear-schedule` or  
  `schtasks /delete /tn GithubClonerAgent-daily-pull /f`
- **macOS:** Log file: `GithubClonerAgent/pull.log`. To remove:  
  `python clone_repos.py --clear-schedule` or edit with `crontab -e`.

## Mac vs Windows

- **macOS:** Use `python3 clone_repos.py` (or `python` if it's Python 3).
- **Windows:** Use `python clone_repos.py` from Command Prompt or PowerShell; if needed, try `py clone_repos.py`.

Repos that already exist are skipped when cloning. The scheduled job only runs `git pull` in existing repos.


