import argparse
import requests
import json
import pandas as pd
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# --- ARGUMENTS ---
parser = argparse.ArgumentParser(description="Fetch GitHub repo statistics")
parser.add_argument("--token", help="GitHub personal access token", required=True)
parser.add_argument("--org", help="The organisation on GitHub to get repo stats for", default="apache")
args = parser.parse_args()

# --- CONFIG ---
ORG = args.org
TOKEN = args.token
HEADERS = {"Authorization": f"token {TOKEN}"} if TOKEN else {}

# --- SETUP LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    filename="repo_stats.log",
    filemode="w"  # "w" = overwrite each run, "a" = append
)


def fetchAllReposOf(organisation):
    repos_url = f"https://api.github.com/orgs/{organisation}/repos?per_page=100"
    repos = []
    while repos_url:
        r = requests.get(repos_url, headers=HEADERS)
        r.raise_for_status()
        repos.extend(r.json())
        # Check for next page
        repos_url = r.links.get("next", {}).get("url")

    return repos


def saveReposToJson(repos, filename):
    with open(filename, "w") as f:
        json.dump(repos, f, indent=4)


def getAllReposOf(organisation):
    filename = f"{organisation}_repos.json"

    try:
        # Try to open the file in read-only mode
        with open(filename, "r") as f:
            repos = json.load(f)
        logging.info(f"Loaded {len(repos)} repos from {filename}")
    except FileNotFoundError:
        # File doesn't exist > fetch from GitHub
        repos = fetchAllReposOf(organisation)
        saveReposToJson(repos, filename)
        logging.info(f"Fetched {len(repos)} repos and saved to {filename}")

    return repos


def raise_error(response):
    # If the request failed, raise an exception with the actual JSON message
    if not response.ok:
        msg = response.json().get("message", response.text)
        raise requests.exceptions.HTTPError(f"{response.status_code} {msg}")

def fetchCommitData(org, repo):
    logging.info(f"Checking commit data of {repo}...")

    # Latest commit (most recent)
    latest_url = f"https://api.github.com/repos/{org}/{repo}/commits?per_page=1"
    r = requests.get(latest_url, headers=HEADERS)
    raise_error(r)
    latest_commit = r.json()[0]
    latest_date = latest_commit["commit"]["author"]["date"]

    # Extract total number of commits
    link = r.links.get("last", {}).get("url")
    parsed_url = urlparse(link)
    query_params = parse_qs(parsed_url.query)
    total_commits = int(query_params.get("page", [0])[0])

    # Oldest commit (first)
    oldest_url = f"https://api.github.com/repos/{org}/{repo}/commits?per_page=1&page={total_commits}"
    r = requests.get(oldest_url, headers=HEADERS)
    raise_error(r)
    oldest_commit = r.json()[0]
    oldest_date = oldest_commit["commit"]["author"]["date"]

    return total_commits, latest_date, oldest_date


def process_repo(repo):
    name = repo["name"]
    language = repo["language"]
    stars = repo["stargazers_count"]
    forks = repo["forks_count"]

    try:
        n_commits, latest_commit_date, oldest_commit_date = fetchCommitData(ORG, name)
    except requests.exceptions.HTTPError as e:
        logging.warning(f"Failed to get commit data of {name}: {e}")
        n_commits, latest_commit_date, oldest_commit_date = None, None, None

    return {
        "repo": name,
        "main_language": language,
        "stars": stars,
        "forks": forks,
        "num_commits": n_commits,
        "first_commit_date": oldest_commit_date,
        "last_commit_date": latest_commit_date,
    }


if __name__ == "__main__":
    repos = getAllReposOf(ORG)
    data = []

    # Run the repo processing in parallel
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_repo, repo) for repo in repos]
        for future in as_completed(futures):
            data.append(future.result())

    df = pd.DataFrame(data)

    # Convert commit dates to datetime
    df["first_commit_date"] = pd.to_datetime(df["first_commit_date"])
    df["last_commit_date"] = pd.to_datetime(df["last_commit_date"])

    # Add project life column (as timedelta in days)
    df["project_life_days"] = (df["last_commit_date"] - df["first_commit_date"]).dt.days

    logging.info("Collected data:\n%s", df)
    df.to_csv(f"{ORG}_repo_stats.csv", index=False)
