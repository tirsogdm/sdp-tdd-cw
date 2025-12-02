import json
import sys

import pandas as pd
from categ import categorize_repo


def add_column_category(df, json_data, name_col="repo"):
    """
    1. Looks up the full repo object from json_data using the df[name_col].
    2. Runs the categorization logic on that full object.
    3. Returns the DF with a new 'category' column.
    
    :param df: The target DataFrame containing a column of repo names.
    :param json_data: The list of dicts loaded from the JSON file.
    :param name_col: The name of the column in df that holds the repo name.
    """

    repo_lookup = {repo.get("name", ""): repo for repo in json_data}

    def get_category_for_row(row_name):
        if pd.isna(row_name):
            return None
                    
        repo_object = repo_lookup.get(row_name)
        
        if repo_object:
            return categorize_repo(repo_object) 
        else:
            return None

    # 4. Apply to the DataFrame
    df['category'] = df[name_col].apply(get_category_for_row)
    
    return df

if __name__ == "__main__":
    repos_json = sys.argv[1]
    original_csv = sys.argv[2]
    output_csv = sys.argv[3]

    with open(repos_json, "r") as f:
        all_repos_data = json.load(f)

    df_projects = pd.read_csv(original_csv) 
    
    print(f"Before: {df_projects.shape}")

    df_categorized = add_column_category(df_projects, all_repos_data, name_col="repo")

    df_categorized.to_csv(output_csv, index=False)
    print(f"After: {df_categorized.shape}")
    print(df_categorized.head())