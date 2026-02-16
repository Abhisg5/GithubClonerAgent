#!/usr/bin/env python3
"""
Clone all GitHub repositories for the authenticated user.
Works on macOS and Windows. Requires GitHub CLI (gh) to be installed and authenticated.
"""

import argparse
import fnmatch
import json
import os
import platform
import smtplib
import ssl
import subprocess
import sys
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GH_INSTALL_URL = "https://cli.github.com/"
TASK_NAME = "GithubClonerAgent-daily-pull"
# 2 AM EST = 7:00 UTC (cron uses UTC on most systems)
CRON_TIME_UTC = "7"  # hour for 0 7 * * *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = "config.json"


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


def load_config() -> dict:
    """Load optional config.json from script dir. Returns dict of options (empty if missing)."""
    path = os.path.join(SCRIPT_DIR, CONFIG_FILE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def apply_filters(
    repos: list[dict],
    exclude: list[str],
    only: list[str],
) -> list[dict]:
    """Filter repos by --exclude and --only glob patterns on nameWithOwner."""
    out = []
    for r in repos:
        name = r["name"]
        if only:
            if not any(fnmatch.fnmatch(name, p.strip()) for p in only):
                continue
        if exclude:
            if any(fnmatch.fnmatch(name, p.strip()) for p in exclude):
                continue
        out.append(r)
    return out


def get_repo_list(
    owner: str | None,
    limit: int,
    no_archived: bool = False,
    exclude: list[str] | None = None,
    only: list[str] | None = None,
) -> list[dict]:
    """Fetch list of repos via gh repo list. Returns list of {name, url, sshUrl}."""
    json_fields = "nameWithOwner,url,sshUrl"
    if no_archived:
        json_fields += ",isArchived"
    args = ["gh", "repo", "list", "--limit", str(limit), "--json", json_fields]
    if owner:
        args.insert(3, owner)
    result = run_cmd(args)
    data = json.loads(result.stdout)
    repos = []
    for r in data:
        if no_archived and r.get("isArchived"):
            continue
        repos.append({
            "name": r["nameWithOwner"],
            "url": r["url"],
            "sshUrl": r.get("sshUrl", r["url"]),
        })
    return apply_filters(repos, exclude or [], only or [])


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


def _pull_one(path: str) -> tuple[str, bool, str]:
    """Run git pull in one repo. Returns (basename, success, error_message)."""
    name = os.path.basename(path)
    try:
        r = run_cmd(["git", "-C", path, "pull"], check=False)
        if r.returncode == 0:
            return (name, True, "")
        err = (r.stderr or r.stdout or "pull failed").strip().split("\n")[0][:200]
        return (name, False, err)
    except Exception as e:
        return (name, False, str(e)[:200])


def pull_all_repos(
    output_dir: str,
    jobs: int = 1,
    only_repo_names: set[str] | None = None,
) -> tuple[int, list[str], list[tuple[str, str]]]:
    """Run git pull. If only_repo_names is set, only pull those (from your GitHub list); else all git dirs."""
    repos = find_repo_dirs(output_dir)
    if only_repo_names is not None:
        repos = [p for p in repos if os.path.basename(p) in only_repo_names]
    if not repos:
        print("No git repositories found.")
        return 0, [], []
    pulled_names: list[str] = []
    failed: list[tuple[str, str]] = []
    if jobs <= 1:
        for path in repos:
            name, ok, err = _pull_one(path)
            if ok:
                print(f"  pulled: {path}")
                pulled_names.append(name)
            else:
                print(f"  failed: {path} ({err})", file=sys.stderr)
                failed.append((name, err))
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futures = {ex.submit(_pull_one, path): path for path in repos}
            for fut in as_completed(futures):
                name, ok, err = fut.result()
                if ok:
                    print(f"  pulled: {futures[fut]}")
                    pulled_names.append(name)
                else:
                    print(f"  failed: {os.path.join(output_dir, name)} ({err})", file=sys.stderr)
                    failed.append((name, err))
    return len(pulled_names), pulled_names, failed


def setup_schedule_windows(output_dir: str) -> bool:
    """Create Windows scheduled task: daily at 2 AM (local time). Runs full sync (clone new + pull)."""
    python_exe = sys.executable
    script_py = os.path.join(SCRIPT_DIR, "clone_repos.py")
    cmd = f'"{python_exe}" "{script_py}" --sync -o "{output_dir}"'
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
    """Add cron job: daily at 2 AM EST (7 AM UTC). Runs full sync (clone new + pull)."""
    python_exe = sys.executable
    script_py = os.path.join(SCRIPT_DIR, "clone_repos.py")
    log_file = os.path.join(SCRIPT_DIR, "sync.log")
    # 0 7 * * * = 7:00 UTC = 2 AM EST
    cron_cmd = f'{python_exe} "{script_py}" --sync -o "{output_dir}" >> "{log_file}" 2>&1'
    cron_line = f"0 7 * * * {cron_cmd}"
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        existing = result.stdout if result.returncode == 0 else ""
        # Avoid duplicate (match --sync or legacy --pull-only)
        if TASK_NAME in existing or ("clone_repos.py" in existing and ("--sync" in existing or "--pull-only" in existing)):
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
    """Install daily 2 AM sync schedule for current platform. Email notification via config if set."""
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
        new_lines = [
            line for line in existing.splitlines()
            if marker not in line or ("--sync" not in line and "--pull-only" not in line)
        ]
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


def _fetch_password_from_gist(raw_url: str) -> str:
    """Fetch password from a secret gist raw URL. Returns stripped content or empty string on failure."""
    try:
        req = urllib.request.Request(raw_url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
            return body
    except Exception:
        return ""


def send_notification_email(config: dict, subject: str, body: str) -> bool:
    """Send an email using config SMTP settings. Returns True on success. Mac and Windows."""
    to_email = config.get("notify_email", "").strip()
    if not to_email:
        return False
    host = config.get("smtp_host", "").strip()
    user = config.get("smtp_user", "").strip()
    password = (
        (config.get("smtp_password") or "").strip()
        or os.environ.get("GITHUB_CLONER_AGENT_SMTP_PASSWORD", "").strip()
    )
    if not password and config.get("smtp_password_gist_raw_url"):
        password = _fetch_password_from_gist(config.get("smtp_password_gist_raw_url", "").strip())
    if not host or not user or not password:
        print("Email not sent: set notify_email, smtp_host, smtp_user, and smtp_password (or env GITHUB_CLONER_AGENT_SMTP_PASSWORD or smtp_password_gist_raw_url) in config.json.", file=sys.stderr)
        return False
    port = int(config.get("smtp_port", 587))
    from_email = config.get("smtp_from") or user
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))
    try:
        # Use unverified context to avoid SSL cert strictness errors (e.g. Basic Constraints) on Windows
        context = ssl._create_unverified_context()
        with smtplib.SMTP(host, port) as server:
            server.starttls(context=context)
            server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())
        print("Notification email sent.")
        return True
    except Exception as e:
        print(f"Failed to send notification email: {e}", file=sys.stderr)
        return False


