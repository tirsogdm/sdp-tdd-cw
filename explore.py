import os
import requests
import subprocess
from pathlib import Path
from pydriller.git import Git
from pydriller import Repository

GITHUB_API_URL = "https://api.github.com"

def make_headers():
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def fetch_apache_repos(max_repos=None):
    """
    Fetch public repositories from the Apache organisation on GitHub.
    """
    headers = make_headers()    
    repos = []
    url = f"{GITHUB_API_URL}/orgs/apache/repos"
    params = {"per_page": 100, "page": 1, "type": "public"}

    while True:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        batch = res.json()
        if not batch:
            break
        repos.extend(batch)
        if max_repos is not None and len(repos) >= max_repos:
            repos = repos[:max_repos]
            break
        params["page"] += 1

    return repos


def has_test_dir(repo_full_name, max_depth=2):
    """
    TDD-likelihood heuristic: projects with a meaningful test suite tend to have a near top-level directory whose name contains "test".
    """
    headers = make_headers()
    queue = [("", 0)]  # (path, depth)

    while queue:
        path, depth = queue.pop(0)
        if depth > max_depth:
            continue

        if path:
            url = f"{GITHUB_API_URL}/repos/{repo_full_name}/contents/{path}"
        else:
            url = f"{GITHUB_API_URL}/repos/{repo_full_name}/contents"

        resp = requests.get(url, headers=headers)
        if resp.status_code == 404:
            continue
        resp.raise_for_status()
        items = resp.json()
        
        for item in items:
            if item.get("type") != "dir":
                continue

            dir_name = item.get("name", "")
            if "test" in dir_name.lower():
                return True
            
            sub_path = dir_name if not path else f"{path}/{dir_name}"
            if depth < max_depth:
                queue.append((sub_path, depth + 1))

    return False

def filter_repos(
        repos,
        language=None,
        min_size=None,
        max_size=None,
        require_apache_license=True,
        exclude_forks=True, 
        exclude_archived=True
):
    """
    Filter a list of repositories based on various criteria. Experimenting, not sure how useful this will be.
    """
    filtered = []

    for r in repos:
        if exclude_forks and r.get("fork"):
            continue
        if exclude_archived and r.get("archived"):
            continue

        if language is not None and r.get("language") != language:
            continue

        size = r.get("size", 0)
        if min_size is not None and size < min_size:
            continue
        if max_size is not None and size > max_size:
            continue

        lic = r.get("license", {})
        spdx = lic.get("spdx_id")
        if require_apache_license and spdx != "Apache-2.0":
            continue
        
        filtered.append(r)

    return filtered

def clone_or_update_repo(repo_name, base_dir="repos"):
    base = Path(base_dir)
    base.mkdir(exist_ok=True)
    local_path = base / repo_name.replace("/", "__")

    if not local_path.exists():
        print(f"Cloning {repo_name}...")
        subprocess.run(["git", "clone", f"https://github.com/{repo_name}.git", str(local_path)], check=True)
    else:
        print(f"Updating {repo_name}...")
        subprocess.run(["git", "-C", str(local_path), "fetch", "--all", "--prune"], check=True)

    return local_path

def choose_main_branch(branches):
    """
    """
    if "main" in branches:
        return "main"
    if "master" in branches:
        return "master"
    return branches[0] if branches else None

"""
Potential issue:
- This approach to search for unreachable branches can also include branches that have been rebased.
"""
def get_unreachable_branches(repo_path):
    g = Git(str(repo_path))
    repo = g.repo

    remote = repo.remotes.origin
    remote_branches = []
    for ref in remote.refs:
        if ref.remote_head == "HEAD":
            continue

        remote_branches.append(ref.remote_head)

    if not remote_branches:
        return None, []
    
    main_short = choose_main_branch(remote_branches)
    main_ref = f"origin/{main_short}"

    main_commits = {
        c.hash for c in Repository(str(repo_path), only_in_branch=main_ref).traverse_commits()
    }

    results = []
    for br_short in remote_branches:
        ref_obj = next(r for r in remote.refs if r.remote_head == br_short)
        head_hash = ref_obj.commit.hexsha

        reachable = head_hash in main_commits
        results.append({"branch": br_short, "head": head_hash, "reachable": reachable})

    return main_short, results

def iter_commits_for_branch(repo_path, branch):
    repo = Repository(str(repo_path), only_in_branch=branch)
    for commit in repo.traverse_commits():
        yield commit


if __name__ == "__main__":
    # 1) Fetch & filter some Apache repos
    repos = fetch_apache_repos(max_repos=20)
    filtered_repos = filter_repos(repos, language="Java")
    print(f"After filtering, {len(filtered_repos)} repos remain.")

    # 2) Take first repo as an example
    if not filtered_repos:
        raise SystemExit("No repositories matched the filtering criteria.")

    example = filtered_repos[0]
    full_name = example["full_name"]
    print(f"Analysing repository: {full_name}")

    # 3) Clone/update repo and analyse branches
    local_path = clone_or_update_repo(full_name)
    main_branch, branch_info = get_unreachable_branches(local_path)

    print(f"Main branch: {main_branch}")
    print("Branches and reachability from main")

    for info in branch_info:
        br = info["branch"]
        head_hash = info["head"]
        reachable = info["reachable"]
        status = "reachable" if reachable else "NOT reachable"
        print(f"  {br:20s} {head_hash[:7]} -> {status}")