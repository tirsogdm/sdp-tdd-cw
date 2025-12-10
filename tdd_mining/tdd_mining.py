#!/usr/bin/env python3

import argparse
import csv
import json
import logging
import multiprocessing as mp
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from generic_terms import GENERIC_TERMS
from pydriller import Repository

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(processName)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Change logging based on flag
def configure_pydriller_logging(verbose: bool):
    if not verbose:
        logging.getLogger("pydriller").setLevel(logging.WARNING)
        logging.getLogger("pydriller.repository").setLevel(logging.WARNING)


# =============================================================================
# Java-Specific Patterns
# =============================================================================

# Exclusion patterns (not production code)
JAVA_EXCLUDE_PATTERNS = [
    r".*package-info\.java$",
    r".*module-info\.java$",
    r".*/generated/.*\.java$",
    r".*/target/.*\.java$",
    r".*/build/.*\.java$",
]

# Patterns that indicate a file is a test HELPER, not an actual test
# These are support files that dont test a specific production class
TEST_HELPER_PATTERNS = [
    r"^Abstract.*Test.*\.java$",  # AbstractMonitorTest (base class)
    r"^.*TestCase\.java$",  # FileBasedTestCase
    r"^.*TestUtils?\.java$",  # TestUtils, TestUtil
    r"^.*TestHelper\.java$",
    r"^.*TestBase\.java$",
    r"^.*TestSupport\.java$",
    r"^.*TestResources?\.java$",
    r"^Mock.*\.java$",  # MockSerializedClass
    r"^Stub.*\.java$",
    r"^Fake.*\.java$",
    r"^Dummy.*\.java$",
    r"^.*Benchmark\.java$",  # Benchmarks
    r"^.*TestArguments?\.java$",
    r"^.*TestConstants?\.java$",
    r"^.*TestFixture\.java$",
    r"^.*Assertions?\.java$",  # CounterAssertions
    r"^.*Adapter\.java$",  # IOIntStreamAdapter
    r"^.*Proxy\.java$",  # FileChannelProxy
    r"^.*Wrapper\.java$",
    r"^ThrowOn.*\.java$",  # ThrowOnCloseReader
    r"^.*Listener\.java$",  # CollectionFileListener
    r"^Custom.*Exception\.java$",
    r"^.*ForTest\.java$",
    r"^.*TestFactory.*\.java$",
    r"^Broken.*\.java$",  # BrokenTestFactories
]


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class JavaFileInfo:
    """Information about a Java file entry."""

    filepath: str  # Current/final filepath
    filename: str
    class_name: str  # Current class name
    base_class_name: str  # The production class this tests (for test files)
    package_path: str
    commit_hash: str
    commit_date: datetime
    author: str
    is_test: bool
    is_test_helper: bool  # True if this is a test utility/helper, not an actual test

    # Lines and commit size metrics
    file_lines_added: int = 0  # Lines added for THIS file
    commit_total_lines_added: int = 0  # Total lines added in the commit
    commit_files_count: int = 0  # Total files modified in the commit
    commit_java_files_count: int = 0  # Java files modified in the commit

    # Rename tracking
    original_filepath: str = None

    # Deletion tracking
    is_deleted: bool = False
    deletion_date: datetime = None  # When file was deleted
    deletion_commit: str = None  # Commit hash where file was deleted

    # All class names this file has ever had (for matching renamed files)
    all_class_names: list = field(default_factory=list)

    # All package paths this file has ever had
    all_package_paths: list = field(default_factory=list)


@dataclass
class TestProductionPair:
    """A matched pair of test and production files."""

    test_file: str
    prod_file: str
    test_class: str
    prod_class: str
    test_commit: str
    prod_commit: str
    test_date: datetime
    prod_date: datetime
    test_author: str
    prod_author: str
    classification: str
    time_diff_hours: float
    # time_diff_category: str
    match_method: str

    # Commit size metrics for test
    test_file_lines: int = 0
    test_commit_total_lines: int = 0
    test_commit_files: int = 0
    test_commit_java_files: int = 0

    # Commit size metrics for prod
    prod_file_lines: int = 0
    prod_commit_total_lines: int = 0
    prod_commit_files: int = 0
    prod_commit_java_files: int = 0

    # Rename tracking
    test_was_renamed: bool = False
    prod_was_renamed: bool = False
    test_original_file: str = None
    prod_original_file: str = None

    # Deletion tracking - differentiates truly deleted files from renamed ones
    # pair_status: ACTIVE (both exist), TEST_DELETED, PROD_DELETED, BOTH_DELETED
    # Case where a test-prod pair existed in the past but does not anymore
    pair_status: str = "ACTIVE"
    test_is_deleted: bool = False
    prod_is_deleted: bool = False
    test_deletion_date: datetime = None
    prod_deletion_date: datetime = None
    test_deletion_commit: str = None
    prod_deletion_commit: str = None


@dataclass
class RepositoryAnalysis:
    """Complete analysis for a repository."""

    repo_name: str
    repo_path: str
    analysis_date: str
    analysis_duration_seconds: float = 0.0
    total_commits: int = 0
    total_java_files_added: int = 0
    total_test_files_added: int = 0
    total_test_helpers: int = 0
    total_prod_files_added: int = 0
    matched_pairs: int = 0
    test_first_count: int = 0
    same_commit_count: int = 0
    prod_first_count: int = 0
    unmatched_test_files: int = 0
    unmatched_prod_files: int = 0
    multi_test_prod_files: int = 0  # Prod files with multiple tests

    # Deletion tracking counts
    active_pairs: int = 0  # Both files still exist
    deleted_pairs: int = 0  # At least one file was deleted
    test_deleted_pairs: int = 0  # Only test was deleted
    prod_deleted_pairs: int = 0  # Only prod was deleted
    both_deleted_pairs: int = 0  # Both files were deleted

    pairs: list = field(default_factory=list)
    unmatched_tests_details: list = field(default_factory=list)
    # Commit stats: list of {commit_hash, commit_date, author, total_lines, files_count, java_files_count}
    commit_stats: list = field(default_factory=list)
    error: str = None


# =============================================================================
# Java File Classifier
# =============================================================================