def get_device_info() -> str:
    """Return a short description of this machine for notification emails."""
    host = platform.node() or "unknown"
    system = platform.system()
    release = platform.release()
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    return f"{host} ({system} {release}) — user: {user}"


def build_notification_body(
    sync_type: str,
    output_dir: str,
    cloned: int,
    pulled: int,
    cloned_names: list[str],
    pulled_names: list[str],
    failed: list[tuple[str, str]] | None = None,
    committed_names: list[str] | None = None,
    prs: list[tuple[str, str]] | None = None,
    commit_errors: list[tuple[str, str]] | None = None,
) -> str:
    """Build a descriptive email body for debugging."""
    failed = failed or []
    committed_names = committed_names or []
    prs = prs or []
    commit_errors = commit_errors or []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    device = get_device_info()
    lines = [
        "GithubClonerAgent run finished",
        "",
        "--- Device ---",
        device,
        "",
        "--- When ---",
        now,
        "",
        "--- Output directory ---",
        output_dir,
        "",
    ]
    if sync_type == "sync":
        lines.extend([
            "--- Summary ---",
            f"Cloned: {cloned} repo(s)",
            f"Pulled: {pulled} repo(s)",
            f"Committed (local changes → feature/date): {len(committed_names)} repo(s)",
            f"PRs created: {len(prs)}",
        ])
        if failed:
            lines.append(f"Pull failed: {len(failed)} repo(s)")
        if commit_errors:
            lines.append(f"Commit/PR errors: {len(commit_errors)} repo(s)")
        lines.append("")
        if cloned_names:
            lines.append("--- Repos cloned ---")
            lines.extend(f"  • {n}" for n in sorted(cloned_names))
            lines.append("")
        if pulled_names:
            lines.append("--- Repos pulled ---")
            lines.extend(f"  • {n}" for n in sorted(pulled_names))
            lines.append("")
        if committed_names:
            lines.append("--- Committed (pushed to feature/date branch) ---")
            lines.extend(f"  • {n}" for n in sorted(committed_names))
            lines.append("")
        if prs:
            lines.append("--- PRs created (feature/date → main) ---")
            for name, url in sorted(prs, key=lambda x: x[0]):
                lines.append(f"  • {name}")
                lines.append(f"    {url}")
            lines.append("")
    else:
        lines.append("--- Summary ---")
        lines.append(f"Pulled: {pulled} repo(s)")
        if failed:
            lines.append(f"Failed: {len(failed)} repo(s)")
        lines.append("")
        if pulled_names:
            lines.append("--- Repos pulled ---")
            lines.extend(f"  • {n}" for n in sorted(pulled_names))
            lines.append("")
    if failed:
        lines.append("--- Pull failed (check branch/remote) ---")
        for name, err in sorted(failed, key=lambda x: x[0]):
            lines.append(f"  • {name}")
            lines.append(f"    {err}")
        lines.append("")
    if commit_errors:
        lines.append("--- Commit/PR errors ---")
        for name, err in sorted(commit_errors, key=lambda x: x[0]):
            lines.append(f"  • {name}")
            lines.append(f"    {err}")
    return "\n".join(lines)


