from pathlib import Path
import pandas as pd
import shutil

# -------------------------
# Config
# -------------------------
BASE_DIR = Path("results/Set-4/")
OUT_DIR = BASE_DIR.parent.parent / "results_ADJ"

COMMIT_SIZE_CSV = BASE_DIR / "tdd_commits.csv"
PAIRS_CSV = BASE_DIR / "tdd_pairs.csv"

# Outlier definition (Quintile thresholds)
Q_LINES = 0.99
Q_FILES = 0.99

# -------------------------
# Helpers
# -------------------------
def summarise(label: str, series: pd.Series):
    counts = series.value_counts(dropna=False)
    props = (counts / counts.sum()).rename("proportion")
    out = pd.concat([counts.rename("count"), props], axis=1)
    print(f"\n== {label} ==")
    print(out)

# -------------------------
# ------- Load data -------
# -------------------------
cs_all = pd.read_csv(COMMIT_SIZE_CSV)
pairs_all = pd.read_csv(PAIRS_CSV)

# Normalise globally
cs_all["commit_hash"] = cs_all["commit_hash"].astype(str)
pairs_all["test_commit"] = pairs_all["test_commit"].astype(str)

# Adjusted column
pairs_all["classification_adj"] = pairs_all["classification"].copy()

# Per-repo audit data
summary_rows = []
outlier_rows = []

# -------------------------
# Analysis loop
# -------------------------
repos = sorted(pairs_all["repository"].unique())

for repo in repos:
    # Filter data for this repo
    cs = cs_all[cs_all["repository"] == repo].copy()
    pairs_idxs = pairs_all.index[pairs_all["repository"] == repo] # indices in global pairs df

    if cs.empty or len(pairs_idxs) == 0:
        continue

    # Ensure numeric types, NaN -> 0, int
    cs["total_lines_added"] = pd.to_numeric(cs["total_lines_added"], errors="coerce").fillna(0)
    cs["total_files_count"] = pd.to_numeric(cs["total_files_count"], errors="coerce").fillna(0)

    # Compute quantile thresholds (for lines added and files modified)
    thr_lines = cs["total_lines_added"].quantile(Q_LINES)
    thr_files = cs["total_files_count"].quantile(Q_FILES)

    # Flag outlier commits (OR rule)
    cs["is_outlier"] = (cs["total_lines_added"] >= thr_lines) | (cs["total_files_count"] >= thr_files)
    cs["out_due_to_lines"] = cs["total_lines_added"] >= thr_lines
    cs["out_due_to_files"] = cs["total_files_count"] >= thr_files

    outlier_commits = set(cs.loc[cs["is_outlier"], "commit_hash"].astype(str))

    # Apply adjustement to pairs
    same_mask_repo = pairs_all.loc[pairs_idxs, "classification"] == "SAME_COMMIT"
    n_same = int(same_mask_repo.sum())

    if n_same > 0 and outlier_commits:
        # For SAME_COMMIT pairs, check whether the commit is an outlier
        same_idxs = pairs_idxs[same_mask_repo] # [True, False, ...] -> actual indices (where True)
        is_same_outlier = pairs_all.loc[same_idxs, "test_commit"].isin(outlier_commits) # Gets commit of each SAME_COMMIT pair index, checks if in outliers -> [True, False, ...]

        # Write out
        pairs_all.loc[same_idxs, "same_commit_is_outlier"] = is_same_outlier
        pairs_all.loc[same_idxs[is_same_outlier], "classification_adj"] = "SAME_COMMIT_OUTLIER"

        n_relabeled = int(is_same_outlier.sum())
    else:
        n_relabeled = 0
    
    frac_relabeled = (n_relabeled / n_same) if n_same > 0 else 0.0

    summary_rows.append({
        "repository": repo,
        "commit_size_rows": int(len(cs)),
        "pairs_rows": int(len(pairs_idxs)),
        "q_lines": Q_LINES,
        "q_files": Q_FILES,
        "thr_lines": float(thr_lines),
        "thr_files": float(thr_files),
        "outlier_commits": int(len(outlier_commits)),
        "outlier_commit_fraction": float(cs["is_outlier"].mean() if len(cs) > 0 else 0.0),
        "same_commit_pairs": n_same,
        "same_commit_pairs_relabeled": n_relabeled,
        "same_commit_pairs_relabeled_fraction": float(frac_relabeled)
    })

    if len(outlier_commits) > 0:
        out = cs.loc[cs["is_outlier"], ["repository", "commit_hash", "total_lines_added", "total_files_count", "out_due_to_lines", "out_due_to_files"]].copy()
        out["thr_lines"] = float(thr_lines)
        out["thr_files"] = float(thr_files)
        outlier_rows.append(out)

# -------------------------
# Write adjusted artefacts
# -------------------------

OUT_DIR.mkdir(parents=True, exist_ok=True)

# Copy original commit size CSV
shutil.copy2(COMMIT_SIZE_CSV, OUT_DIR / COMMIT_SIZE_CSV.name)

# Write adjusted pairs CSV
pairs_all.to_csv(OUT_DIR / PAIRS_CSV.name, index=False)

# Write summary CSV
summary_df = pd.DataFrame(summary_rows).sort_values(["same_commit_pairs_relabeled_fraction", "same_commit_pairs"], ascending=[False, False])
summary_df.to_csv(OUT_DIR / "squash_like_summary.csv", index=False)

# Write outlier commits CSV
if outlier_rows:
    outlier_df = pd.concat(outlier_rows, ignore_index=True)
    outlier_df.to_csv(OUT_DIR / "outlier_commits.csv", index=False)

# -------------------------
# Sanity-check prints
# -------------------------
print(f"Repos processed: {len(summary_df)}")
print(f"Adjusted pairs written to: {OUT_DIR / PAIRS_CSV.name}")
print(f"Summary written to: {OUT_DIR / 'squash_like_summary.csv'}")

# Global (all-repos) before/after classification distribution (quick summary check)
print(summarise("Original classification distribution (global)", pairs_all["classification"]))
print(summarise("Adjusted classification distribution (global)", pairs_all["classification_adj"]))