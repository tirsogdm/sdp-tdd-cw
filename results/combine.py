"""
Need all the partial files in the same folder as this script like:
- tdd_1_commits.csv
- tdd_2_commits.csv
- ...
"""

import pandas as pd


def combine(filenames, output):
    df_list = list()

    for filename in filenames:
        df = pd.read_csv(filename)
        df_list.append(df)

    big_frame = pd.concat(df_list, ignore_index=True)

    big_frame.to_csv(output, index=False)


if __name__ == "__main__":
    tables = ["commits", "pairs", "unmatched", "summary"]

    for table in tables:
        files = [f"tdd_{num}_{table}.csv" for num in range(1, 7)]

        combine(files, f"all_{table}.csv")