def maybe_notify_after_run(
    config: dict,
    sync_type: str,
    output_dir: str = "",
    cloned: int = 0,
    pulled: int = 0,
    cloned_names: list[str] | None = None,
    pulled_names: list[str] | None = None,
    failed: list[tuple[str, str]] | None = None,
    committed_names: list[str] | None = None,
    prs: list[tuple[str, str]] | None = None,
    commit_errors: list[tuple[str, str]] | None = None,
) -> None:
    """If config has email notification set, send summary after sync or pull-only."""
    cloned_names = cloned_names or []
    pulled_names = pulled_names or []
    failed = failed or []
    committed_names = committed_names or []
    prs = prs or []
    commit_errors = commit_errors or []
    body = build_notification_body(
        sync_type,
        output_dir,
        cloned,
        pulled,
        cloned_names,
        pulled_names,
        failed,
        committed_names=committed_names,
        prs=prs,
        commit_errors=commit_errors,
    )
    if sync_type == "sync":
        subject = f"GithubClonerAgent sync done — {platform.node() or 'device'}"
    else:
        subject = f"GithubClonerAgent pull done — {platform.node() or 'device'}"
    send_notification_email(config, subject, body)


def clone_repo(
    url: str,
    dest_dir: str,
    use_ssh: bool,
    dry_run: bool,
    shallow: bool = False,
    verbose_skip: bool = False,
) -> bool:
    """Clone a single repo. Returns True on success or skip."""
    if dry_run:
        print(f"  [dry run] would clone: {url} -> {dest_dir}")
        return True
    target = os.path.join(dest_dir, os.path.basename(url).replace(".git", ""))
    if os.path.isdir(target):
        if verbose_skip:
            print(f"  skip (exists): {target}")
        return True
    try:
        cmd = ["git", "clone"]
        if shallow:
            cmd.extend(["--depth", "1"])
        cmd.extend([url, target])
        run_cmd(cmd)
        print(f"  cloned: {target}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  error cloning {url}: {e.stderr or e}", file=sys.stderr)
        return False