class JavaFileClassifier:
    """Classifies Java files and extracts metadata."""

    def __init__(self):
        self.exclude_patterns = [
            re.compile(p, re.IGNORECASE) for p in JAVA_EXCLUDE_PATTERNS
        ]
        self.helper_patterns = [re.compile(p) for p in TEST_HELPER_PATTERNS]

    def is_java_file(self, filepath: str) -> bool:
        """Check if file is a Java source file."""
        return filepath.endswith(".java")

    def should_exclude(self, filepath: str) -> bool:
        """Check if file should be excluded from analysis."""
        return any(p.match(filepath) for p in self.exclude_patterns)

    def is_test_helper(self, filepath: str) -> bool:
        """
        Check if a file in test directory is a helper/utility rather than an actual test.
        """
        filename = os.path.basename(filepath)
        return any(p.match(filename) for p in self.helper_patterns)

    def is_test_file(self, filepath: str) -> bool:
        """
        Determine if a Java file is a UNIT TEST file.
        """
        filename = os.path.basename(filepath)
        path_lower = filepath.lower()

        # =======================================================================
        # DIRECTORY EXCLUSIONS - Check first before filename patterns
        # =======================================================================

        # 1. Integration test directories - ALWAYS exclude regardless of filename
        integration_dir_patterns = [
            "/src/it/",
            "/src/integration-test/",
            "/src/integrationtest/",
            "/src/integration/",
            "src/it/",
            "/it/src/",
            "/its/",  # Maven integration test suite
            "its/",
            "-it/",  # core-it, maven-it patterns
            "-it-",  # foo-it-bar patterns
            "/it-",  # /it-tests, /it-suite
            "it-suite",  # Explicit it-suite
            "core-it",  # Common Apache pattern
            "integration-tests/",
            "integrationtests/",
        ]
        for dir_pattern in integration_dir_patterns:
            if dir_pattern in path_lower:
                return False

        # 2. Test resources - sample/fixture files, not actual tests
        if "/test/resources/" in path_lower or "/testresources/" in path_lower:
            return False

        # 3. Sample/example directories
        if "/samples/" in path_lower or "/examples/" in path_lower:
            return False

        # =======================================================================
        # FILENAME EXCLUSIONS - for Integration Tests
        # =======================================================================
        integration_test_patterns = [
            r"^.*IT\.java$",  # FooIT.java
            r"^.*ITCase\.java$",  # FooITCase.java
            r"^.*Spec\.java$",  # FooSpec.java
            r"^.*IntegrationTest\.java$",
            r"^.*AcceptanceTest\.java$",
            r"^.*E2ETest\.java$",
            r"^.*EndToEndTest\.java$",
        ]

        for pattern in integration_test_patterns:
            if re.match(pattern, filename):
                return False

        # =======================================================================
        # UNIT TEST CHECK
        # =======================================================================

        # Filename patterns
        unit_test_patterns = [
            r"^.*Test\.java$",  # FooTest.java
            r"^.*Tests\.java$",  # FooTests.java
            r"^Test[A-Z].*\.java$",  # TestFoo.java
        ]

        for pattern in unit_test_patterns:
            if re.match(pattern, filename):
                return True

        # Directory-based (for helpers without Test suffix)
        unit_test_dirs = [
            "/src/test/java/",
            "/test/java/",
            "/tests/java/",
        ]

        for indicator in unit_test_dirs:
            if indicator in path_lower:
                return True

        return False

    def extract_class_name(self, filepath: str) -> str:
        """Extract the class name from a Java file path."""
        filename = os.path.basename(filepath)
        return filename.replace(".java", "")

    def extract_base_class_name(self, test_class: str) -> list[str]:
        """
        Extract possible production class names from a test class name.

        EXCLUDES:
        - Integration test patterns (IT + numbers/lowercase)
        - Project-prefixed integration tests
        - Generic/common class names that cause false matches

        Returns list of candidates in order of likelihood.
        """
        candidates = []
        base = test_class

        # =======================================================================
        # INTEGRATION TEST PATTERN DETECTION
        # These patterns indicate tests named after test IDs, not production classes
        # =======================================================================

        # Pattern 1: Starts with IT followed by numbers or lowercase
        # EG: IT0001Test, ITmng1234Test, etc.
        if re.match(r"^IT[0-9a-z]", test_class):
            return []

        # Pattern 2: Contains IT followed by numbers in the middle
        # EG: MavenIT0001Test, KafkaITmng1234Test, FooITCase0001, etc.
        if re.search(r"IT[0-9]{2,}", test_class):
            return []

        # Pattern 3: Contains ITmng or IТCase followed by numbers
        if re.search(r"IT(mng|Case|case)[0-9]", test_class):
            return []

        # Pattern 4: Ends with IT + numbers (Mng1234IT)
        if re.search(r"[0-9]+IT$", test_class.replace("Test", "").replace("Case", "")):
            return []

        # =======================================================================
        # REMOVE TEST SUFFIXES
        # =======================================================================
        test_suffixes = [
            "Test",
            "Tests",
            "TestCase",
            "IntegrationTest",
            "UnitTest",
            "FunctionalTest",
        ]

        for suffix in test_suffixes:
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break

        # Handle prefix patterns (TestFoo -> Foo)
        if (
            test_class.startswith("Test")
            and len(test_class) > 4
            and test_class[4].isupper()
        ):
            prefix_candidate = test_class[4:]
            # Remove suffix from prefix candidate too
            for suffix in test_suffixes:
                if prefix_candidate.endswith(suffix):
                    prefix_candidate = prefix_candidate[: -len(suffix)]
                    break
            if len(prefix_candidate) >= 4:
                candidates.append(prefix_candidate)

        if not base:
            return candidates if candidates else []

        # MINIMUM LENGTH CHECK
        # (Very short base names are likely false positives)
        if len(base) < 4:
            return [base] if len(base) >= 3 else []

        # GENERATE CANDIDATES FROM NAMES
        # EG: IOUtilsMultithreadedSkip -> [IOUtilsMultithreadedSkip, IOUtils]

        # Find positions of uppercase letters
        upper_positions = [0]
        for i, c in enumerate(base):
            if c.isupper() and i > 0:
                upper_positions.append(i)

        # Generate candidates from progressively shorter prefixes
        # Require minimum 4 chars to avoid generic matches
        for i in range(len(upper_positions) - 1, 0, -1):
            pos = upper_positions[i]
            candidate = base[:pos]
            if candidate and len(candidate) >= 4:
                if candidate not in candidates:
                    candidates.append(candidate)

        # Add the full base (without test suffix) as primary candidate
        if base not in candidates and len(base) >= 4:
            candidates.insert(0, base)

        # FILTER OUT FALSE POSITIVES
        # These are common names that appear in many classes and cause bad matches
        # Generic terms that are too broad
        # Based on final_java_candidates list
        # Defined in the file "generic_terms.py"
        generic_terms = GENERIC_TERMS

        candidates = [c for c in candidates if c not in generic_terms]

        # Skip if base looks like a test ID
        # EG: UpperCase + numbers (Mng1234, Issue5678)
        candidates = [
            c for c in candidates if not re.match(r"^[A-Z][a-z]*[0-9]{3,}$", c)
        ]

        return candidates

    def extract_package_path(self, filepath: str) -> str:
        """
        Extract a normalized package path for matching.

        For a file like: kafka-clients/src/main/java/org/apache/kafka/clients/Producer.java
        Returns: kafka-clients/org/apache/kafka/clients

        Needed to make sure that test-prod pairs are not matched across different modules in
        any particular project.
        EG: Tests in module-X match production in module-X and not a different module.
        """
        # Normalizing file paths
        path = filepath.replace("\\", "/")

        # Normalizing test paths to prod paths
        source_root_patterns = [
            ("src/test/java/", "src/main/java/"),
            ("src/test/scala/", "src/main/scala/"),
            ("src/test/groovy/", "src/main/groovy/"),
            ("src/it/java/", "src/main/java/"),
            ("src/it/scala/", "src/main/scala/"),
            ("src/integrationTest/java/", "src/main/java/"),
            ("src/testFixtures/java/", "src/main/java/"),
            ("src/test-integration/java/", "src/main/java/"),
            ("test/java/", "main/java/"),
            ("test/", "main/"),
        ]

        for test_pattern, main_pattern in source_root_patterns:
            if test_pattern in path:
                path = path.replace(test_pattern, main_pattern)
                break

        # Split path into module prefix and package path
        # EG: kafka-clients/src/main/java/org/apache/kafka/clients/Producer.java
        # module_path = "kafka-clients"
        # package_path = "org/apache/kafka/clients"
        source_roots = [
            "src/main/java/",
            "src/main/scala/",
            "src/main/groovy/",
            "src/java/",
            "main/java/",
            "java/",
        ]

        module_path = ""
        package_path = ""

        for root in source_roots:
            if root in path:
                parts = path.split(root, 1)
                module_path = parts[0].rstrip("/")
                package_path = os.path.dirname(parts[1])
                break
        else:
            package_path = os.path.dirname(path)

        # Combine module and package for final path (ensures that cross module matching does not happen)
        if module_path and package_path:
            return f"{module_path}/{package_path}"
        elif module_path:
            return module_path
        else:
            return package_path

    # NOTE: Old function not currently being used
    # def get_test_class_candidates(self, prod_class: str) -> list[str]:
    #     """Generate possible test class names from a production class name."""
    #     candidates = []
    #     suffixes = ["Test", "Tests", "TestCase"]
    #     for suffix in suffixes:
    #         candidates.append(f"{prod_class}{suffix}")
    #     candidates.append(f"Test{prod_class}")
    #     return candidates


