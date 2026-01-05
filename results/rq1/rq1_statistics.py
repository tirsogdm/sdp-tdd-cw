import pandas as pd

CSV_PATH = "all_summary_adjusted.csv"

METRICS = {
    "test_first_adj_%": "Test-first adjusted (%)",
    "prod_first_adj_%": "Production-first (%)",
    "same_commit_adj_%": "Same-commit (%)",
}

def compute_stats(series: pd.Series) -> dict:
    """Compute summary statistics for a numeric pandas Series."""
    series = pd.to_numeric(series, errors="coerce").dropna()

    return {
        "count": series.count(),
        "mean": series.mean(),
        "std_dev": series.std(),
        "min": series.min(),
        "max": series.max(),
    }

def main():
    df = pd.read_csv(CSV_PATH)

    print("\nRepository-level statistics\n" + "=" * 35)

    for column, label in METRICS.items():
        if column not in df.columns:
            print(f"\n⚠ Column '{column}' not found — skipping")
            continue

        stats = compute_stats(df[column])

        print(f"\n{label}")
        print("-" * len(label))
        print(f"Repositories analysed: {stats['count']}")
        print(f"Mean: {stats['mean']:.2f}%")
        print(f"Standard deviation: {stats['std_dev']:.2f}")
        print(f"Minimum: {stats['min']:.2f}%")
        print(f"Maximum: {stats['max']:.2f}%")

if __name__ == "__main__":
    main()
