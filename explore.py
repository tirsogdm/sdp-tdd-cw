import os
import requests

GITHUB_API_URL = "https://api.github.com"

def fetch_apache_repos():
    """
    Fetch public repositories from the Apache organisation on GitHub.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    repos = []
    url = f"{GITHUB_API_URL}/orgs/apache/repos"
    params = {"per_page": 100, "page": 1, "type": "public"}

    while True:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        repos.extend(batch)
        params["page"] += 1

    return repos

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

        lic = r.get("license")
        if require_apache_license and lic is not None:
            spdx = lic.get("spdx_id")
            if spdx != "Apache-2.0":
                continue

        filtered.append(r)       

    return filtered

if __name__ == "__main__":
    repos = fetch_apache_repos()
    print(f"Fetched {len(repos)} repos.")

    java_repos = filter_repos(
        repos,
        language="Python"
    )

    print(f"After filtering, {len(java_repos)} repos remain. Removed {len(repos) - len(java_repos)}.")

    for r in java_repos:
        print(
            r["full_name"],
            "| lang:", r["language"],
            "| size:", r["size"],
            "| license:", (r["license"]["spdx_id"] if r["license"] else "None")
        )