# =============================================================================
# Test-Production Matcher
# =============================================================================


class TestProductionMatcher:
    """Matches test files to their pairing production files."""

    def __init__(self):
        self.classifier = JavaFileClassifier()

    def find_matches(
        self, test_files: dict[str, JavaFileInfo], prod_files: dict[str, JavaFileInfo]
    ) -> tuple[list[TestProductionPair], int, int, int, list]:
        """
        Find matching test-production pairs.

        Uses BEST MATCH strategy: each test matches to ONE best production file.
        Multiple tests CAN match to the same production file.
        """
        pairs = []
        matched_tests = set()
        prod_match_counts = defaultdict(int)
        unmatched_details = []

        # Build production file lookup by ALL class names (current + historical)
        prod_by_class = defaultdict(list)
        for filepath, info in prod_files.items():
            # Add current class name
            prod_by_class[info.class_name].append(info)
            # Add all historical class names
            for historical_name in info.all_class_names:
                if historical_name != info.class_name:
                    prod_by_class[historical_name].append(info)

        # For each test file, find the BEST matching production file
        for test_path, test_info in test_files.items():
            if test_info.is_test_helper:
                continue

            # Get all candidate production class names
            prod_candidates = []

            # From current class name
            for bc in self.classifier.extract_base_class_name(test_info.class_name):
                if bc not in prod_candidates:
                    prod_candidates.append(bc)

            # From historical class names
            for historical_test_name in test_info.all_class_names:
                for bc in self.classifier.extract_base_class_name(historical_test_name):
                    if bc not in prod_candidates:
                        prod_candidates.append(bc)

            # If no candidates (eg: integration test pattern), skip
            if not prod_candidates:
                unmatched_details.append(
                    {
                        "filepath": test_info.filepath,
                        "class_name": test_info.class_name,
                        "all_class_names": test_info.all_class_names,
                        "candidates_tried": [],
                        "reason": "No valid production class candidates (likely integration test)",
                        "original_filepath": test_info.original_filepath,
                        "commit_hash": test_info.commit_hash,
                        "commit_date": (
                            test_info.commit_date.isoformat()
                            if test_info.commit_date
                            else None
                        ),
                        "author": test_info.author,
                        "is_helper": test_info.is_test_helper,
                    }
                )
                continue

            best_match = None
            best_match_method = None

            # Try candidates in order (first candidate is most likely)
            for prod_class in prod_candidates:
                if prod_class not in prod_by_class:
                    continue

                prod_matches = prod_by_class[prod_class]

                # Get all test package paths (current + historical)
                all_test_packages = list(
                    set([test_info.package_path] + test_info.all_package_paths)
                )

                # Priority 1: Same package (exact match)
                for prod_info in prod_matches:
                    all_prod_packages = list(
                        set([prod_info.package_path] + prod_info.all_package_paths)
                    )
                    for tp in all_test_packages:
                        if tp in all_prod_packages:
                            best_match = prod_info
                            best_match_method = "exact_class_same_package"
                            break
                    if best_match:
                        break

                if best_match:
                    break

                # Priority 2: Similar package (same module/subpackage)
                for prod_info in prod_matches:
                    all_prod_packages = list(
                        set([prod_info.package_path] + prod_info.all_package_paths)
                    )
                    for tp in all_test_packages:
                        for pp in all_prod_packages:
                            if self._packages_similar(tp, pp):
                                best_match = prod_info
                                best_match_method = "exact_class_similar_package"
                                break
                        if best_match:
                            break
                    if best_match:
                        break

                if best_match:
                    break

                # Priority 3: Different package (only for first/best candidate)
                # This is less reliable, so only use for the most likely candidate
                if prod_matches and prod_candidates.index(prod_class) == 0:
                    best_match = prod_matches[0]
                    best_match_method = "exact_class_different_package"
                    break

            if best_match:
                pair = self._create_pair(test_info, best_match, best_match_method)
                pairs.append(pair)
                matched_tests.add(test_path)
                prod_match_counts[best_match.filepath] += 1
            else:
                unmatched_details.append(
                    {
                        "filepath": test_info.filepath,
                        "class_name": test_info.class_name,
                        "all_class_names": test_info.all_class_names,
                        "candidates_tried": prod_candidates,
                        "reason": "No matching production file found",
                        "original_filepath": test_info.original_filepath,
                        "commit_hash": test_info.commit_hash,
                        "commit_date": (
                            test_info.commit_date.isoformat()
                            if test_info.commit_date
                            else None
                        ),
                        "author": test_info.author,
                        "is_helper": test_info.is_test_helper,
                    }
                )

        # Count statistics
        unmatched_test_count = len(
            [t for t in test_files.values() if not t.is_test_helper]
        ) - len(matched_tests)
        matched_prods = set(prod_match_counts.keys())
        unmatched_prod_count = len(prod_files) - len(matched_prods)
        multi_test_count = sum(1 for count in prod_match_counts.values() if count > 1)

        return (
            pairs,
            unmatched_test_count,
            unmatched_prod_count,
            multi_test_count,
            unmatched_details,
        )

    def _packages_similar(self, pkg1: str, pkg2: str) -> bool:
        """
        Check if two package paths are similar enough to be a valid match.
        Requires at least 3 matching path segments from the end.
        """
        if not pkg1 or not pkg2:
            return False

        if pkg1 == pkg2:
            return True

        # Normalize test/main paths
        norm1 = pkg1.replace("/test/", "/main/").replace("/tests/", "/main/")
        norm2 = pkg2.replace("/test/", "/main/").replace("/tests/", "/main/")

        if norm1 == norm2:
            return True

        # Split into segments
        pkg1_parts = [p for p in pkg1.split("/") if p]
        pkg2_parts = [p for p in pkg2.split("/") if p]

        # Require at least 3 parts to compare
        if len(pkg1_parts) < 3 or len(pkg2_parts) < 3:
            return False

        # Count matching segments from the end (package structure)
        # EG: org/apache/commons/io vs org/apache/commons/io/input
        min_len = min(len(pkg1_parts), len(pkg2_parts))
        match_count = 0

        for i in range(1, min_len + 1):
            if pkg1_parts[-i] == pkg2_parts[-i]:
                match_count += 1
            else:
                break

        # Require at least 3 matching segments for "similar"
        # Ensures same organization + project + subpackage
        return match_count >= 3

    def _create_pair(
        self, test_info: JavaFileInfo, prod_info: JavaFileInfo, match_method: str
    ) -> TestProductionPair:
        """Create a TestProductionPair with classification and commit size metrics."""

        if test_info.commit_hash == prod_info.commit_hash:
            classification = "SAME_COMMIT"
            time_diff = 0.0
        elif test_info.commit_date < prod_info.commit_date:
            classification = "TEST_FIRST"
            time_diff = (
                prod_info.commit_date - test_info.commit_date
            ).total_seconds() / 3600
        else:
            classification = "PRODUCTION_FIRST"
            time_diff = (
                test_info.commit_date - prod_info.commit_date
            ).total_seconds() / 3600

        time_diff_abs = abs(time_diff)
        # time_category = categorize_time_diff(time_diff_abs, classification)

        # Determine pair status based on deletion state
        # ACTIVE: both files exist
        # TEST_DELETED: only test was deleted
        # PROD_DELETED: only prod was deleted
        # BOTH_DELETED: both files were deleted
        test_deleted = test_info.is_deleted
        prod_deleted = prod_info.is_deleted

        if not test_deleted and not prod_deleted:
            pair_status = "ACTIVE"
        elif test_deleted and not prod_deleted:
            pair_status = "TEST_DELETED"
        elif not test_deleted and prod_deleted:
            pair_status = "PROD_DELETED"
        else:
            pair_status = "BOTH_DELETED"

        return TestProductionPair(
            test_file=test_info.filepath,
            prod_file=prod_info.filepath,
            test_class=test_info.class_name,
            prod_class=prod_info.class_name,
            test_commit=test_info.commit_hash,
            prod_commit=prod_info.commit_hash,
            test_date=test_info.commit_date,
            prod_date=prod_info.commit_date,
            test_author=test_info.author,
            prod_author=prod_info.author,
            classification=classification,
            time_diff_hours=time_diff_abs,
            # time_diff_category=time_category,
            match_method=match_method,
            # Commit size metrics for test
            test_file_lines=test_info.file_lines_added,
            test_commit_total_lines=test_info.commit_total_lines_added,
            test_commit_files=test_info.commit_files_count,
            test_commit_java_files=test_info.commit_java_files_count,
            # Commit size metrics for prod
            prod_file_lines=prod_info.file_lines_added,
            prod_commit_total_lines=prod_info.commit_total_lines_added,
            prod_commit_files=prod_info.commit_files_count,
            prod_commit_java_files=prod_info.commit_java_files_count,
            # Rename tracking
            test_was_renamed=test_info.original_filepath is not None,
            prod_was_renamed=prod_info.original_filepath is not None,
            test_original_file=test_info.original_filepath,
            prod_original_file=prod_info.original_filepath,
            # Deletion tracking
            pair_status=pair_status,
            test_is_deleted=test_deleted,
            prod_is_deleted=prod_deleted,
            test_deletion_date=test_info.deletion_date,
            prod_deletion_date=prod_info.deletion_date,
            test_deletion_commit=test_info.deletion_commit,
            prod_deletion_commit=prod_info.deletion_commit,
        )


