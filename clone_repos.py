#!/usr/bin/env python3
"""
Clone all GitHub repositories for the authenticated user.
Works on macOS and Windows. Requires GitHub CLI (gh) to be installed and authenticated.
"""

import argparse
import json
import os
import subprocess
import sys
import webbrowser

GH_INSTALL_URL = "https://cli.github.com/"
TASK_NAME = "GithubClonerAgent-daily-pull"
# 2 AM EST = 7:00 UTC (cron uses UTC on most systems)
CRON_TIME_UTC = "7"  # hour for 0 7 * * *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_default_output_dir() -> str:
    """Programming folder: parent of GithubClonerAgent."""
    return os.path.dirname(SCRIPT_DIR)


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result. Works on Windows and Unix."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
    )


def gh_installed() -> bool:
    """Check if GitHub CLI is installed."""
    try:
        subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            check=False,
        )
        return True
    except FileNotFoundError:
        return False


def gh_authenticated() -> bool:
    """Check if GitHub CLI is logged in."""
    try:
        result = run_cmd(["gh", "auth", "status"], check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def prompt_install_gh() -> bool:
    """Tell user how to install gh, open install page; return False so script exits."""
    print("GitHub CLI (gh) is not installed.", file=sys.stderr)
    print("", file=sys.stderr)
    if sys.platform == "darwin":
        print("  Install with Homebrew:  brew install gh", file=sys.stderr)
    elif sys.platform == "win32":
        print("  Install with winget:    winget install GitHub.cli", file=sys.stderr)
        print("  Or download:            https://cli.github.com/", file=sys.stderr)
    else:
        print("  Install: https://cli.github.com/", file=sys.stderr)
    print("", file=sys.stderr)
    try:
        webbrowser.open(GH_INSTALL_URL)
        print("Opened install page in your browser.", file=sys.stderr)
    except Exception:
        print(f"Open in browser: {GH_INSTALL_URL}", file=sys.stderr)
    return False


def prompt_gh_login() -> bool:
    """Run gh auth login interactively. Returns True if login succeeded."""
    print("GitHub CLI is not logged in. Running: gh auth login", file=sys.stderr)
    print("", file=sys.stderr)
    ret = subprocess.run(
        ["gh", "auth", "login"],
        stdin=None,
        stdout=None,
        stderr=None,
    )
    return ret.returncode == 0


def ensure_gh_ready() -> bool:
    """Ensure gh is installed and authenticated. Prompt install or login as needed. Return True if ready."""
    if not gh_installed():
        return prompt_install_gh()
    if not gh_authenticated():
        if not prompt_gh_login():
            print("Login failed or was cancelled.", file=sys.stderr)
            return False
    return True


def get_repo_list(owner: str | None, limit: int) -> list[dict]:
    """Fetch list of repos via gh repo list. Returns list of {owner/name, clone_url}."""
    # gh repo list [owner] --limit N --json nameWithOwner,url,sshUrl
    args = ["gh", "repo", "list", "--limit", str(limit), "--json", "nameWithOwner,url,sshUrl"]
    if owner:
        args.insert(3, owner)
    result = run_cmd(args)
    data = json.loads(result.stdout)
    return [
        {"name": r["nameWithOwner"], "url": r["url"], "sshUrl": r.get("sshUrl", r["url"])}
        for r in data
    ]


def find_repo_dirs(output_dir: str) -> list[str]:
    """Return list of directories under output_dir that are git repos (have .git)."""
    repos = []
    try:
        for name in os.listdir(output_dir):
            path = os.path.join(output_dir, name)
            if os.path.isdir(path) and os.path.isdir(os.path.join(path, ".git")):
                repos.append(path)
    except OSError:
        pass
    return sorted(repos)


def pull_all_repos(output_dir: str) -> int:
    """Run git pull in every repo under output_dir. Return number of successes."""
    repos = find_repo_dirs(output_dir)
    if not repos:
        print("No git repositories found.")
        return 0
    ok = 0
    for path in repos:
        try:
            r = run_cmd(["git", "-C", path, "pull"], check=False)
            if r.returncode == 0:
                print(f"  pulled: {path}")
                ok += 1
            else:
                print(f"  failed: {path} ({r.stderr or r.stdout or 'pull failed'})", file=sys.stderr)
        except Exception as e:
            print(f"  error in {path}: {e}", file=sys.stderr)
    return ok


def setup_schedule_windows(output_dir: str) -> bool:
    """Create Windows scheduled task: daily at 2 AM (local time)."""
    python_exe = sys.executable
    script_py = os.path.join(SCRIPT_DIR, "clone_repos.py")
    cmd = f'"{python_exe}" "{script_py}" --pull-only -o "{output_dir}"'
    # Run at 2:00 AM local time (user should set timezone to Eastern for 2 AM EST)
    try:
        subprocess.run(
            [
                "schtasks", "/create", "/tn", TASK_NAME,
                "/tr", cmd,
                "/sc", "daily", "/st", "02:00",
                "/f",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        print("Scheduled task created: runs daily at 2:00 AM (local time).")
        print("  Set system timezone to Eastern for 2 AM EST.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to create scheduled task: {e.stderr or e}", file=sys.stderr)
        return False


def setup_schedule_mac(output_dir: str) -> bool:
    """Add cron job: daily at 2 AM EST (7 AM UTC)."""
    python_exe = sys.executable
    script_py = os.path.join(SCRIPT_DIR, "clone_repos.py")
    log_file = os.path.join(SCRIPT_DIR, "pull.log")
    # 0 7 * * * = 7:00 UTC = 2 AM EST
    cron_cmd = f'{python_exe} "{script_py}" --pull-only -o "{output_dir}" >> "{log_file}" 2>&1'
    cron_line = f"0 7 * * * {cron_cmd}"
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        existing = result.stdout if result.returncode == 0 else ""
        # Avoid duplicate
        if TASK_NAME in existing or "clone_repos.py" in existing and "--pull-only" in existing:
            print("Cron entry already present.")
            return True
        new_crontab = (existing.rstrip() + "\n" + cron_line + "\n").lstrip()
        proc = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"Failed to install crontab: {proc.stderr}", file=sys.stderr)
            return False
        print("Cron job added: runs daily at 2 AM EST (7:00 UTC).")
        print(f"  Log: {log_file}")
        return True
    except FileNotFoundError:
        print("crontab not found. Install cron or add the job manually.", file=sys.stderr)
        return False


def setup_schedule(output_dir: str) -> bool:
    """Install daily 2 AM pull schedule for current platform."""
    if sys.platform == "win32":
        return setup_schedule_windows(output_dir)
    if sys.platform == "darwin":
        return setup_schedule_mac(output_dir)
    print("Schedule setup is supported on Windows and macOS only.", file=sys.stderr)
    return False


def clear_schedule_windows() -> bool:
    """Remove the Windows scheduled task."""
    r = subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        print("Scheduled task removed.")
        return True
    err = (r.stderr or r.stdout or "").lower()
    if "cannot find" in err or "not found" in err or r.returncode == 1:
        print("No scheduled task found (already removed or never set).")
        return True
    print(f"Failed to remove task: {r.stderr or r.stdout}", file=sys.stderr)
    return False


def clear_schedule_mac() -> bool:
    """Remove the GithubClonerAgent cron job."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        existing = result.stdout if result.returncode == 0 else ""
        marker = "clone_repos.py"
        new_lines = [line for line in existing.splitlines() if marker not in line or "--pull-only" not in line]
        new_crontab = "\n".join(new_lines)
        if new_crontab.rstrip() != existing.rstrip():
            subprocess.run(
                ["crontab", "-"],
                input=new_crontab + "\n" if new_crontab else "",
                capture_output=True,
                text=True,
                check=True,
            )
            print("Cron job removed.")
        else:
            print("No cron job found (already removed or never set).")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to update crontab: {e.stderr or e}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("crontab not found.", file=sys.stderr)
        return False


def clear_schedule() -> bool:
    """Remove the daily pull schedule for current platform."""
    if sys.platform == "win32":
        return clear_schedule_windows()
    if sys.platform == "darwin":
        return clear_schedule_mac()
    print("Schedule clear is supported on Windows and macOS only.", file=sys.stderr)
    return False


def clone_repo(url: str, dest_dir: str, use_ssh: bool, dry_run: bool) -> bool:
    """Clone a single repo. Returns True on success."""
    if dry_run:
        print(f"  [dry run] would clone: {url} -> {dest_dir}")
        return True
    target = os.path.join(dest_dir, os.path.basename(url).replace(".git", ""))
    if os.path.isdir(target):
        print(f"  skip (exists): {target}")
        return True
    try:
        run_cmd(["git", "clone", url, target])
        print(f"  cloned: {target}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  error cloning {url}: {e.stderr or e}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clone all your GitHub repos. Requires 'gh' CLI (gh auth login)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be cloned; do not run git clone.",
    )
    parser.add_argument(
        "--pull-only",
        action="store_true",
        help="Only run 'git pull' in all repos under output dir (no clone).",
    )
    parser.add_argument(
        "--setup-schedule",
        action="store_true",
        help="Install daily scheduled task to pull all repos at 2 AM EST.",
    )
    parser.add_argument(
        "--clear-schedule",
        action="store_true",
        help="Remove the daily pull scheduled task or cron job.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Directory to clone/pull repos (default: Programming folder, parent of GithubClonerAgent).",
    )
    parser.add_argument(
        "--owner",
        default=None,
        help="GitHub user or org to list repos for (default: authenticated user).",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=1000,
        help="Max number of repos to fetch (default: 1000).",
    )
    parser.add_argument(
        "--ssh",
        action="store_true",
        help="Use SSH URL for clone (default: HTTPS).",
    )
    args = parser.parse_args()

    dest = os.path.abspath(args.output_dir or get_default_output_dir())

    if args.setup_schedule:
        return 0 if setup_schedule(dest) else 1

    if args.clear_schedule:
        return 0 if clear_schedule() else 1

    if args.pull_only:
        n = pull_all_repos(dest)
        print(f"Pulled {n} repo(s).")
        return 0

    if not ensure_gh_ready():
        return 1
    if not args.dry_run and not os.path.isdir(dest):
        os.makedirs(dest, exist_ok=True)

    print(f"Clone target: {dest}")
    print("Fetching repository list from GitHub...")
    try:
        repos = get_repo_list(args.owner, args.limit)
    except subprocess.CalledProcessError as e:
        print(f"Error listing repos: {e.stderr or e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not repos:
        print("No repositories found.")
        return 0

    print(f"Found {len(repos)} repo(s). {'[DRY RUN]' if args.dry_run else ''}")
    url_key = "sshUrl" if args.ssh else "url"
    ok = 0
    for r in repos:
        if clone_repo(r[url_key], dest, args.ssh, args.dry_run):
            ok += 1
    print(f"Done: {ok}/{len(repos)} repos.")
    return 0 if ok == len(repos) else 1


if __name__ == "__main__":
    sys.exit(main())
