# Java Test-Driven Development (TDD) Analyzer

## Installation

### Requirements

- Dependencies in `requirements.txt` (`pydriller`, `python-dateutil`)

```bash
pip install -r requirements.txt
```

> Activate the virtual env or make the python file executable using chmod

## Clone Repositories (run this before the analyzer)

Use `clone_repos.py` to pull the target Apache repositories listed in your CSV.

```bash
# Clone all repos from the CSV into ./repos
python clone_repos.py ./repos --csv final_java_candidates_part1.csv --workers 8
```

`clone_repos.py` options:

- `output_dir` (positional): destination folder for the repositories.
- `--csv`: path to the CSV containing the repo list.
- `--workers`: number of parallel processes (default: 4).

## Usage

### Basic Usage

```bash
python tdd_mining.py ./repos
```

### Options

```
positional arguments:
  repos_dir             Directory containing cloned repositories

options:
  -h, --help            Show help message
  -o                    Output file prefix (default: tdd) (change to keep old files if needed)
  --include-repos       Only analyze specific repositories (debugging)
  --since               Analyze commits since date (YYYY-MM-DD)
  --to                  Analyze commits until date (YYYY-MM-DD)
  --max-commits         Maximum commits to analyze per repository
  --workers             Number of parallel workers (default: 80% of CPU cores)
  --no-unmatched        Skip generating the unmatched test files CSV
  -v                    Enable verbose logging (Set flag to look cool)
```

### Examples

```bash
# Analyze all repos in a directory
python tdd_mining.py ./repos

# Analyze specific repositories (useful for testing)
python tdd_mining.py ./repos --include-repos commons-io commons-lang

# Limit commits and workers
python tdd_mining.py ./repos --max-commits 5000 --workers 8

# Skip unmatched CSV output
python tdd_mining.py ./repos --no-unmatched

# Custom output prefix
python tdd_mining.py ./repos -o my_analysis
```

## Output Files

The analyzer generates 5 output files:

### 1. `tdd_pairs.csv`

All matched test-production pairs with classifications.

| Column                    | Description                                         |
| ------------------------- | --------------------------------------------------- |
| `repository`              | Repository name                                     |
| `classification`          | TEST_FIRST, SAME_COMMIT, or PRODUCTION_FIRST        |
| `test_file`               | Path to test file                                   |
| `prod_file`               | Path to production file                             |
| `test_class`              | Test class name                                     |
| `prod_class`              | Production class name                               |
| `test_commit`             | Commit hash where test was added                    |
| `prod_commit`             | Commit hash where production file was added         |
| `test_date`               | Date test was added                                 |
| `prod_date`               | Date production file was added                      |
| `test_author`             | Author who added test                               |
| `prod_author`             | Author who added production file                    |
| `time_diff_hours`         | Time difference in hours                            |
| `time_diff_days`          | Time difference in days                             |
| `test_file_lines`         | Lines added in test file                            |
| `test_commit_total_lines` | Total lines in test's commit                        |
| `test_commit_files`       | Total files in test's commit                        |
| `test_commit_java_files`  | Java files in test's commit                         |
| `prod_file_lines`         | Lines added in production file                      |
| `prod_commit_total_lines` | Total lines in production's commit                  |
| `prod_commit_files`       | Total files in production's commit                  |
| `prod_commit_java_files`  | Java files in production's commit                   |
| `pair_status`             | ACTIVE, TEST_DELETED, PROD_DELETED, or BOTH_DELETED |

### 2. `tdd_summary.csv`

Per-repository statistics.

| Column                      | Description                              |
| --------------------------- | ---------------------------------------- |
| `repository`                | Repository name                          |
| `analysis_duration_seconds` | Time to analyze                          |
| `total_commits`             | Total commits analyzed                   |
| `test_files_added`          | Total test files found                   |
| `test_helpers`              | Test helper files excluded               |
| `prod_files_added`          | Total production files found             |
| `matched_pairs`             | Successfully matched pairs               |
| `multi_test_prods`          | Production files with multiple tests     |
| `test_first_count`          | Number of TEST_FIRST pairs               |
| `same_commit_count`         | Number of SAME_COMMIT pairs              |
| `prod_first_count`          | Number of PRODUCTION_FIRST pairs         |
| `test_first_%`              | Percentage TEST_FIRST                    |
| `same_commit_%`             | Percentage SAME_COMMIT                   |
| `prod_first_%`              | Percentage PRODUCTION_FIRST              |
| `unmatched_test_files`      | Tests without matching production files  |
| `unmatched_prod_files`      | Production files without matching tests  |
| `match_rate_%`              | Percentage of tests successfully matched |