# =============================================================================
# Repository Analyzer
# =============================================================================


def analyze_repository(
    repo_path: str,
    repo_name: str = None,
    since: datetime = None,
    to: datetime = None,
    max_commits: int = None,
    verbose: bool = False,
) -> RepositoryAnalysis:
    """Analyze a Java repository for tdd practices."""
    start_time = time.time()

    configure_pydriller_logging(verbose)

    if repo_name is None:
        repo_name = Path(repo_path).name

    analysis = RepositoryAnalysis(
        repo_name=repo_name,
        repo_path=repo_path,
        analysis_date=datetime.now().isoformat(),
    )

    try:
        logger.info(f"Analyzing repository: {repo_name}")

        classifier = JavaFileClassifier()
        matcher = TestProductionMatcher()

        # Collect all events (oldest first)
        file_events = []
        commit_stats = {}  # commit_hash -> {total_lines, files_count, java_files_count}

        # TODO: Remove? used for testing earlier
        repo_kwargs = {"path_to_repo": repo_path}
        if since:
            repo_kwargs["since"] = since
        if to:
            repo_kwargs["to"] = to

        commit_count = 0

        logger.info(f"{repo_name}: Phase 1 - Scanning commits...")

        for commit in Repository(**repo_kwargs).traverse_commits():
            commit_count += 1

            if max_commits and commit_count > max_commits:
                break

            if commit_count % 500 == 0:
                logger.info(f"{repo_name}: Scanned {commit_count} commits...")

            # Calculate commit level stats and collect all events
            total_lines = 0
            files_count = len(commit.modified_files)
            java_files_count = 0

            for mod_file in commit.modified_files:
                total_lines += mod_file.added_lines or 0

                if not mod_file.change_type:
                    continue

                change_type = mod_file.change_type.name
                new_path = mod_file.new_path
                old_path = mod_file.old_path

                # Count Java files
                is_java_new = new_path and classifier.is_java_file(new_path)
                is_java_old = old_path and classifier.is_java_file(old_path)
                if is_java_new or is_java_old:
                    java_files_count += 1

                # Collect events
                if change_type == "RENAME" and old_path and new_path:
                    if is_java_new and not classifier.should_exclude(new_path):
                        file_events.append(
                            {
                                "type": "RENAME",
                                "new_path": new_path,
                                "old_path": old_path,
                                "commit_hash": commit.hash,
                                "commit_date": commit.committer_date,
                                "author": (
                                    commit.author.name if commit.author else "Unknown"
                                ),
                            }
                        )

                elif change_type == "ADD" and new_path:
                    if is_java_new and not classifier.should_exclude(new_path):
                        file_events.append(
                            {
                                "type": "ADD",
                                "filepath": new_path,
                                "commit_hash": commit.hash,
                                "commit_date": commit.committer_date,
                                "author": (
                                    commit.author.name if commit.author else "Unknown"
                                ),
                                "file_lines_added": mod_file.added_lines or 0,
                            }
                        )

                elif change_type == "DELETE" and old_path:
                    if is_java_old:
                        file_events.append(
                            {
                                "type": "DELETE",
                                "filepath": old_path,
                                "commit_hash": commit.hash,
                                "commit_date": commit.committer_date,
                            }
                        )

            commit_stats[commit.hash] = {
                "commit_hash": commit.hash,
                "commit_date": commit.committer_date,
                "author": commit.author.name if commit.author else "Unknown",
                "total_lines": total_lines,
                "files_count": files_count,
                "java_files_count": java_files_count,
            }

        analysis.total_commits = commit_count
        # Store commit stats as list for CSV export
        analysis.commit_stats = list(commit_stats.values())

        logger.info(
            f"{repo_name}: Phase 2 - Building file histories with delete/re-add handling..."
        )

        # =======================================================================
        # Delete / Re-add Checks
        # =======================================================================

        # Collect all adds and deletes per filepath
        file_timeline = defaultdict(list)  # filepath -> [(event_type, event), ...]

        for event in file_events:
            if event["type"] == "ADD":
                file_timeline[event["filepath"]].append(("ADD", event))
            elif event["type"] == "DELETE":
                file_timeline[event["filepath"]].append(("DELETE", event))

        # Build rename chains: new_path -> old_path and old_path -> new_path
        rename_forward = {}  # old_path -> new_path
        rename_backward = {}  # new_path -> old_path

        for event in file_events:
            if event["type"] == "RENAME":
                rename_forward[event["old_path"]] = event["new_path"]
                rename_backward[event["new_path"]] = event["old_path"]

        # Helper functions for rename chain traversal
        def get_original_path(path):
            """Follow rename chain backwards to find original path."""
            visited = set()
            current = path
            while current in rename_backward and current not in visited:
                visited.add(current)
                current = rename_backward[current]
            return current

        def get_final_path(path):
            """Follow rename chain forwards to find final path."""
            visited = set()
            current = path
            while current in rename_forward and current not in visited:
                visited.add(current)
                current = rename_forward[current]
            return current

        def get_all_paths(path):
            """Get all paths a file has ever had."""
            paths = set()

            # Go backward to original
            current = path
            visited = set()
            while current and current not in visited:
                paths.add(current)
                visited.add(current)
                current = rename_backward.get(current)

            # Go forward to final
            current = path
            visited = set()
            while current and current not in visited:
                paths.add(current)
                visited.add(current)
                current = rename_forward.get(current)

            return list(paths)

        def get_effective_addition(filepath):
            """
            Get the effective addition event for a file, accounting for delete+re-add.
            Returns the MOST RECENT addition that comes after any deletion.
            """
            events = file_timeline.get(filepath, [])
            if not events:
                return None

            # Events are in chronological order
            last_delete_idx = -1
            for i, (event_type, _) in enumerate(events):
                if event_type == "DELETE":
                    last_delete_idx = i

            # Find the first ADD after the last DELETE
            for i, (event_type, event) in enumerate(events):
                if event_type == "ADD" and i > last_delete_idx:
                    return event

            # If no ADD after DELETE, return the first ADD (file might have been re-added via rename)
            for event_type, event in events:
                if event_type == "ADD":
                    return event

            return None

        def get_deletion_info(filepath):
            """
            Get deletion information for a file if it was deleted.
            """
            events = file_timeline.get(filepath, [])
            if not events:
                return False, None, None

            # Check if the last event is a DELETE
            last_event_type, last_event = events[-1]
            if last_event_type == "DELETE":
                # Make sure it wasnt renamed
                if filepath not in rename_forward:
                    return (
                        True,
                        last_event.get("commit_date"),
                        last_event.get("commit_hash"),
                    )
            return False, None, None

        # Process all files and build file info
        test_file_additions = {}
        prod_file_additions = {}
        processed_files = set()

        test_helper_count = 0
        deleted_test_count = 0
        deleted_prod_count = 0

        # Get all unique original paths (starting points of rename chains)
        all_starting_paths = set()
        for event in file_events:
            if event["type"] == "ADD":
                original = get_original_path(event["filepath"])
                all_starting_paths.add(original)

        for original_path in all_starting_paths:
            if original_path in processed_files:
                continue
            processed_files.add(original_path)

            final_path = get_final_path(original_path)
            all_paths = get_all_paths(original_path)

            # Check if the file was ultimately deleted
            file_is_deleted, deletion_date, deletion_commit = get_deletion_info(
                final_path
            )

            # Get the effective addition (accounting for delete+re-add)
            add_event = get_effective_addition(original_path)
            if not add_event:
                # Try other paths in the chain
                for p in all_paths:
                    add_event = get_effective_addition(p)
                    if add_event:
                        break

            if not add_event:
                continue

            # Use final path for classification but track all historical names
            is_test = classifier.is_test_file(final_path)
            is_helper = classifier.is_test_helper(final_path) if is_test else False

            if is_helper:
                test_helper_count += 1

            # Extract class names from ALL historical paths
            all_class_names = []
            all_package_paths = []
            for p in all_paths:
                cn = classifier.extract_class_name(p)
                if cn not in all_class_names:
                    all_class_names.append(cn)
                pp = classifier.extract_package_path(p)
                if pp not in all_package_paths:
                    all_package_paths.append(pp)

            current_class = classifier.extract_class_name(final_path)
            base_candidates = (
                classifier.extract_base_class_name(current_class)
                if is_test
                else [current_class]
            )

            # For tests, also get base candidates from historical names
            if is_test:
                for cn in all_class_names:
                    for bc in classifier.extract_base_class_name(cn):
                        if bc not in base_candidates:
                            base_candidates.append(bc)

            # Get commit stats
            commit_hash = add_event["commit_hash"]
            stats = commit_stats.get(commit_hash, {})

            file_info = JavaFileInfo(
                filepath=final_path,
                filename=os.path.basename(final_path),
                class_name=current_class,
                base_class_name=(
                    base_candidates[0] if base_candidates else current_class
                ),
                package_path=classifier.extract_package_path(final_path),
                commit_hash=commit_hash,
                commit_date=add_event["commit_date"],
                author=add_event["author"],
                is_test=is_test,
                is_test_helper=is_helper,
                file_lines_added=add_event.get("file_lines_added", 0),
                commit_total_lines_added=stats.get("total_lines", 0),
                commit_files_count=stats.get("files_count", 0),
                commit_java_files_count=stats.get("java_files_count", 0),
                original_filepath=(
                    original_path if original_path != final_path else None
                ),
                is_deleted=file_is_deleted,
                deletion_date=deletion_date,
                deletion_commit=deletion_commit,
                all_class_names=all_class_names,
                all_package_paths=all_package_paths,
            )

            if is_test:
                test_file_additions[final_path] = file_info
                if file_is_deleted:
                    deleted_test_count += 1
            else:
                prod_file_additions[final_path] = file_info
                if file_is_deleted:
                    deleted_prod_count += 1

        analysis.total_test_files_added = len(test_file_additions)
        analysis.total_test_helpers = test_helper_count
        analysis.total_prod_files_added = len(prod_file_additions)
        analysis.total_java_files_added = len(test_file_additions) + len(
            prod_file_additions
        )

        actual_tests = len(test_file_additions) - test_helper_count
        logger.info(
            f"{repo_name}: Found {actual_tests} test files ({test_helper_count} helpers, {deleted_test_count} deleted), "
            f"{len(prod_file_additions)} production files ({deleted_prod_count} deleted)"
        )

        if test_file_additions and prod_file_additions:
            pairs, unmatched_tests, unmatched_prods, multi_tests, unmatched_details = (
                matcher.find_matches(test_file_additions, prod_file_additions)
            )

            analysis.pairs = [asdict(p) for p in pairs]
            analysis.matched_pairs = len(pairs)
            analysis.unmatched_test_files = unmatched_tests
            analysis.unmatched_prod_files = unmatched_prods
            analysis.multi_test_prod_files = multi_tests
            analysis.unmatched_tests_details = unmatched_details

            # Count classifications and pair status
            for pair in pairs:
                if pair.classification == "TEST_FIRST":
                    analysis.test_first_count += 1
                elif pair.classification == "SAME_COMMIT":
                    analysis.same_commit_count += 1
                else:
                    analysis.prod_first_count += 1

                # Count deletion status
                if pair.pair_status == "ACTIVE":
                    analysis.active_pairs += 1
                else:
                    analysis.deleted_pairs += 1
                    if pair.pair_status == "TEST_DELETED":
                        analysis.test_deleted_pairs += 1
                    elif pair.pair_status == "PROD_DELETED":
                        analysis.prod_deleted_pairs += 1
                    elif pair.pair_status == "BOTH_DELETED":
                        analysis.both_deleted_pairs += 1

            logger.info(
                f"{repo_name}: Matched {len(pairs)} pairs - "
                f"TEST_FIRST: {analysis.test_first_count}, "
                f"SAME_COMMIT: {analysis.same_commit_count}, "
                f"PRODUCTION_FIRST: {analysis.prod_first_count}"
            )
            logger.info(
                f"{repo_name}: Pair status - ACTIVE: {analysis.active_pairs}, "
                f"DELETED: {analysis.deleted_pairs} (test: {analysis.test_deleted_pairs}, "
                f"prod: {analysis.prod_deleted_pairs}, both: {analysis.both_deleted_pairs})"
            )
            logger.info(
                f"{repo_name}: {multi_tests} prod files have multiple tests, "
                f"{unmatched_tests} tests unmatched"
            )

        for pair in analysis.pairs:
            if isinstance(pair.get("test_date"), datetime):
                pair["test_date"] = pair["test_date"].isoformat()
            if isinstance(pair.get("prod_date"), datetime):
                pair["prod_date"] = pair["prod_date"].isoformat()
            # Serialize deletion dates
            if isinstance(pair.get("test_deletion_date"), datetime):
                pair["test_deletion_date"] = pair["test_deletion_date"].isoformat()
            if isinstance(pair.get("prod_deletion_date"), datetime):
                pair["prod_deletion_date"] = pair["prod_deletion_date"].isoformat()

    except Exception as e:
        logger.error(f"Error analyzing {repo_name}: {e}")
        import traceback

        traceback.print_exc()
        analysis.error = str(e)

    analysis.analysis_duration_seconds = time.time() - start_time
    logger.info(
        f"{repo_name}: Analysis completed in {analysis.analysis_duration_seconds:.1f} seconds"
    )

    return analysis


