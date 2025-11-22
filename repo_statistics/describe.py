import pandas as pd

# Load the CSV into a DataFrame
df = pd.read_csv("apache_repo_stats.csv", parse_dates=["first_commit_date", "last_commit_date"])

# View basic descriptive statistics for numeric columns
print(df.describe())

# Optional: view first few rows to check it loaded correctly
print(df.head())

n = 10
top_n = df.sort_values("num_commits", ascending=False).head(n)
print("top num of commits")
print(top_n)

top_n = df.sort_values("project_life_days", ascending=False).head(n)
print("top project life days")
print(top_n)
