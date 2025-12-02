import argparse
import json
import re
from collections import defaultdict

import pandas as pd


# Pre-compiling patterns for performance and accuracy.
# \b ensures word boundaries (prevents "net" matching "magnet").
# re.IGNORECASE handles capitalization.
def compile_pattern(keywords):
    # Escape keywords to handle special chars like "c++" or "ci-"
    escaped = [re.escape(k) for k in keywords]
    pattern_str = r"\b(" + "|".join(escaped) + r")\b"
    return re.compile(pattern_str, re.IGNORECASE)


# Configuration mapping
CATEGORY_KEYWORDS = {
    "Retired/Incubating/Attic": [
        "incubator",
        "incubating",
        "retired",
        "attic",
        "sandbox",
        "proposal",
        "harmony",
    ],
    "Build and Testing Tools": [
        "maven",
        "ant",
        "buildr",
        "gradle",
        "surefire",
        "jenkins",
        "compiler",
        "archetype",
        "plugin",
        "verifier",
        "qa",
        "ci",
        "unittest",
        "testing",
        "mock",
    ],
    "Infrastructure/DevOps Tooling": [
        "infrastructure",
        "site",
        "website",
        "doc",
        "docs",
        "docker",
        "helm",
        "k8s",
        "kubernetes",
        "admin",
        "dashboard",
        "devops",
        "travis",
        "appveyor",
        "container",
        "deployment",
    ],
    "Distributed Systems/Databases": [
        "hadoop",
        "spark",
        "kafka",
        "flink",
        "zookeeper",
        "cassandra",
        "hbase",
        "hive",
        "cloud",
        "cluster",
        "storm",
        "samza",
        "tez",
        "pig",
        "oozie",
        "sqoop",
        "flume",
        "avro",
        "parquet",
        "ignite",
        "geode",
        "kudu",
        "drill",
        "impala",
        "kylin",
        "phoenix",
        "pulsar",
        "rocketmq",
        "dubbo",
        "skywalking",
        "shardingsphere",
        "doris",
        "iotdb",
        "couchdb",
        "db",
        "database",
        "store",
        "nosql",
        "sql",
        "mesos",
        "helix",
        "curator",
        "bookkeeper",
        "ozone",
        "submarine",
        "airflow",
        "superset",
        "jpa",
        "jdbc",
        "persistence",
    ],
    "Application/Web Frameworks": [
        "struts",
        "tapestry",
        "wicket",
        "faces",
        "web",
        "framework",
        "portal",
        "django",
        "tomcat",
        "httpd",
        "server",
        "servlet",
        "jsp",
        "sling",
        "camel",
        "cxf",
        "axis",
        "servicemix",
        "karaf",
        "geronimo",
        "openwebbeans",
        "tomee",
        "nifi",
        "cloudstack",
        "turbine",
        "velocity",
        "freemarker",
        "tiles",
        "guacamole",
        "rest",
        "api",
        "mvc",
    ],
    "Domain-Specific Libraries": [
        "pdf",
        "xml",
        "codec",
        "math",
        "image",
        "audio",
        "video",
        "compress",
        "crypt",
        "nlp",
        "search",
        "lucene",
        "solr",
        "tika",
        "poi",
        "opennlp",
        "xerces",
        "xalan",
        "batik",
        "fop",
        "chemistry",
        "mahout",
        "openoffice",
        "spamassassin",
        "geo",
        "spatial",
        "learning",
        "ai",
        "machine learning",
    ],
    "Core Libraries/Utilities": [
        "commons",
        "lib",
        "util",
        "log",
        "io",
        "net",
        "lang",
        "collections",
        "runtime",
        "apr",
        "mina",
        "netty",
        "thrift",
        "jmeter",
        "logging",
        "serializer",
    ],
}

# Compile all patterns once at startup
CATEGORY_PATTERNS = {
    cat: compile_pattern(kws) for cat, kws in CATEGORY_KEYWORDS.items()
}


def categorize_repo(repo):
    name = repo.get("name", "")
    desc = repo.get("description") or ""

    full_text = f"{name} {desc}"

    scores = defaultdict(int)

    # 1. Special hard check for Retired/Incubating
    # Usually if it's retired, we don't care about the tech stack anymore.
    if CATEGORY_PATTERNS["Retired/Incubating/Attic"].search(full_text):
        return "Retired/Incubating/Attic"

    # 2. Score other categories
    for category, pattern in CATEGORY_PATTERNS.items():
        if category == "Retired/Incubating/Attic":
            continue

        # Count all occurrences of keywords in the text
        matches = pattern.findall(full_text)
        scores[category] = len(matches)

    if not scores:
        return None

    best_category = max(scores, key=scores.get)

    if scores[best_category] == 0:
        return None

    return best_category

def categorize_repos(input_file, output_file, repo_filter):
    try:
        with open(input_file, "r") as f:
            repos = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        return

    mapped_data = []

    # Only process repos that match the filter
    filtered_repos = [r for r in repos if repo_filter(r)]

    print(f"Processing {len(filtered_repos)} repositories...")

    for repo in filtered_repos:
        cat = categorize_repo(repo)
        mapped_data.append(
            {
                "project": repo.get("name"),
                "category": cat,
                "description_snippet": (repo.get("description") or "")[
                    :50
                ],  # Helpful for debugging CSV
            }
        )

    df = pd.DataFrame(mapped_data)
    df.to_csv(output_file, index=False)

    print(f"Successfully saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Categorize repositories based on keywords."
    )
    parser.add_argument("input_file", help="Path to the JSON input file")
    parser.add_argument("output_file", help="Path to the CSV output file")
    parser.add_argument(
        "--lang", default="Java", help="Language to filter by (default: Java)"
    )

    args = parser.parse_args()

    # Dynamic filter based on CLI argument
    def check_criteria(repo):
        # robust check for language existence
        return repo.get("language") == args.lang

    categorize_repos(args.input_file, args.output_file, check_criteria)
