"""
Finds the missing repos from the split parts compared to the original dataset.

entries:
    - final_java_candidates.csv: 461

    - final_java_candidates_part1: 79
    - final_java_candidates_part2: 79
    - final_java_candidates_part3: 79
    - final_java_candidates_part4: 79
    - final_java_candidates_part5: 75
    ---------------------------------
                           total: 391

The final java candidates part 1-4 have 79 entries, part 5 has 75 which adds up to 391.
However, in our final candidates there are 461 entries so some were lost.

The missing part6 has 70 entries.
"""

import pandas as pd


if __name__ == "__main__":
    files = [f"final_java_candidates_part{num}.csv" for num in range(1, 6)]

    df_list = list()

    for filename in files:
        df = pd.read_csv(filename)
        df_list.append(df)

    combined_parts = pd.concat(df_list, ignore_index=True)
    original = pd.read_csv("final_java_candidates.csv")

    print("Combined:", combined_parts.shape)
    print("Original:", original.shape)

    matching_rows = (
        original[["repo"]]
        .apply(tuple, axis=1)
        .isin(combined_parts[["repo"]].apply(tuple, axis=1))
    )

    missing = original[~matching_rows]

    print(missing.shape)
    missing.to_csv("final_java_candidates_part6.csv", index=False)