# =============================================================================
# Parallel Processing
# =============================================================================


class ParallelAnalyzer:
    """Manages parallel analysis of multiple repositories."""

    def __init__(self, max_workers: int = None):
        if max_workers is None:
            # Defaults to 80% of CPU cores unless explicitly mentioned
            max_workers = max(1, int(mp.cpu_count() * 0.8))
        self.max_workers = max_workers
        logger.info(f"Initialized parallel analyzer with {max_workers} workers")

    def analyze_repositories(
        self,
        repos: list[dict],
        since: datetime = None,
        to: datetime = None,
        max_commits_per_repo: int = None,
        verbose: bool = False,
    ) -> tuple[list[RepositoryAnalysis], float]:
        results = []
        failed_repos = []
        actual_time_start = time.time()

        logger.info(f"Starting analysis of {len(repos)} repositories...")

        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}

            for repo in repos:
                path = repo["path"]
                name = repo.get("name", Path(path).name)

                logger.info(f"Submitting {name} for analysis...")
                future = executor.submit(
                    analyze_repository,
                    path,
                    name,
                    since,
                    to,
                    max_commits_per_repo,
                    verbose,
                )
                futures[future] = name

            for future in as_completed(futures):
                repo_name = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    if result.error:
                        logger.warning(
                            f"Completed {repo_name} with error: {result.error}"
                        )
                        failed_repos.append((repo_name, result.error))
                    else:
                        logger.info(f"Completed analysis of {repo_name}")
                # Create a placeholder for failed repos so they appear in output
                except Exception as e:
                    logger.error(f"Failed to analyze {repo_name}: {e}")
                    failed_repos.append((repo_name, str(e)))
                    failed_analysis = RepositoryAnalysis(
                        repo_name=repo_name,
                        repo_path="",
                        analysis_date=datetime.now().isoformat(),
                        error=str(e),
                    )
                    results.append(failed_analysis)

        if failed_repos:
            logger.warning(f"\n{len(failed_repos)} repositories had errors:")
            for name, error in failed_repos:
                logger.warning(f"  - {name}: {error[:100]}")

        total_time = time.time() - actual_time_start
        logger.info(
            f"Analysis complete: {len(results) - len(failed_repos)}/{len(repos)} successful "
            f"in {total_time:.1f}s"
        )

        return results, total_time


