import csv
import os
import time

from pydriller import Repository

# TODO: What if a file was added then removed? would still appear in the dictionary
# TODO: If a file was added -> removed at another point of time the dict would still keep track

# Took ~5 minutes for 5 repos. Same approx time for downloading.

# Repo names
TARGET_REPOS = [
    "commons-lang",
    "commons-io",
    "commons-collections",
    "commons-math",
    "maven",
]

# Path
LOCAL_REPOS_DIR = os.path.join(os.getcwd(), "repos")
MASTER_OUTPUT_FILE = "tdd_dataset.csv"


def get_file_role(filename):
    if not filename.endswith(".java"):
        return None, None
    filename = filename.replace("\\", "/")

    # Test file
    if filename.endswith("Test.java"):
        return "TEST", filename.split("/")[-1].replace("Test.java", "")

    # Production code file
    elif filename.endswith(".java") and "package-info" not in filename:
        return "CODE", filename.split("/")[-1].replace(".java", "")

    return None, None


def mine_repos():
    print(f"Starting mining on {len(TARGET_REPOS)} repositories")

    # CSV Headers
    headers = [
        "Project",
        "Commit_Hash",
        "Date",
        "Author",
        "Commit_Size",
        "TDD_Category",
        "Class_Name",
        "Test_File",
        "Latency_Hours",
        "Related_Commit",
    ]

    with open(MASTER_OUTPUT_FILE, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(headers)

        for repo_name in TARGET_REPOS:
            repo_path = os.path.join(LOCAL_REPOS_DIR, repo_name)

            if not os.path.exists(repo_path):
                print(f"[SKIP] Repo not found: {repo_path}")
                continue

            print(f"Mining: {repo_name}:")
            repo_start_time = time.time()  # Timer for individual repo

            # {'hash': str, 'date': datetime}
            seen_code = {}
            seen_tests = {}

            try:
                for commit in Repository(repo_path).traverse_commits():
                    commit_date = commit.committer_date

                    # Scan Commit for NEW files
                    added_in_this_commit = {}
                    for mod in commit.modified_files:
                        if mod.change_type.name == "ADD":
                            role, class_name = get_file_role(mod.filename)
                            if role:
                                if class_name not in added_in_this_commit:
                                    added_in_this_commit[class_name] = {}
                                added_in_this_commit[class_name][role] = mod.filename

                    for class_name, roles in added_in_this_commit.items():

                        # test_filename = roles.get("TEST", f"{class_name}Test.java")

                        # CASE 1: ATOMIC TDD (Both in this commit)
                        if "TEST" in roles and "CODE" in roles:
                            writer.writerow(
                                [
                                    repo_name,
                                    commit.hash,
                                    commit_date,
                                    commit.author.name,
                                    len(commit.modified_files),
                                    "ATOMIC_TDD",
                                    class_name,
                                    roles["TEST"],
                                    0.0,
                                    commit.hash,
                                ]
                            )
                            # Mark as seen
                            seen_tests[class_name] = {
                                "hash": commit.hash,
                                "date": commit_date,
                                "filename": roles["TEST"],
                            }
                            seen_code[class_name] = {
                                "hash": commit.hash,
                                "date": commit_date,
                            }
                            continue

                        # CASE 2: TEST LAST (Test here, Code seen before)
                        if "TEST" in roles and class_name in seen_code:
                            prev_info = seen_code[class_name]
                            diff = (
                                commit_date - prev_info["date"]
                            ).total_seconds() / 3600.0

                            writer.writerow(
                                [
                                    repo_name,
                                    commit.hash,
                                    commit_date,
                                    commit.author.name,
                                    len(commit.modified_files),
                                    "TEST_LAST",
                                    class_name,
                                    roles["TEST"],
                                    round(diff, 2),
                                    prev_info["hash"],
                                ]
                            )
                            seen_tests[class_name] = {
                                "hash": commit.hash,
                                "date": commit_date,
                            }

                        # CASE 3: STRICT TDD (Code here, Test seen before)
                        elif "CODE" in roles and class_name in seen_tests:
                            prev_info = seen_tests[class_name]
                            diff = (
                                commit_date - prev_info["date"]
                            ).total_seconds() / 3600.0
                            prev_info = seen_tests[class_name]
                            actual_test_name = prev_info["filename"]

                            writer.writerow(
                                [
                                    repo_name,
                                    commit.hash,
                                    commit_date,
                                    commit.author.name,
                                    len(commit.modified_files),
                                    "STRICT_TDD",
                                    class_name,
                                    actual_test_name,
                                    round(diff, 2),
                                    prev_info["hash"],
                                ]
                            )
                            seen_code[class_name] = {
                                "hash": commit.hash,
                                "date": commit_date,
                            }

                        # Update Memory for singles
                        if "TEST" in roles:
                            actual_test_filename = roles.get("TEST")
                            seen_tests[class_name] = {
                                "hash": commit.hash,
                                "date": commit_date,
                                "filename": actual_test_filename,
                            }
                        if "CODE" in roles:
                            seen_code[class_name] = {
                                "hash": commit.hash,
                                "date": commit_date,
                            }

                # Print individual repo time
                repo_end = time.time()
                print(
                    f"   > Finished {repo_name} in {(repo_end - repo_start_time):.2f} seconds."
                )

            except Exception as e:
                print(f"Error processing {repo_name}: {e}")

    print(f"Final dataset saved to {MASTER_OUTPUT_FILE}")


if __name__ == "__main__":
    # Overall timing code block
    start_time = time.time()

    mine_repos()

    end_time = time.time()
    total_duration = end_time - start_time

    print("\n" + "=" * 40)
    print(f"TOTAL EXECUTION TIME: {total_duration:.2f} seconds")
    print(f"({total_duration/60:.2f} minutes)")
    print("=" * 40)
