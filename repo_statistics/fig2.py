import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv('final_java_candidates.csv')

cols = ['java_files', 'test_files', 'num_commits', 'project_life_days', 'test_ratio']

summary = df[cols].agg(['min', 'median', 'max', 'mean', 'std']).transpose()
summary.columns = ['Min', 'Median', 'Max', 'Mean', 'Std. Dev.']

print("--- LaTeX Table Code ---")
latex_out = summary.style.format(precision=2).to_latex(
    column_format='lrrrrr',
    hrules=True,
    caption="Descriptive statistics of the selected Java repositories.",
    label="tab:repo_stats"
)
print(latex_out)




df['has_ci_system'] = df['has_ci_system'].map({True: 'Yes', False: 'No', 1: 'Yes', 0: 'No'})
df['has_build_system'] = df['has_build_system'].map({True: 'Yes', False: 'No', 1: 'Yes', 0: 'No'})


fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
sns.set_style("whitegrid")

# Subplot 1: Distribution of Test Ratio
sns.boxplot(y=df['test_ratio'], ax=ax1, color='#a1c9f4', showfliers=False)
sns.stripplot(y=df['test_ratio'], ax=ax1, color='black', alpha=0.3, jitter=True)
ax1.set_title("A: Distribution of Test-to-Code Ratio", fontsize=14, fontweight='bold')
ax1.set_ylabel("Test Ratio (Test Files / Total Java Files)")

# Subplot 2: CI and Build System Adoption
infrastructure = df[['has_ci_system', 'has_build_system']].apply(pd.Series.value_counts).T
infrastructure.plot(kind='bar', stacked=True, ax=ax2, color=['#ff9999','#66b3ff'])
ax2.set_title("B: Automation Infrastructure Adoption", fontsize=14, fontweight='bold')
ax2.set_ylabel("Number of Projects")
ax2.set_xlabel("Feature")
ax2.legend(title="Adopted?")
plt.xticks(rotation=0)

plt.tight_layout()
plt.savefig('fig2.png', dpi=300)
print("\nFigure saved as 'fig2.png'")