# =============================================================================
# CSV Report Generator
# =============================================================================


class CSVReportGenerator:
    """Generates CSV reports for analysis results."""

    @staticmethod
    def generate_pairs_csv(analyses: list[RepositoryAnalysis], output_path: str):
        """Generate CSV with all test-production pairs (tdd_pairs.csv)."""
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            writer.writerow(
                [
                    "repository",
                    "classification",
                    # "time_diff_category",
                    "test_file",
                    "prod_file",
                    "test_class",
                    "prod_class",
                    "test_commit",
                    "prod_commit",
                    "test_date",
                    "prod_date",
                    "test_author",
                    "prod_author",
                    "time_diff_hours",
                    "time_diff_days",
                    # "match_method",
                    # Commit size metrics for test
                    "test_file_lines",
                    "test_commit_total_lines",
                    "test_commit_files",
                    "test_commit_java_files",
                    # Commit size metrics for prod
                    "prod_file_lines",
                    "prod_commit_total_lines",
                    "prod_commit_files",
                    "prod_commit_java_files",
                    # Rename tracking - present in JSON if needed or uncomment
                    # "test_was_renamed",
                    # "prod_was_renamed",
                    # "test_original_file",
                    # "prod_original_file",
                    # Deletion tracking
                    "pair_status",
                    # Deletion info - present in JSON if needed or uncomment
                    # "test_is_deleted",
                    # "prod_is_deleted",
                    # "test_deletion_date",
                    # "prod_deletion_date",
                    # "test_deletion_commit",
                    # "prod_deletion_commit",
                ]
            )

            for analysis in analyses:
                if analysis.error:
                    continue

                for pair in analysis.pairs:
                    time_diff_hours = pair["time_diff_hours"]
                    time_diff_days = time_diff_hours / 24.0

                    writer.writerow(
                        [
                            analysis.repo_name,
                            pair["classification"],
                            # pair.get("time_diff_category", "UNKNOWN"),
                            pair["test_file"],
                            pair["prod_file"],
                            pair["test_class"],
                            pair["prod_class"],
                            pair["test_commit"][:8],
                            pair["prod_commit"][:8],
                            pair["test_date"],
                            pair["prod_date"],
                            pair["test_author"],
                            pair["prod_author"],
                            f"{time_diff_hours:.2f}",
                            f"{time_diff_days:.1f}",
                            # pair["match_method"],
                            # Commit size metrics for test
                            pair.get("test_file_lines", 0),
                            pair.get("test_commit_total_lines", 0),
                            pair.get("test_commit_files", 0),
                            pair.get("test_commit_java_files", 0),
                            # Commit size metrics for prod
                            pair.get("prod_file_lines", 0),
                            pair.get("prod_commit_total_lines", 0),
                            pair.get("prod_commit_files", 0),
                            pair.get("prod_commit_java_files", 0),
                            # Rename tracking
                            # pair.get("test_was_renamed", False),
                            # pair.get("prod_was_renamed", False),
                            # pair.get("test_original_file", ""),
                            # pair.get("prod_original_file", ""),
                            # Deletion tracking
                            pair.get("pair_status", "ACTIVE"),
                            # Deletion info
                            # pair.get("test_is_deleted", False),
                            # pair.get("prod_is_deleted", False),
                            # pair.get("test_deletion_date", ""),
                            # pair.get("prod_deletion_date", ""),
                            # pair.get("test_deletion_commit", "")[:8] if pair.get("test_deletion_commit") else "",
                            # pair.get("prod_deletion_commit", "")[:8] if pair.get("prod_deletion_commit") else "",
                        ]
                    )

        logger.info(f"Pairs CSV saved to {output_path}")

    @staticmethod
    def generate_summary_csv(analyses: list[RepositoryAnalysis], output_path: str):
        """Generate summary CSV with per-repository statistics (tdd_summary.csv)."""
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            writer.writerow(
                [
                    "repository",
                    "analysis_duration_seconds",
                    "total_commits",
                    "test_files_added",
                    "test_helpers",
                    "prod_files_added",
                    "matched_pairs",
                    "multi_test_prods",
                    "test_first_count",
                    "same_commit_count",
                    "prod_first_count",
                    "test_first_%",
                    "same_commit_%",
                    "prod_first_%",
                    "unmatched_test_files",
                    "unmatched_prod_files",
                    "match_rate_%",
                    # Deletion tracking
                    # "active_pairs",
                    # "deleted_pairs",
                    # "test_deleted_pairs",
                    # "prod_deleted_pairs",
                    # "both_deleted_pairs",
                ]
            )

            for analysis in analyses:
                if analysis.error:
                    writer.writerow([analysis.repo_name, "ERROR", analysis.error])
                    continue

                total_pairs = analysis.matched_pairs
                # pct = percentage
                test_first_pct = (
                    (analysis.test_first_count / total_pairs * 100)
                    if total_pairs > 0
                    else 0
                )
                same_commit_pct = (
                    (analysis.same_commit_count / total_pairs * 100)
                    if total_pairs > 0
                    else 0
                )
                prod_first_pct = (
                    (analysis.prod_first_count / total_pairs * 100)
                    if total_pairs > 0
                    else 0
                )

                actual_tests = (
                    analysis.total_test_files_added - analysis.total_test_helpers
                )
                match_rate = (
                    (analysis.matched_pairs / actual_tests * 100)
                    if actual_tests > 0
                    else 0
                )

                writer.writerow(
                    [
                        analysis.repo_name,
                        f"{analysis.analysis_duration_seconds:.1f}",
                        analysis.total_commits,
                        analysis.total_test_files_added,
                        analysis.total_test_helpers,
                        analysis.total_prod_files_added,
                        analysis.matched_pairs,
                        analysis.multi_test_prod_files,
                        analysis.test_first_count,
                        analysis.same_commit_count,
                        analysis.prod_first_count,
                        f"{test_first_pct:.1f}",
                        f"{same_commit_pct:.1f}",
                        f"{prod_first_pct:.1f}",
                        analysis.unmatched_test_files,
                        analysis.unmatched_prod_files,
                        f"{match_rate:.1f}",
                        # Deletion tracking
                        # analysis.active_pairs,
                        # analysis.deleted_pairs,
                        # analysis.test_deleted_pairs,
                        # analysis.prod_deleted_pairs,
                        # analysis.both_deleted_pairs,
                    ]
                )

        logger.info(f"Summary CSV saved to {output_path}")

    @staticmethod
    def generate_unmatched_csv(analyses: list[RepositoryAnalysis], output_path: str):
        """Generate CSV with unmatched test files (debugging) (tdd_unmatched.csv)."""
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            writer.writerow(
                [
                    "repository",
                    "test_file",
                    "test_class",
                    "candidates_tried",
                    "original_filepath",
                    "commit_hash",
                    "commit_date",
                    "author",
                    "is_helper",
                ]
            )

            # TODO: Add deletion info
            for analysis in analyses:
                if analysis.error:
                    continue

                for detail in analysis.unmatched_tests_details:
                    writer.writerow(
                        [
                            analysis.repo_name,
                            detail["filepath"],
                            detail["class_name"],
                            "|".join(detail.get("candidates_tried", [])),
                            detail.get("original_filepath", ""),
                            (
                                detail.get("commit_hash", "")[:8]
                                if detail.get("commit_hash")
                                else ""
                            ),
                            detail.get("commit_date", ""),
                            detail.get("author", ""),
                            detail.get("is_helper", False),
                        ]
                    )

        logger.info(f"Unmatched tests CSV saved to {output_path}")

    @staticmethod
    def generate_commits_csv(analyses: list[RepositoryAnalysis], output_path: str):
        """Generate CSV with commit size metrics for each commit (tdd_commits.csv)."""
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            writer.writerow(
                [
                    "repository",
                    "commit_hash",
                    "commit_date",
                    "author",
                    "total_lines_added",
                    "total_files_count",
                    "java_files_count",
                ]
            )

            for analysis in analyses:
                if analysis.error:
                    continue

                for commit in analysis.commit_stats:
                    # Handle datetime serialization
                    commit_date = commit.get("commit_date", "")
                    if isinstance(commit_date, datetime):
                        commit_date = commit_date.isoformat()

                    writer.writerow(
                        [
                            analysis.repo_name,
                            (
                                commit.get("commit_hash", "")[:8]
                                if commit.get("commit_hash")
                                else ""
                            ),
                            commit_date,
                            commit.get("author", ""),
                            commit.get("total_lines", 0),
                            commit.get("files_count", 0),
                            commit.get("java_files_count", 0),
                        ]
                    )

        logger.info(f"Commits CSV saved to {output_path}")

    # TODO: Add another CSV with average stats (+ more) based on commits file


