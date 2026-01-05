import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv('apache_repo_stats.csv')

# Filter for the top languages to keep the chart legible
top_languages = df['main_language'].value_counts().nlargest(15).index
df = df[df['main_language'].isin(top_languages)]

plt.figure(figsize=(12, 6))
sns.set_style("whitegrid")

sns.boxplot(data=df, x='main_language', y='num_commits', 
            palette="pastel", showfliers=False,
            order=df['main_language'].value_counts().index)

sns.stripplot(data=df, x='main_language', y='num_commits', 
              color="black", alpha=0.3, jitter=True,
              order=df['main_language'].value_counts().index)

plt.xticks(rotation=45, ha='right')

plt.yscale('log')
plt.xlabel("Main Language")
plt.ylabel("Commit Volume (Log Scale)")

counts = df['main_language'].value_counts()
new_labels = [f"{lang}\n(n={counts[lang]})" for lang in df['main_language'].value_counts().index]
plt.gca().set_xticklabels(new_labels)

plt.tight_layout()

plt.savefig('fig1.png')
