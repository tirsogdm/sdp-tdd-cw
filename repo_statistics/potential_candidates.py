import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

# --- ARGUMENTS ---
parser = argparse.ArgumentParser(description="Initial Filtering for java projects")
parser.add_argument("--token", help="GitHub personal access token", required=True)
parser.add_argument(
    "--input", help="Input raw stats CSV", default="apache_repo_stats.csv"
)
parser.add_argument(
    "--output", help="Output CSV", default="potential_java_candidates.csv"
)
parser.add_argument("--org", help="GitHub Organization", default="apache")
parser.add_argument(
    "--limit", help="Limit number of repos to process (0 for all)", type=int, default=0
)
args = parser.parse_args()

HEADERS = {"Authorization": f"token {args.token}"}
ORG = args.org

# Logging config
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


# Filters initial dataset for Java projects based on criteria
def filter_initial_candidates(input_file):
    if not os.path.exists(input_file):
        logging.error(f"Input file {input_file} not found.")
        return pd.DataFrame()

    df = pd.read_csv(input_file)
    logging.info(f"Loaded {len(df)} total repositories.")

    # Current filters: Java, >500 commits, >1 year old
    # Ensuring mature or developed java projects rather than starting out
    filtered_df = df[
        (df["main_language"] == "Java")
        & (df["num_commits"] > 500)
        & (df["project_life_days"] > 365)
    ]

    return filtered_df


# Main data retreival and analysis pipeline
def check_repo_structure(repo_data):
    index, row = repo_data
    repo_name = row["repo"]

    stats = {
        "has_build_system": False,
        "has_ci_system": False,
        "java_files": 0,
        "test_files": 0,
        "test_ratio": 0.0,
    }

    try:
        # Check root files for evidence of CI or Build systems
        # Checking for CI: Indicates an active auto testing mechanism
        # Checking for Build Systems: Indicates a structured, buildable project (better chances of TDD practices and easier to locate)
        contents_url = f"https://api.github.com/repos/{ORG}/{repo_name}/contents"
        r = requests.get(contents_url, headers=HEADERS, timeout=15)

        if r.status_code == 200:
            root_files = [f["name"] for f in r.json()]

            # Build Systems
            # Checks for Maven, Gradle, Ant, SBT, or Bazel
            has_pom = "pom.xml" in root_files
            has_gradle = any(
                f in root_files for f in ["build.gradle", "build.gradle.kts"]
            )
            has_ant = "build.xml" in root_files
            has_sbt = "build.sbt" in root_files
            has_bazel = "WORKSPACE" in root_files or "BUILD" in root_files

            stats["has_build_system"] = (
                has_pom or has_gradle or has_ant or has_sbt or has_bazel
            )

            # CI Systems
            # Checks for Jenkins, Travis, GitHub Actions, CircleCI, AppVeyor, Azure Pipelines
            has_jenkins = "Jenkinsfile" in root_files
            has_travis = ".travis.yml" in root_files
            has_github_actions = ".github" in root_files
            has_circleci = ".circleci" in root_files
            has_appveyor = "appveyor.yml" in root_files or ".appveyor.yml" in root_files
            has_azure = "azure-pipelines.yml" in root_files

            stats["has_ci_system"] = (
                has_jenkins
                or has_travis
                or has_github_actions
                or has_circleci
                or has_appveyor
                or has_azure
            )

        # Tree level scanning for all files
        # Calculates Total no. of Test Files / Total no. Java Files
        # Allowing for better selection of candidates based on test file ratio.
        tree_url = (
            f"https://api.github.com/repos/{ORG}/{repo_name}/git/trees/HEAD?recursive=1"
        )
        r = requests.get(tree_url, headers=HEADERS, timeout=15)

        if r.status_code == 200:
            tree = r.json().get("tree", [])
            java_count = 0
            test_count = 0

            for item in tree:
                path = item["path"]
                filename = path.split("/")[-1]

                # Java file
                if item["type"] == "blob" and path.endswith(".java"):

                    # Exclude metadata
                    if filename in ["package-info.java", "module-info.java"]:
                        continue

                    # Exclude auto generated Code
                    if "generated-sources" in path or "generated/source" in path:
                        continue

                    java_count += 1

                    # Java test files (2 options)
                    if filename.endswith("Test.java") or filename.endswith(
                        "Tests.java"
                    ):
                        test_count += 1

            stats["java_files"] = java_count
            stats["test_files"] = test_count
            if java_count > 0:
                stats["test_ratio"] = round(test_count / java_count, 4)

    except Exception as e:
        logging.warning(f"Error analyzing {repo_name}: {str(e)}")

    # Combine original row data with new stats
    combined = row.to_dict()
    combined.update(stats)
    return combined


def main():
    df = filter_initial_candidates(args.input)
    if df.empty:
        return

    # Limitor incase API calls are being throttled
    if args.limit > 0:
        logging.info(f"Limiting analysis to top {args.limit} candidates.")
        df = df.head(args.limit)

    logging.info("Starting analysis...")

    results = []

    # Analysis
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(check_repo_structure, (i, row)) for i, row in df.iterrows()
        ]

        for i, future in enumerate(as_completed(futures), 1):
            try:
                data = future.result()
                results.append(data)
                if i % 10 == 0 or i == len(df):
                    logging.info(f"Progress: {i}/{len(df)} repositories analyzed")
            except Exception as e:
                logging.error(f"Task failed: {e}")

    # Save Results
    result_df = pd.DataFrame(results)

    # Columns for output .csv
    cols = [
        "repo",
        "stars",
        "num_commits",
        "test_ratio",
        "test_files",
        "java_files",
        "has_build_system",
        "has_ci_system",
    ]
    remaining = [c for c in result_df.columns if c not in cols]
    result_df = result_df[cols + remaining]

    result_df.to_csv(args.output, index=False)
    logging.info(f"Data collection complete. Saved to {args.output}")


if __name__ == "__main__":
    main()