# =============================================================================
# JSON Report Generator
# =============================================================================


class JSONReportGenerator:
    """Generates JSON reports."""

    @staticmethod
    def generate_report(
        analyses: list[RepositoryAnalysis],
        output_path: str,
        total_time: float = None,
    ):

        valid_analyses = [a for a in analyses if a.error is None]

        # Total cpu time (sum of all individual times)
        total_cpu_time = sum(a.analysis_duration_seconds for a in analyses)

        report = {
            "analysis_date": datetime.now().isoformat(),
            "total_repositories": len(analyses),
            "successfully_analyzed": len(valid_analyses),
            "total_time_seconds": total_time,
            "total_cpu_time": total_cpu_time,
            "aggregate_statistics": {},
            "repository_analyses": [],
        }

        if valid_analyses:
            total_pairs = sum(a.matched_pairs for a in valid_analyses)
            total_test_first = sum(a.test_first_count for a in valid_analyses)
            total_same_commit = sum(a.same_commit_count for a in valid_analyses)
            total_prod_first = sum(a.prod_first_count for a in valid_analyses)

            report["aggregate_statistics"] = {
                "total_commits_analyzed": sum(a.total_commits for a in valid_analyses),
                "total_test_files_added": sum(
                    a.total_test_files_added for a in valid_analyses
                ),
                "total_test_helpers": sum(a.total_test_helpers for a in valid_analyses),
                "total_prod_files_added": sum(
                    a.total_prod_files_added for a in valid_analyses
                ),
                "total_matched_pairs": total_pairs,
                "total_multi_test_prods": sum(
                    a.multi_test_prod_files for a in valid_analyses
                ),
                "total_test_first": total_test_first,
                "total_same_commit": total_same_commit,
                "total_production_first": total_prod_first,
                "test_first_percentage": (
                    (total_test_first / total_pairs * 100) if total_pairs > 0 else 0
                ),
                "same_commit_percentage": (
                    (total_same_commit / total_pairs * 100) if total_pairs > 0 else 0
                ),
                "production_first_percentage": (
                    (total_prod_first / total_pairs * 100) if total_pairs > 0 else 0
                ),
            }

        # NOTE: Change value for debugging if needed
        # Removes the complete list of unmatched test files from the JSON
        for analysis in analyses:
            analysis_dict = asdict(analysis)
            # Remove large lists from JSON
            if len(analysis_dict.get("unmatched_tests_details", [])) > 100:
                analysis_dict["unmatched_tests_details"] = analysis_dict[
                    "unmatched_tests_details"
                ][:100]
                analysis_dict["unmatched_tests_truncated"] = True
            # Removes commit_stats CSV information from JSON for the time being
            analysis_dict.pop("commit_stats", None)

            report["repository_analyses"].append(analysis_dict)

        with open(output_path, "w") as f:
            # json.dump(report, f, indent=2, default=str)
            # No pre-formatting using whitepsaces
            json.dump(report, f, separators=(",", ":"), default=str)

        logger.info(f"JSON report saved to {output_path}")


# =============================================================================
# Console Reporter
# =============================================================================


