import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def plot_box_by_classification_combined_lines(
    df: pd.DataFrame,
    class_col: str = "classification",
    outlier_col: str = "same_commit_is_outlier",
    ignore_outliers: bool = True,
    test_lines_col: str = "test_commit_total_lines",
    prod_lines_col: str = "prod_commit_total_lines",
    min_size: float = 1.0,
    log_y: bool = True,
    title: str | None = None,
    figsize=(5, 5),
    save_path: str | None = None,
    summary_csv_path: str | None = None,
    annotate_stats: bool = True,
    stats_fmt: str = "{:.0f}",
    box_spacing: float = 1,
    box_width: float = 0.5,
):
    data = df.copy()
    
    if outlier_col in data.columns:
        data[outlier_col] = data[outlier_col].fillna(False).astype(bool)

    if ignore_outliers and outlier_col in data.columns:
        data = data[~data[outlier_col]]

    needed = [class_col, test_lines_col, prod_lines_col]
    data = data[needed].copy()

    data[test_lines_col] = pd.to_numeric(data[test_lines_col], errors="coerce")
    data[prod_lines_col] = pd.to_numeric(data[prod_lines_col], errors="coerce")

    data["combined_commit_total_lines"] = data[test_lines_col] + data[prod_lines_col]
    data = data[[class_col, "combined_commit_total_lines"]].dropna()
    data = data[np.isfinite(data["combined_commit_total_lines"])]

    if min_size is not None:
        data = data[data["combined_commit_total_lines"] >= min_size]

    # ---- Summary stats ----
    grp = data.groupby(class_col)["combined_commit_total_lines"]
    summary = grp.agg(
        n="size",
        mean="mean",
        median="median",
        q1=lambda x: x.quantile(0.25),
        q3=lambda x: x.quantile(0.75),
        p5=lambda x: np.percentile(x, 5),
        p95=lambda x: np.percentile(x, 95),
    ).reset_index()

    preferred_order = ["SAME_COMMIT", "PRODUCTION_FIRST", "TEST_FIRST"]
    present = summary[class_col].tolist()

    order = [c for c in preferred_order if c in present]
    order += [c for c in present if c not in order]
    
    summary = summary.set_index(class_col).loc[order].reset_index()

    grouped = [
        data.loc[data[class_col] == cls, "combined_commit_total_lines"].to_numpy()
        for cls in order
    ]
    ns = [len(g) for g in grouped]

    fig, ax = plt.subplots(figsize=figsize)

    # ---- NEW: tighter positions + widths ----
    positions = np.arange(1, len(order) + 1) * box_spacing

    bp = ax.boxplot(
        grouped,
        positions=positions,      # <--- NEW
        widths=box_width,         # <--- NEW
        showfliers=False,
        whis=(5, 95),
        showmeans=True,
        meanline=False,
        meanprops=dict(marker="D", markersize=6),
    )

    # custom x tick labels at our positions
    ax.set_xticks(positions)
    ax.set_xticklabels([f"{cls}\n(n={n})" for cls, n in zip(order, ns)])
    ax.set_xticklabels([f"{cls}\n(n={n})" for cls, n in zip(order, ns)], fontsize=8)
    ax.tick_params(axis="x", pad=2)

    # tighten left/right whitespace
    ax.set_xlim(positions[0] - box_spacing, positions[-1] + box_spacing)

    ax.set_ylabel(f"{test_lines_col} + {prod_lines_col}")
    if log_y:
        ax.set_yscale("log")

    if title is None:
        title = "Box plot of combined commit size by classification" + (
            " (outliers removed)" if ignore_outliers else " (with outliers)"
        )
    # ax.set_title(title)
    ax.grid(True, which="both", axis="y", linestyle="--", linewidth=0.5, alpha=0.5)

    # ---- Annotate mean + median on the plot ----
    if annotate_stats:
        y_max = summary["p95"].to_numpy()
        means = summary["mean"].to_numpy()
        medians = summary["median"].to_numpy()

        offset = 1.15 if log_y else 1.02

        for x, y, mu, med in zip(positions, y_max, means, medians):
            text = f"mean={stats_fmt.format(mu)}\nmedian={stats_fmt.format(med)}"
            ax.text(x, y * offset, text, ha="center", va="bottom", fontsize=9)

        ax.margins(y=0.15)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=300, bbox_inches="tight")
        print(f"Saved plot to: {save_path}")

    if summary_csv_path:
        summary.to_csv(summary_csv_path, index=False)
        print(f"Saved summary table to: {summary_csv_path}")

    # plt.show()
    return summary


df = pd.read_csv("all_results_adjusted/all_pairs_adjusted.csv")
plot_box_by_classification_combined_lines(df, ignore_outliers=False,
    save_path="boxplot_combined_commit_size_w_outliers.png")
plot_box_by_classification_combined_lines(df, ignore_outliers=True,
    save_path="boxplot_combined_commit_size_no_outliers.png")