import pandas as pd
import matplotlib.pyplot as plt
import numpy as np


CSV_PATH = "all_summary_adjusted.csv"

CSV_PATH_NO_OUTLIERS = CSV_PATH
CSV_PATH_WITH_OUTLIERS = "all_summary.csv"

COLUMNS = {
    "test_first_adj_%": "Test-first (%)",
    "prod_first_adj_%": "Production-first (%)",
    "same_commit_adj_%": "Same-commit (%)",
}

plt.rcParams.update({
    "font.size": 10,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "figure.dpi": 300,
})

def draw_histogram():
    df = pd.read_csv(CSV_PATH)

    #df_no = pd.read_csv(CSV_PATH_NO_OUTLIERS)
    #df_all = pd.read_csv(CSV_PATH_WITH_OUTLIERS)

    fig, axes = plt.subplots(
        nrows=3,
        ncols=1,
        figsize=(4.5, 6.5),
        sharex=True,
        constrained_layout=True
    )

    bins = np.linspace(0, 100, 26)

    for ax, (adj_col, label) in zip(axes, COLUMNS.items()):
        raw_col = adj_col.replace("_adj", "")

        values_adj = pd.to_numeric(df[adj_col], errors="coerce").dropna()
        values_raw = pd.to_numeric(df[raw_col], errors="coerce").dropna()

        # Outliers excluded
        ax.hist(
            values_adj,
            bins=bins,
            edgecolor="black",
            linewidth=0.6,
            alpha=0.85,
            label="Outliers excluded"
        )

        # Outliers included
        ax.hist(
            values_raw,
            bins=bins,
            edgecolor="black",
            linewidth=0.6,
            alpha=0.45,
            label="Outliers included"
        )

        ax.set_ylabel("Repositories")
        ax.set_title(label, loc="left")
        ax.legend(frameon=False, fontsize=8)

    axes[-1].set_xlabel("Percentage of test–production pairs (%)")
    axes[-1].set_xlim(0, 100)

    fig.savefig("figure1_distributions_overlay.pdf")
    fig.savefig("figure1_distributions_overlay.png")

    plt.close(fig)

def draw_boxplot(df):
    data = [
        pd.to_numeric(df["test_first_adj_%"], errors="coerce").dropna(),
        pd.to_numeric(df["prod_first_adj_%"], errors="coerce").dropna(),
        pd.to_numeric(df["same_commit_adj_%"], errors="coerce").dropna(),
    ]

    labels = [
        "Test-first",
        "Production-first",
        "Same-commit",
    ]

    fig, ax = plt.subplots(figsize=(4.5, 3.5))

    bp = ax.boxplot(
        data,
        labels=labels,
        widths=0.4,
        patch_artist=False,
        showfliers=False
    )

    ax.set_ylabel("Adjusted Percentage (%)")
    ax.set_ylim(0, 100)

    for i, values in enumerate(data, start=1):
        mean = values.mean()
        median = values.median()

        # Mean marker (diamond)
        ax.plot(
            i,
            mean,
            marker="D",
            color="green",
            markersize=3,
            zorder=3
        )

        y_values = [0, 30, 101, 91]

        ax.text(
            i,
            y_values[i],
            f"mean = {mean:.1f}\nmedian = {median:.1f}",
            ha="center",
            va="bottom",
            fontsize=7
        )

    fig.savefig("figure2_boxplot.pdf")
    fig.savefig("figure2_boxplot.png")
    plt.close(fig)


def main():
    df = pd.read_csv(CSV_PATH)
    draw_boxplot(df)

if __name__ == "__main__":
    main()