def repo_status(path: str, require_branch: str | None) -> dict | None:
    """Return dict with branch, ahead, behind, dirty for one repo, or None on error."""
    try:
        branch_r = run_cmd(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], check=False)
        if branch_r.returncode != 0:
            return {"path": path, "branch": "?", "ahead": 0, "behind": 0, "dirty": False, "error": "not a branch"}
        branch = branch_r.stdout.strip()
        dirty_r = run_cmd(["git", "-C", path, "status", "--porcelain"], check=False)
        dirty = bool(dirty_r.stdout.strip())
        ahead, behind = 0, 0
        try:
            count_r = run_cmd(
                ["git", "-C", path, "rev-list", "--left-right", "--count", "@{u}...HEAD"],
                check=False,
            )
            if count_r.returncode == 0 and count_r.stdout.strip():
                behind_s, ahead_s = count_r.stdout.split()
                behind, ahead = int(behind_s), int(ahead_s)
        except (ValueError, IndexError):
            pass
        return {
            "path": path,
            "branch": branch,
            "ahead": ahead,
            "behind": behind,
            "dirty": dirty,
            "warn_branch": bool(require_branch and branch != require_branch),
        }
    except Exception as e:
        return {"path": path, "branch": "?", "ahead": 0, "behind": 0, "dirty": False, "error": str(e)}


def run_status(
    output_dir: str,
    require_branch: str | None,
    only_repo_names: set[str] | None = None,
) -> int:
    """Print status (branch, ahead/behind, dirty) for each repo. If only_repo_names is set, only those repos (from your GitHub list). Return 0."""
    repos = find_repo_dirs(output_dir)
    if only_repo_names is not None:
        repos = [p for p in repos if os.path.basename(p) in only_repo_names]
    if not repos:
        print("No git repositories found.")
        return 0
    for path in repos:
        info = repo_status(path, require_branch)
        if not info:
            continue
        name = os.path.basename(path)
        branch = info.get("branch", "?")
        ahead = info.get("ahead", 0)
        behind = info.get("behind", 0)
        dirty = "dirty" if info.get("dirty") else "clean"
        line = f"  {name}: {branch}  (ahead {ahead}, behind {behind}) {dirty}"
        if info.get("warn_branch") and require_branch:
            line += f"  [not {require_branch}]"
        if info.get("error"):
            line += f"  ({info['error']})"
        print(line)
    return 0


def sync_repos(
    repos: list[dict],
    dest: str,
    url_key: str,
    shallow: bool,
    jobs: int,
) -> tuple[int, int, list[str], list[str], list[tuple[str, str]]]:
    """Clone missing repos and pull existing. Returns (cloned, pulled, cloned_names, pulled_names, pull_failed)."""
    cloned_names: list[str] = []
    pulled_names: list[str] = []
    to_clone = []
    to_pull = []
    for r in repos:
        name = r["name"].split("/")[-1]
        path = os.path.join(dest, name)
        if os.path.isdir(path) and os.path.isdir(os.path.join(path, ".git")):
            to_pull.append(path)
        else:
            to_clone.append(r)

    if jobs <= 1:
        for r in to_clone:
            if clone_repo(r[url_key], dest, url_key == "sshUrl", False, shallow, verbose_skip=False):
                cloned_names.append(r["name"].split("/")[-1])
    else:
        def do_clone_with_name(r_dict: dict) -> str | None:
            ok = clone_repo(
                r_dict[url_key], dest, url_key == "sshUrl", False, shallow, verbose_skip=False
            )
            return (r_dict["name"].split("/")[-1]) if ok else None

        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futures = [ex.submit(do_clone_with_name, r) for r in to_clone]
            for fut in as_completed(futures):
                name = fut.result()
                if name:
                    cloned_names.append(name)
    cloned = len(cloned_names)

    pull_failed: list[tuple[str, str]] = []
    if jobs <= 1:
        for path in to_pull:
            name, ok, err = _pull_one(path)
            if ok:
                print(f"  pulled: {path}")
                pulled_names.append(name)
            else:
                print(f"  failed: {path} ({err})", file=sys.stderr)
                pull_failed.append((name, err))
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futures = {ex.submit(_pull_one, path): path for path in to_pull}
            for fut in as_completed(futures):
                name, ok, err = fut.result()
                if ok:
                    print(f"  pulled: {futures[fut]}")
                    pulled_names.append(name)
                else:
                    print(f"  failed: {futures[fut]} ({err})", file=sys.stderr)
                    pull_failed.append((name, err))
    pulled = len(pulled_names)
    return cloned, pulled, cloned_names, pulled_names, pull_failed


