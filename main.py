from pydriller import Repository
from git import Repo

"""A simple, example script to traverse the pydriller repository and print commit details."""

repo_path = "/Users/tirso/Desktop/UCL/Term 1/COMP0104_SDP/CW2/sdp-tdd-cw"
repo = Repository(repo_path)
r = Repo(repo_path)

print("HEAD is at:", r.head.commit.hexsha)

commits = []

for commit in repo.traverse_commits():	
	commits.append(commit)

print(f"Total commits: {len(commits)}")
print("First commit details:")
print(f"-- Hash: {commits[0].hash}")
print(f"-- Message: {commits[0].msg}")
print(f"-- Author: {commits[0].author.name}")
print(f"-- Date: {commits[0].author_date}")
print("Last commit details:")
print(f"-- Hash: {commits[-1].hash}")
print(f"-- Message: {commits[-1].msg}")
print(f"-- Author: {commits[-1].author.name}")
print(f"-- Date: {commits[-1].author_date}")