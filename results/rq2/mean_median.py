import pandas as pd

CSV_PATH = "all_results_adjusted/all_pairs_adjusted.csv"  # <-- change this
GROUP_COL = "classification"  # or "classification_adj"

INCLUDE_OUTLIERS = True  # <-- set True to include outliers

OUT_PATH = (
    "size_stats_by_classification_ALL.csv"
    if INCLUDE_OUTLIERS
    else "size_stats_by_classification_NO_OUTLIERS.csv"
)

df = pd.read_csv(CSV_PATH)

# ---- outlier filtering (optional) ----
def to_bool(x):
    if pd.isna(x):
        return False
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y", "t"}

if (not INCLUDE_OUTLIERS) and ("same_commit_is_outlier" in df.columns):
    outlier_mask = df["same_commit_is_outlier"].apply(to_bool)
    df = df[~outlier_mask].copy()

# ---- numeric conversion ----
num_cols = [
    "test_commit_total_lines", "prod_commit_total_lines",
    "test_commit_files", "prod_commit_files",
    "test_commit_java_files", "prod_commit_java_files",
]
for c in num_cols:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

# ---- sums (test + prod) ----
if "test_commit_total_lines" in df.columns and "prod_commit_total_lines" in df.columns:
    df["sum_commit_total_lines"] = df["test_commit_total_lines"].fillna(0) + df["prod_commit_total_lines"].fillna(0)

if "test_commit_files" in df.columns and "prod_commit_files" in df.columns:
    df["sum_commit_files"] = df["test_commit_files"].fillna(0) + df["prod_commit_files"].fillna(0)

if "test_commit_java_files" in df.columns and "prod_commit_java_files" in df.columns:
    df["sum_commit_java_files"] = df["test_commit_java_files"].fillna(0) + df["prod_commit_java_files"].fillna(0)

metrics = [
    "test_commit_total_lines", "prod_commit_total_lines", "sum_commit_total_lines",
    "test_commit_files", "prod_commit_files", "sum_commit_files",
    "test_commit_java_files", "prod_commit_java_files", "sum_commit_java_files",
]
metrics = [m for m in metrics if m in df.columns]

# ---- mean + median by classification ----
mean_df = df.groupby(GROUP_COL)[metrics].mean(numeric_only=True)
median_df = df.groupby(GROUP_COL)[metrics].median(numeric_only=True)

mean_df.columns = [f"{c}__mean" for c in mean_df.columns]
median_df.columns = [f"{c}__median" for c in median_df.columns]

summary = pd.concat([mean_df, median_df], axis=1).reset_index()
summary["n_rows"] = df.groupby(GROUP_COL).size().values

summary.to_csv(OUT_PATH, index=False)

print(summary)
print(f"\nSaved: {OUT_PATH}")
print(f"Included outliers: {INCLUDE_OUTLIERS}")