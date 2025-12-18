import os
import subprocess
from tqdm import tqdm
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

import requests

@dataclass(frozen=True)
class MainCommitMeta:
    oid: str
    parent_count: int

def run_git(repo_dir: str, *args: str) -> str:
    """Run a git command and return stdout (stripped)."""
    res = subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return res.stdout.strip()

def iso_since_years(years: int) -> str:
    since = datetime.now(timezone.utc) - timedelta(days=365 * years)
    return since.strftime("%Y-%m-%d")

def get_main_commits_since(repo_dir: str, main_ref: str = "origin/main", years: int = 3) -> List[MainCommitMeta]:
    """
    Return main commits oldest->newest since N years ago, with parent_count.
    """
    since = iso_since_years(years)
    out = run_git(repo_dir, "rev-list", "--reverse", "--parents", f'--since={since}', main_ref)
    commits: List[MainCommitMeta] = []
    if not out:
        return commits
    for line in out.splitlines():
        parts = line.split()
        oid = parts[0]
        parent_count = len(parts) - 1
        commits.append(MainCommitMeta(oid=oid, parent_count=parent_count))
    return commits

def identify_candidate_squash_commits(main_commits: List[MainCommitMeta], min_files_changed: int = 20, min_lines_changed: int = 500) -> Set[str]:
    out: Set[str] = set()
    for c in tqdm(main_commits, desc="Identifying candidate squash commits"):
        if c.parent_count != 1:
            continue
        if c.files_changed >= min_files_changed or c.lines_changed >= min_lines_changed:
            out.add(c.oid)
    return out


# ---------------------------------------------------------------
# ----- GraphQL lookup mapping mergeCommitOid -> headRefOid -----
# ---------------------------------------------------------------

GITHUB_GQL_URL = "https://api.github.com/graphql"

def make_headers() -> Dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

GQL_MERGED_PRS_PAGE = """
query($owner:String!, $repo:String!, $pageSize:Int!, $after:String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(
      first: $pageSize,
      after: $after,
      states: [MERGED],
      orderBy: { field: CREATED_AT, direction: DESC }
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        mergedAt
        headRefOid
        mergeCommit { oid }
        commits { totalCount }
      }
    }
  }
}
"""

@dataclass(frozen=True)
class PRInfo:
    number: int
    mergedAt: str
    head_ref_oid: str
    merge_commit_oid: str
    commit_count: int

def parse_github_time(ts: str) -> datetime:
    """Parse GitHub timestamp string to datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)

def fetch_merged_prs_window(owner: str, repo: str, since_iso: str, page_size: int = 50, max_pages: int = 200) -> List[PRInfo]:
    since_dt = parse_github_time(since_iso)
    after: Optional[str] = None
    merged_prs: List[PRInfo] = []

    for page_idx in range(max_pages):
        variables = {"owner": owner, "repo": repo, "pageSize": page_size, "after": after}
        resp = requests.post(
            GITHUB_GQL_URL,
            json={"query": GQL_MERGED_PRS_PAGE, "variables": variables},
            headers=make_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(data["errors"])

        conn = data["data"]["repository"]["pullRequests"]
        nodes = conn["nodes"]

        kept = 0
        for pr in nodes:
            if pr["mergedAt"] is None:
                continue
            merged_at = parse_github_time(pr["mergedAt"])
            if merged_at >= since_dt:
                merged_prs.append(
                    PRInfo(
                        number=int(pr["number"]),
                        mergedAt=str(pr["mergedAt"]),
                        head_ref_oid=str(pr["headRefOid"]),
                        merge_commit_oid=str(pr["mergeCommit"]["oid"]),
                        commit_count=int(pr["commits"]["totalCount"]),
                    )
                )
                kept += 1

        print(f"Page {page_idx+1}: kept {kept} (total kept={len(merged_prs)})")

        if not conn["pageInfo"]["hasNextPage"]:
            break
        after = conn["pageInfo"]["endCursor"]

    return merged_prs

if __name__ == "__main__":
    repo_path = "/Users/tirso/Desktop/UCL/Term 1/COMP0104_SDP/CW2/repos/spark"
    # main = get_main_commits_since(repo_path, main_ref="origin/master", years=2)
    # print(len(main), "main commits since 2 years ago")
    since_iso = iso_since_years(2)
    prs = fetch_merged_prs_window("apache", "spark", since_iso)
    print("Merged PRs fetched:", len(prs))