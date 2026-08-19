# SDP TDD Coursework Repository

This repository contains the data-mining pipeline used to study **test-driven development (TDD) signals** in Apache Java projects.

At a high level, the workflow is:
1. Collect Apache repository statistics.
2. Filter and shortlist Java repositories likely suitable for analysis.
3. Clone shortlisted repositories.
4. Mine commit history to classify test/production file pairs as:
   - `TEST_FIRST`
   - `SAME_COMMIT`
   - `PRODUCTION_FIRST`
5. Aggregate and plot research outputs.

## Repository Structure

- `/home/runner/work/sdp-tdd-cw/sdp-tdd-cw/tdd_mining/`  
  Main mining engine (`tdd_mining.py`), clone helper (`clone_repos.py`), and detailed analyzer documentation.

- `/home/runner/work/sdp-tdd-cw/sdp-tdd-cw/repo_statistics/`  
  Scripts to fetch Apache repo metadata and build candidate lists.

- `/home/runner/work/sdp-tdd-cw/sdp-tdd-cw/repo_categories/`  
  Heuristic categorization scripts for repositories.

- `/home/runner/work/sdp-tdd-cw/sdp-tdd-cw/results/`  
  Post-processing scripts and generated figures/tables for RQ analyses.

- `/home/runner/work/sdp-tdd-cw/sdp-tdd-cw/`  
  Additional exploratory/analysis scripts and notes.

## Setup

Install dependencies for the two main script groups:

```bash
pip install -r /home/runner/work/sdp-tdd-cw/sdp-tdd-cw/repo_statistics/requirements.txt
pip install -r /home/runner/work/sdp-tdd-cw/sdp-tdd-cw/tdd_mining/requirements.txt
```

## Typical Usage

### 1) Build a candidate repository list

```bash
python /home/runner/work/sdp-tdd-cw/sdp-tdd-cw/repo_statistics/main.py --token <GITHUB_TOKEN> --org apache
python /home/runner/work/sdp-tdd-cw/sdp-tdd-cw/repo_statistics/potential_candidates.py --token <GITHUB_TOKEN>
python /home/runner/work/sdp-tdd-cw/sdp-tdd-cw/repo_statistics/final_candidates.py
```

### 2) Clone repositories to analyze

```bash
python /home/runner/work/sdp-tdd-cw/sdp-tdd-cw/tdd_mining/clone_repos.py ./repos --csv final_java_candidates_part1.csv --workers 8
```

### 3) Run the TDD mining analysis

```bash
python /home/runner/work/sdp-tdd-cw/sdp-tdd-cw/tdd_mining/tdd_mining.py ./repos
```

For full analyzer options and output schema, see:
- `/home/runner/work/sdp-tdd-cw/sdp-tdd-cw/tdd_mining/README.md`

## Outputs

Main generated artifacts include:
- `tdd_pairs.csv`
- `tdd_summary.csv`
- `tdd_commits.csv`
- `tdd_unmatched.csv` (optional)
- `tdd_report.json`

Plus aggregated/visual outputs under `results/`.
