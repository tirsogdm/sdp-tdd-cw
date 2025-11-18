from pydriller import Repository

"""A simple, example script to traverse the pydriller repository and print commit details."""

repo = Repository("https://github.com/ishepard/pydriller")

for commit in repo.traverse_commits():
	print(commit.hash)
	print(commit.msg)
	print(commit.author.name)

	for file in commit.modified_files:
		print(file.filename, ' has changed')