def print_console_summary(analyses: list[RepositoryAnalysis], total_time: float = None):
    """Print a formatted summary to console."""

    print("\n" + "=" * 100)
    print("JAVA TEST-DRIVEN DEVELOPMENT ANALYSIS REPORT")
    print("=" * 100)

    valid = [a for a in analyses if a.error is None]

    # total_duration = sum(a.analysis_duration_seconds for a in analyses)
    print(f"\nRepositories Analyzed: {len(valid)}/{len(analyses)}")
    print(
        f"Total Analysis Time: {total_time:.1f} seconds ({total_time/60:.1f} minutes)"
    )

    if not valid:
        print("No successful analyses.")
        return

    print("\n--- ANALYSIS TIMING ---")
    for analysis in sorted(
        valid, key=lambda a: a.analysis_duration_seconds, reverse=True
    ):
        print(
            f"  {analysis.repo_name}: {analysis.analysis_duration_seconds:.1f}s ({analysis.total_commits:,} commits)"
        )

    total_pairs = sum(a.matched_pairs for a in valid)
    total_test_first = sum(a.test_first_count for a in valid)
    total_same_commit = sum(a.same_commit_count for a in valid)
    total_prod_first = sum(a.prod_first_count for a in valid)
    total_helpers = sum(a.total_test_helpers for a in valid)
    total_multi = sum(a.multi_test_prod_files for a in valid)

    print("\n--- AGGREGATE STATISTICS ---")
    print(f"Total Commits Analyzed: {sum(a.total_commits for a in valid):,}")
    print(
        f"Total Test Files Added: {sum(a.total_test_files_added for a in valid):,} ({total_helpers} helpers excluded)"
    )
    print(
        f"Total Production Files Added: {sum(a.total_prod_files_added for a in valid):,}"
    )
    print(f"Total Matched Pairs: {total_pairs:,}")
    print(f"Production Files with Multiple Tests: {total_multi:,}")

    print("\n--- CLASSIFICATION BREAKDOWN ---")
    if total_pairs > 0:
        print(
            f"TEST_FIRST (test before production):     {total_test_first:5} ({total_test_first/total_pairs*100:5.1f}%)"
        )
        print(
            f"SAME_COMMIT (test and prod together):    {total_same_commit:5} ({total_same_commit/total_pairs*100:5.1f}%)"
        )
        print(
            f"PRODUCTION_FIRST (prod before test):     {total_prod_first:5} ({total_prod_first/total_pairs*100:5.1f}%)"
        )

    print("\n--- PER-REPOSITORY BREAKDOWN ---")
    print(
        f"{'Repository':<20} {'Time(s)':>8} {'Commits':>8} {'Pairs':>7} {'Multi':>6} {'Test1st':>8} {'Same':>8} {'Prod1st':>8} {'T1st%':>7}"
    )
    print("-" * 105)

    for analysis in sorted(valid, key=lambda a: a.matched_pairs, reverse=True):
        if analysis.matched_pairs > 0:
            test_first_pct = analysis.test_first_count / analysis.matched_pairs * 100
        else:
            test_first_pct = 0

        print(
            f"{analysis.repo_name:<20} {analysis.analysis_duration_seconds:>8.1f} {analysis.total_commits:>8} "
            f"{analysis.matched_pairs:>7} {analysis.multi_test_prod_files:>6} "
            f"{analysis.test_first_count:>8} {analysis.same_commit_count:>8} "
            f"{analysis.prod_first_count:>8} {test_first_pct:>6.1f}%"
        )

    print("\n" + "=" * 100)


# =============================================================================
# Repository Discovery
# =============================================================================


def discover_repositories(
    base_path: str, include_repos: list[str] = None
) -> list[dict]:
    """Discover the Git repositories in mentioned directory"""
    repos = []
    base = Path(base_path)

    if not base.exists():
        logger.warning(f"Directory not found: {base_path}")
        return repos

    # Incase the directory of a specific repo is mentioned
    if (base / ".git").exists():
        if include_repos is None or base.name in include_repos:
            repos.append({"path": str(base), "name": base.name})
        return repos

    all_items = list(base.iterdir())
    logger.info(f"Found {len(all_items)} items in {base_path}")

    for item in all_items:
        if item.is_dir():
            git_path = item / ".git"
            if git_path.exists():
                # Check if this repo should be included
                if include_repos is None or item.name in include_repos:
                    repos.append({"path": str(item), "name": item.name})
                    logger.info(f"  Found repository: {item.name}")
                else:
                    logger.info(f"  Skipping {item.name} (not in include list)")
            else:
                logger.debug(f"  Skipping {item.name} (no .git directory)")
        else:
            logger.debug(f"  Skipping {item.name} (not a directory)")

    logger.info(f"Discovered {len(repos)} repositories in {base_path}")
    return repos


# =============================================================================
# Main Entry Point
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Java repositories for Test-Driven Development practices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Output Files:
            - tdd_pairs.csv:      All matched test-production pairs with classifications
            - tdd_summary.csv:    Per-repository statistics
            - tdd_unmatched.csv:  Unmatched test files for debugging (use --no-unmatched to skip)
            - tdd_commits.csv:    Commit size metrics for each commit
            - tdd_report.json:    Complete analysis data in JSON format

            Classifications:
            - TEST_FIRST:       Test file was committed BEFORE production file
            - SAME_COMMIT:      Test and production files in the SAME commit
            - PRODUCTION_FIRST: Production file was committed BEFORE test file
        """,
    )

    parser.add_argument("repos_dir", help="Directory containing cloned repositories")

    parser.add_argument(
        "-o",
        default="tdd",
        dest="output_prefix",
        help="Output file prefix (default: tdd)",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers (default: 80%% of CPU cores)",
    )

    parser.add_argument(
        "--no-unmatched",
        action="store_true",
        help="Skip generating the unmatched test files CSV",
    )

    parser.add_argument(
        "-v", action="store_true", dest="verbose", help="Enable verbose/debug logging"
    )

    # Following args mainly for testing/debugging purposes
    parser.add_argument(
        "--include-repos",
        nargs="+",
        default=None,
        help="Only analyze these specific repositories",
    )

    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Analyze commits since date (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--to", type=str, default=None, help="Analyze commits until date (YYYY-MM-DD)"
    )

    parser.add_argument(
        "--max-commits",
        type=int,
        default=None,
        help="Maximum commits to analyze per repository",
    )

    args = parser.parse_args()

    configure_pydriller_logging(args.verbose)

    since = datetime.strptime(args.since, "%Y-%m-%d") if args.since else None
    to = datetime.strptime(args.to, "%Y-%m-%d") if args.to else None

    repos = discover_repositories(args.repos_dir, args.include_repos)

    if not repos:
        logger.error(f"No repositories found in {args.repos_dir}")
        if args.include_repos:
            print(f"\nNo matching repositories found for: {args.include_repos}")
        print("Make sure the directory contains subdirectories with .git folders.")
        return 1

    print(f"\nFound {len(repos)} repositories to analyze:")
    for i, repo in enumerate(repos, 1):
        print(f"  {i}. {repo['name']} ({repo['path']})")

    analyzer = ParallelAnalyzer(max_workers=args.workers)
    analyses, total_time = analyzer.analyze_repositories(
        repos,
        since=since,
        to=to,
        max_commits_per_repo=args.max_commits,
        verbose=args.verbose,
    )

    pairs_csv = f"{args.output_prefix}_pairs.csv"
    summary_csv = f"{args.output_prefix}_summary.csv"
    unmatched_csv = f"{args.output_prefix}_unmatched.csv"
    commits_csv = f"{args.output_prefix}_commits.csv"
    json_report = f"{args.output_prefix}_report.json"

    CSVReportGenerator.generate_pairs_csv(analyses, pairs_csv)
    CSVReportGenerator.generate_summary_csv(analyses, summary_csv)
    if not args.no_unmatched:
        CSVReportGenerator.generate_unmatched_csv(analyses, unmatched_csv)
    CSVReportGenerator.generate_commits_csv(analyses, commits_csv)
    JSONReportGenerator.generate_report(analyses, json_report, total_time)

    print_console_summary(analyses, total_time)

    print("\nOutput files:")
    print(f"  - {pairs_csv}:      All test-production pairs")
    print(f"  - {summary_csv}:    Repository summaries")
    if not args.no_unmatched:
        print(f"  - {unmatched_csv}:  Unmatched test files")
    print(f"  - {commits_csv}:    Commit size metrics")
    print(f"  - {json_report}:    Complete JSON report")

    return 0


if __name__ == "__main__":
    exit(main())