def _commit_and_pr_one(repo_path: str, date_str: str) -> tuple[str, bool, str | None, str | None]:
    """
    If repo has local changes: create/checkout feature/date, commit, push, create PR.
    Returns (repo_name, committed, pr_url, error). pr_url and error are None on success.
    """
    name = os.path.basename(repo_path)
    branch = f"feature/{date_str}"
    try:
        r = run_cmd(["git", "-C", repo_path, "status", "--porcelain"], check=False)
        if not r.stdout.strip():
            return (name, False, None, None)  # no changes

        # Create or checkout feature/date branch
        check = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--verify", branch],
            capture_output=True,
            text=True,
        )
        if check.returncode == 0:
            run_cmd(["git", "-C", repo_path, "checkout", branch])
        else:
            run_cmd(["git", "-C", repo_path, "checkout", "-b", branch])

        run_cmd(["git", "-C", repo_path, "add", "-A"])
        r2 = run_cmd(["git", "-C", repo_path, "status", "--porcelain"], check=False)
        if not r2.stdout.strip():
            return (name, False, None, None)  # nothing to commit after add (e.g. only untracked that were ignored)

        run_cmd(
            ["git", "-C", repo_path, "commit", "-m", f"Auto-sync from GithubClonerAgent ({date_str})"]
        )
        run_cmd(["git", "-C", repo_path, "push", "-u", "origin", branch])

        # Create PR (run from repo so gh detects it)
        pr_result = subprocess.run(
            [
                "gh", "pr", "create",
                "--base", "main",
                "--head", branch,
                "--title", f"Auto-sync {date_str}",
                "--body", "Automated sync from GithubClonerAgent.",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        pr_url = pr_result.stdout.strip() if pr_result.returncode == 0 else None
        if pr_result.returncode != 0 and "already exists" not in (pr_result.stderr or "").lower():
            return (name, True, pr_url, (pr_result.stderr or pr_result.stdout or "PR create failed")[:200])
        return (name, True, pr_url, None)
    except subprocess.CalledProcessError as e:
        return (name, False, None, (e.stderr or e.stdout or str(e))[:200])
    except Exception as e:
        return (name, False, None, str(e)[:200])


def commit_and_push_changes(
    dest: str, repo_names: set[str], date_str: str
) -> tuple[list[str], list[tuple[str, str]], list[tuple[str, str]]]:
    """
    For each repo in dest that has local changes: commit to feature/date, push, create PR.
    Returns (committed_names, list of (name, pr_url), list of (name, error)).
    """
    committed: list[str] = []
    prs: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    for name in sorted(repo_names):
        path = os.path.join(dest, name)
        if not os.path.isdir(path) or not os.path.isdir(os.path.join(path, ".git")):
            continue
        repo_name, did_commit, pr_url, err = _commit_and_pr_one(path, date_str)
        if err:
            errors.append((repo_name, err))
            print(f"  commit/PR error {repo_name}: {err}", file=sys.stderr)
        elif did_commit:
            committed.append(repo_name)
            if pr_url:
                prs.append((repo_name, pr_url))
                print(f"  committed & PR: {repo_name} -> {pr_url}")
            else:
                print(f"  committed & pushed: {repo_name}")
    return committed, prs, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clone/sync all your GitHub repos. Requires 'gh' CLI (gh auth login)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be cloned; do not run git clone.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_repos",
        help="List repos from GitHub (with filters) and exit. No clone/pull.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show branch, ahead/behind, and dirty state for each repo in output dir.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Clone any missing repos and pull existing ones (default for scheduled job).",
    )
    parser.add_argument(
        "--pull-only",
        action="store_true",
        help="Only run 'git pull' in all repos under output dir (no clone, no gh).",
    )
    parser.add_argument(
        "--setup-schedule",
        action="store_true",
        help="Install daily task at 2 AM EST to run --sync (clone new + pull existing).",
    )
    parser.add_argument(
        "--clear-schedule",
        action="store_true",
        help="Remove the daily scheduled task or cron job.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Directory to clone/pull repos (default: from config or Programming folder).",
    )
    parser.add_argument(
        "--owner",
        default=None,
        help="GitHub user or org to list repos for (default: authenticated user).",
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=None,
        help="Max number of repos to fetch (default: 1000).",
    )
    parser.add_argument(
        "--no-archived",
        action="store_true",
        help="Skip archived repositories.",
    )
    parser.add_argument(
        "--exclude",
        default=None,
        metavar="PATTERNS",
        help="Comma-separated globs to exclude (e.g. 'old-*,deprecated-*').",
    )
    parser.add_argument(
        "--only",
        default=None,
        metavar="PATTERNS",
        help="Comma-separated globs to include only (e.g. 'my-*').",
    )
    parser.add_argument(
        "--shallow",
        action="store_true",
        help="Clone with --depth 1 for faster first clone.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel clone jobs (default: 1).",
    )
    parser.add_argument(
        "--require-branch",
        default=None,
        metavar="BRANCH",
        help="Warn in --status when a repo is not on this branch (e.g. main).",
    )
    parser.add_argument(
        "--ssh",
        action="store_true",
        help="Use SSH URL for clone (default: HTTPS).",
    )
    args = parser.parse_args()

    # Config file overrides defaults (cli still overrides config)
    config = load_config()
    if args.output_dir is None and config.get("output_dir"):
        args.output_dir = config["output_dir"]
    if args.limit is None:
        args.limit = config.get("limit", 1000)
    if not args.no_archived and config.get("no_archived"):
        args.no_archived = True
    if args.exclude is None and config.get("exclude"):
        args.exclude = config["exclude"] if isinstance(config["exclude"], str) else ",".join(config["exclude"])
    if args.only is None and config.get("only"):
        args.only = config["only"] if isinstance(config["only"], str) else ",".join(config.get("only", []))
    if not args.shallow and config.get("shallow"):
        args.shallow = True
    if args.jobs == 1 and config.get("jobs"):
        args.jobs = int(config["jobs"])
    if args.require_branch is None and config.get("require_branch"):
        args.require_branch = config["require_branch"]

    dest = os.path.abspath(args.output_dir or get_default_output_dir())
    exclude_list = [p.strip() for p in (args.exclude or "").split(",") if p.strip()]
    only_list = [p.strip() for p in (args.only or "").split(",") if p.strip()]

    if args.setup_schedule:
        return 0 if setup_schedule(dest) else 1

    if args.clear_schedule:
        return 0 if clear_schedule() else 1

    if args.status:
        if not ensure_gh_ready():
            return 1
        try:
            gh_repos = get_repo_list(
                args.owner,
                args.limit,
                no_archived=args.no_archived,
                exclude=exclude_list,
                only=only_list,
            )
            only_names = {r["name"].split("/")[-1] for r in gh_repos}
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Could not get GitHub repo list: {e}", file=sys.stderr)
            return 1
        return run_status(dest, args.require_branch, only_repo_names=only_names)

    if args.pull_only:
        if not ensure_gh_ready():
            return 1
        try:
            gh_repos = get_repo_list(
                args.owner,
                args.limit,
                no_archived=args.no_archived,
                exclude=exclude_list,
                only=only_list,
            )
            only_names = {r["name"].split("/")[-1] for r in gh_repos}
        except (subprocess.CalledProcessError, Exception) as e:
            print(f"Could not get GitHub repo list: {e}", file=sys.stderr)
            return 1
        n, pulled_names, failed = pull_all_repos(
            dest, max(1, args.jobs), only_repo_names=only_names
        )
        print(f"Pulled {n} repo(s) (only your GitHub repos).")
        if failed:
            print(f"Failed: {len(failed)} repo(s).", file=sys.stderr)
        maybe_notify_after_run(
            config, "pull", output_dir=dest, pulled=n, pulled_names=pulled_names, failed=failed
        )
        return 0

    # From here we need repo list from GitHub (--list, --sync, or default clone)
    if not ensure_gh_ready():
        return 1
    if not args.dry_run and not args.list_repos and not os.path.isdir(dest):
        os.makedirs(dest, exist_ok=True)

    try:
        repos = get_repo_list(
            args.owner,
            args.limit,
            no_archived=args.no_archived,
            exclude=exclude_list,
            only=only_list,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error listing repos: {e.stderr or e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not repos:
        print("No repositories found.")
        return 0

    if args.list_repos:
        for r in repos:
            print(r["name"])
        return 0

    url_key = "sshUrl" if args.ssh else "url"

    if args.sync:
        print(f"Sync target: {dest}")
        print("Fetching repository list from GitHub...")
        cloned, pulled, cloned_names, pulled_names, pull_failed = sync_repos(
            repos, dest, url_key, args.shallow, max(1, args.jobs)
        )
        print(f"Done: {cloned} cloned, {pulled} pulled.")
        if pull_failed:
            print(f"Failed: {len(pull_failed)} repo(s).", file=sys.stderr)
        # Commit local changes to feature/date and create PRs (only when not dry-run)
        committed_names: list[str] = []
        prs: list[tuple[str, str]] = []
        commit_errors: list[tuple[str, str]] = []
        if not args.dry_run:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            repo_names = {r["name"].split("/")[-1] for r in repos}
            print("Checking for local changes to commit and open PRs...")
            committed_names, prs, commit_errors = commit_and_push_changes(dest, repo_names, date_str)
            if committed_names:
                print(f"Committed: {len(committed_names)} repo(s). PRs created: {len(prs)}.")
            if commit_errors:
                print(f"Commit/PR errors: {len(commit_errors)} repo(s).", file=sys.stderr)
        maybe_notify_after_run(
            config,
            "sync",
            output_dir=dest,
            cloned=cloned,
            pulled=pulled,
            cloned_names=cloned_names,
            pulled_names=pulled_names,
            failed=pull_failed,
            committed_names=committed_names,
            prs=prs,
            commit_errors=commit_errors,
        )
        return 0

    # Default: clone only (no pull)
    print(f"Clone target: {dest}")
    print("Fetching repository list from GitHub...")
    print(f"Found {len(repos)} repo(s). {'[DRY RUN]' if args.dry_run else ''}")
    ok = 0
    if args.jobs <= 1:
        for r in repos:
            if clone_repo(r[url_key], dest, args.ssh, args.dry_run, args.shallow, verbose_skip=True):
                ok += 1
    else:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            futures = {
                ex.submit(clone_repo, r[url_key], dest, args.ssh, args.dry_run, args.shallow, True): r
                for r in repos
            }
            for fut in as_completed(futures):
                if fut.result():
                    ok += 1
    print(f"Done: {ok}/{len(repos)} repos.")
    return 0 if ok == len(repos) else 1


if __name__ == "__main__":
    sys.exit(main())
