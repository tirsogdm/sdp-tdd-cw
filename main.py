from pydriller import Repository

repo = Repository("https://github.com/ishepard/pydriller")

for commit in repo.traverse_commits():
	print(commit.hash)
	print(commit.msg)
	print(commit.author.name)

	for file in commit.modified_files:
		print(file.filename, ' has changed')