### 3. `tdd_commits.csv`

Commit size metrics for each commit analyzed.

| Column              | Description                 |
| ------------------- | --------------------------- |
| `repository`        | Repository name             |
| `commit_hash`       | Short commit hash           |
| `commit_date`       | Commit timestamp            |
| `author`            | Commit author               |
| `total_lines_added` | Total lines added in commit |
| `total_files_count` | Total files modified        |
| `java_files_count`  | Java files modified         |

### 4. `tdd_unmatched.csv`

Unmatched test files for debugging (optional, use `--no-unmatched` to skip).

| Column              | Description                           |
| ------------------- | ------------------------------------- |
| `repository`        | Repository name                       |
| `test_file`         | Test file path                        |
| `test_class`        | Test class name                       |
| `candidates_tried`  | Production class candidates attempted |
| `original_filepath` | Original path if renamed              |
| `commit_hash`       | Commit where test was added           |
| `commit_date`       | Date test was added                   |
| `author`            | Author who added test                 |
| `is_helper`         | Whether identified as test helper     |

NOTE: 'is_helper' is currently redundant (always returns false), used it earlier when helpers were included in this .csv

### 5. `tdd_report.json`

Complete analysis data in JSON format, including all fields (+those commented out in the CSVs).

## Classifications

| Classification     | Meaning                               |
| ------------------ | ------------------------------------- |
| `TEST_FIRST`       | Test committed BEFORE production file |
| `SAME_COMMIT`      | Test and production in same commit    |
| `PRODUCTION_FIRST` | Production committed BEFORE test      |

## Pair Status

| Status         | Meaning                                    |
| -------------- | ------------------------------------------ |
| `ACTIVE`       | Both test and production files still exist |
| `TEST_DELETED` | Test was deleted, production still exists  |
| `PROD_DELETED` | Production was deleted, test still exists  |
| `BOTH_DELETED` | Both files were deleted                    |

## Match Methods

| Method                          | Description                                                 |
| ------------------------------- | ----------------------------------------------------------- |
| `exact_class_same_package`      | Class names match and same package (highest confidence)     |
| `exact_class_similar_package`   | Class names match, packages share ≥3 segments               |
| `exact_class_different_package` | Class names match but different packages (lower confidence) |

## What Gets Excluded

### Integration Tests (excluded from analysis)

- Files ending in `IT.java`, `ITCase.java`, `Spec.java`
- Files in `/src/it/`, `/its/`, `integration-tests/` directories
- Files ending in `IntegrationTest.java`, `AcceptanceTest.java`, `E2ETest.java`

### Test Helpers (tracked but not matched)

- `Abstract*Test*.java`, `*TestCase.java`, `*TestUtils.java`
- `Mock*.java`, `Stub*.java`, `Fake*.java`
- `*TestHelper.java`, `*TestBase.java`, `*TestSupport.java`

### Non-Production Files

- `package-info.java`, `module-info.java`
- Files in `/generated/`, `/target/`, `/build/` directories

### Generic Class Names (filtered from matching)

- Project names, Common prefixes, Utility patterns, Common classes.
- All entries in `generic_terms.py`

## How It Works

1. **Phase 1**: Scan all commits chronologically, collecting ADD/RENAME/DELETE events
2. **Phase 2**: Build rename chains and file timelines to handle renames and delete/re-add scenarios
3. **Phase 3**: Classify files as tests or production, extract class names and packages
4. **Phase 4**: Match tests to production files using tokenization (more info ahead) and package similarity
5. **Phase 5**: Classify pairs based on commit timestamps
6. **Phase 6**: Generate output files

## CamelCase Tokenization

The analyzer uses CamelCase tokenization to extract production class candidates from test names:

```
IOUtilsCopyDirectoryTest
  → Tokens: ['IO', 'Utils', 'Copy', 'Directory', 'Test']
  → After removing 'Test': ['IO', 'Utils', 'Copy', 'Directory']
  → Candidates: ['IOUtilsCopyDirectory', 'IOUtilsCopy', 'IOUtils']
```

This handles test names like `FileUtilsListFilesTest` → matches `FileUtils.java`.
Note: Minimum length has to be > 3.
