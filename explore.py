import os
import requests

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
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        batch = resp.json()
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

if __name__ == "__main__":
    repos = fetch_apache_repos(max_repos=200)
    print(f"Fetched {len(repos)} repos.")

    filtered_repos = filter_repos(
        repos,
        language="Java"
    )

    print(f"After filtering, {len(filtered_repos)} repos remain. Removed {len(repos) - len(filtered_repos)}.")

    for r in filtered_repos:
        full_name = r["full_name"]
        test_dir = has_test_dir(full_name) # TODO: Probably want to incorporate this check into the filtering step above
        print(
            full_name,
            "| lang:", r["language"],
            "| size:", r["size"],
            "| license:", (r["license"]["spdx_id"] if r["license"] else "None"),
            "| has test dir:", test_dir
        )