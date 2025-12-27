from pathlib import Path
import argparse
import pandas as pd
import matplotlib.pyplot as plt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", type=Path, required=True, help="Base directory containing CSV results")
    ap.add_argument("--repo", type=str, required=True, help="Repository name to plot (must match 'repository' column)")

    args = ap.parse_args()

    base_dir = Path(args.base_dir)
    commits_path = base_dir / "tdd_commits.csv"
    outliers_path = base_dir / "outlier_commits.csv"

    cs = pd.read_csv(commits_path)
    outliers = pd.read_csv(outliers_path)

    # Filter
    cs = cs[cs["repository"] == args.repo].copy()
    if cs.empty:
        raise SystemExit(f"No data for repository '{args.repo}' in {commits_path}")
    
    # Normalise
    cs["commit_hash"] = cs["commit_hash"].astype(str)
    cs["total_lines_added"] = pd.to_numeric(cs["total_lines_added"], errors="coerce").fillna(0)
    cs["total_files_count"] = pd.to_numeric(cs["total_files_count"], errors="coerce").fillna(0)

    # Sort
    if "commit_date" in cs.columns:
        cs["commit_date"] = pd.to_datetime(cs["commit_date"], errors="coerce", utc=True)
        cs = cs.sort_values(["commit_date", "commit_hash"], kind="stable")
    
    outliers_info = outliers.loc[outliers["repository"] == args.repo, ["commit_hash", "out_due_to_lines", "out_due_to_files"]].copy()
    outliers_info["commit_hash"] = outliers_info["commit_hash"].astype(str)

    cs = cs.merge(outliers_info, on="commit_hash", how="left")

    cs["is_outlier_lines"] = cs["out_due_to_lines"].astype(str).str.lower().eq("true")
    cs["is_outlier_files"] = cs["out_due_to_files"].astype(str).str.lower().eq("true")

    # === Plot ===
    y1 = cs["total_lines_added"].to_numpy()
    y2 = cs["total_files_count"].to_numpy()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 8))

    ax1.scatter(
        [i for i, v in enumerate(cs["is_outlier_lines"]) if not v],
        y1[~cs["is_outlier_lines"].to_numpy()],
        label="non-outlier-lines",
        s=10
    )

    ax1.scatter(
        [i for i, v in enumerate(cs["is_outlier_lines"]) if v],
        y1[cs["is_outlier_lines"].to_numpy()],
        label="outlier-lines",
        s=10
    )

    ax1.scatter(
        [i for i, v in enumerate(cs["is_outlier_files"]) if v],
        y1[cs["is_outlier_files"].to_numpy()],
        label="outlier-files",
        color="red",
        s=1
    )

    ax1.set_yscale("log")
    ax1.set_xlabel("Commits index")
    ax1.set_ylabel("Total lines added")
    ax1.set_title(f"Commits index vs total lines added")
    ax1.legend()

    ax2.scatter(
        [i for i, v in enumerate(cs["is_outlier_files"]) if not v],
        y2[~cs["is_outlier_files"].to_numpy()],
        label="non-outlier-files",
        s=10
    )

    ax2.scatter(
        [i for i, v in enumerate(cs["is_outlier_files"]) if v],
        y2[cs["is_outlier_files"].to_numpy()],
        label="outlier-files",
        s=10
    )

    ax2.scatter(
        [i for i, v in enumerate(cs["is_outlier_lines"]) if v],
        y2[cs["is_outlier_lines"].to_numpy()],
        label="outlier-lines",
        color="red",
        s=1
    )

    ax2.set_yscale("log")
    ax2.set_xlabel("Commits index")
    ax2.set_ylabel("Total files count")
    ax2.set_title(f"Commits index vs total files count")
    ax2.legend()

    fig.suptitle(f"Repository: {args.repo}", fontsize=16)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()