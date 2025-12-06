#!/usr/bin/env python3
"""
Clone Apache Java Repositories from CSV

Usage:
    python clone_repos.py <output_directory> [--limit N] [--csv path/to/csv] [--workers N]

Examples:
    python clone_repos.py ./repos                    # Clone all repos
    python clone_repos.py ./repos --limit 5          # Clone only first 5 repos
    python clone_repos.py ./repos --workers 8        # Use 8 parallel workers
"""

import argparse
import csv
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

GITHUB_ORG = "apache"


# Get total size of directory
def get_dir_size(path: Path) -> int:
    """Get total size of directory in bytes."""
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f}"


# Main cloning function
def clone_repo(args: tuple) -> tuple[str, bool, int]:
    repo_name, output_dir = args
    repo_url = f"https://github.com/{GITHUB_ORG}/{repo_name}.git"
    repo_path = Path(output_dir) / repo_name

    # Skip if already exists
    if (repo_path / ".git").exists():
        size = get_dir_size(repo_path)
        print(f"  [SKIP] {repo_name} (already exists - {format_size(size)})")
        return (repo_name, True, size)

    # Clone
    subprocess.run(
        ["git", "clone", "--quiet", repo_url, str(repo_path)],
        capture_output=True,
    )

    size = get_dir_size(repo_path)
    print(f"  [DONE] {repo_name} ({format_size(size)})")
    return (repo_name, True, size)


def main():
    parser = argparse.ArgumentParser(
        description="Clone Apache Java repositories from CSV"
    )
    parser.add_argument("output_dir", help="Directory to clone repositories into")
    # For testing
    parser.add_argument(
        "--limit", type=int, default=0, help="Only clone first N repositories"
    )
    parser.add_argument(
        "--csv",
        help="Path to CSV file",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )

    args = parser.parse_args()

    # Create output directory
    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Read repos from CSV
    repos = []
    with open(args.csv, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            repos.append(row["repo"])

    # Apply limit
    if args.limit > 0:
        repos = repos[: args.limit]

    print("=" * 50)
    print("Repository Cloner")
    print("=" * 50)
    print(f"CSV File:    {args.csv}")
    print(f"Output Dir:  {args.output_dir}")
    print(f"Repos:       {len(repos)}")
    print("=" * 50)
    print()

    # Prepare arguments for parallel execution
    clone_args = [(repo, args.output_dir) for repo in repos]

    # Clone in parallel
    total_size = 0
    success_count = 0

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(clone_repo, arg): arg[0] for arg in clone_args}

        for future in as_completed(futures):
            repo_name, success, size = future.result()
            if success:
                success_count += 1
                total_size += size

    print()
    print("=" * 50)
    print("Cloning Complete")
    print("=" * 50)
    print(f"Repositories: {success_count}/{len(repos)}")
    print(f"Total Size:   {format_size(total_size)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
