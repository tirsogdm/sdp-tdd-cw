import os

import pandas as pd

# Configuration
INPUT_FILE = "potential_java_candidates.csv"
OUTPUT_FILE = "final_java_candidates.csv"

# Filters

# Ensures project has sufficient complexitity to warrant TDD also removes emtpy wrappers or templates.
MIN_JAVA_FILES = 50
# Filters out projects with trivial testing implementation.
# MIN_TEST_RATIO = 0
# Removes repositories which are purely test suites.
# MAX_TEST_RATIO = 1


def print_final_list():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        return

    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} repositories from {INPUT_FILE}")

    # Checking for CI or Build Systems
    # Logic: (Has any CI) OR (Has any Build System)
    candidates = df[df["has_build_system"] | df["has_ci_system"]].copy()
    print(f"Repositories with CI & Build System: {len(candidates)}")

    # Checking for Java files and test ratio
    quality_candidates = candidates[
        (candidates["java_files"] > MIN_JAVA_FILES)
        # & (candidates["test_ratio"] >= MIN_TEST_RATIO)
        # & (candidates["test_ratio"] <= MAX_TEST_RATIO)
    ].copy()

    print(f"Repositories after Quality Filtering: {len(quality_candidates)}")
    print(
        # f" (Criteria: >{MIN_JAVA_FILES} files, {MIN_TEST_RATIO}-{MAX_TEST_RATIO} test ratio)"
        f" (Criteria: >{MIN_JAVA_FILES} files)"
    )

    # Sort by Test Ratio (Descending)
    final_list = quality_candidates.sort_values(by="test_ratio", ascending=False)

    # Save to CSV
    cols = [
        "repo",
        "test_ratio",
        "test_files",
        "java_files",
        "num_commits",
        "stars",
        "has_ci_system",
        "has_build_system",
    ]
    # Add remaining columns
    remaining = [c for c in final_list.columns if c not in cols]
    final_list[cols + remaining].to_csv(OUTPUT_FILE, index=False)
    print(f"Final Shortlist saved to: {OUTPUT_FILE}")

    # Split into 5 parts 
    num_parts = 5
    chunk_size = (len(final_list) + num_parts - 1) // num_parts  # ceiling division

    for i in range(num_parts):
        part = final_list.iloc[i * chunk_size : (i + 1) * chunk_size]
        if not part.empty:
            part_file = f"final_java_candidates_part{i+1}.csv"
            part.to_csv(part_file, index=False)
            print(f"Saved part {i+1}: {part_file}")

if __name__ == "__main__":
    print_final_list()
