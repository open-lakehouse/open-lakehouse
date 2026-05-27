"""Local validation tests for the realtime-mode RTM pipeline.

These do not start a streaming query and do not need Kafka. They check the
sensitive-data regexes and the DataFrame transformation logic against
deterministic blocks, so the demo author can confirm the routing decisions
are correct before submitting the streaming job.

Run:

    poetry run python demos/realtime-mode/test_pipeline.py

Exit code 0 = all assertions hold.
"""

from __future__ import annotations

import re
import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as f
from pyspark.sql.types import LongType, StringType, StructField, StructType

# Patterns must mirror rtm_pipeline.detect_sensitive_data() exactly.
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_RE = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
PRIVATE_KEY_RE = re.compile(r"0x[a-fA-F0-9]{64}")


TEST_AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
TEST_JWT = ".".join(
    [
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
        "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    ]
)


def classify(text: str) -> str | None:
    if text is None:
        return None
    if AWS_KEY_RE.search(text):
        return "CREDENTIAL_AWS_KEY"
    if JWT_RE.search(text):
        return "CREDENTIAL_JWT"
    if PRIVATE_KEY_RE.search(text):
        return "CREDENTIAL_PRIVATE_KEY"
    if SSN_RE.search(text):
        return "PII_SSN"
    if CREDIT_CARD_RE.search(text):
        return "PII_CREDIT_CARD"
    if EMAIL_RE.search(text):
        return "PII_EMAIL"
    return None


PATTERN_CASES = [
    (None, None, "None input"),
    ("Hello world", None, "Clean text"),
    ("Contact: user@example.com", "PII_EMAIL", "Email"),
    ("USER@DOMAIN.ORG", "PII_EMAIL", "Uppercase email"),
    ("My SSN is 123-45-6789", "PII_SSN", "SSN"),
    ("Card: 4111-1111-1111-1111", "PII_CREDIT_CARD", "CC dashes"),
    ("Card: 4111 1111 1111 1111", "PII_CREDIT_CARD", "CC spaces"),
    ("Card: 4111111111111111", "PII_CREDIT_CARD", "CC no separators"),
    (TEST_AWS_KEY, "CREDENTIAL_AWS_KEY", "AWS key"),
    (TEST_JWT, "CREDENTIAL_JWT", "JWT"),
    (
        "Private key: 0x" + "1234567890abcdef" * 4,
        "CREDENTIAL_PRIVATE_KEY",
        "Eth private key",
    ),
]


def run_pattern_tests() -> int:
    failed = 0
    for text, expected, label in PATTERN_CASES:
        actual = classify(text)
        status = "ok" if actual == expected else "FAIL"
        if actual != expected:
            failed += 1
            print(f"  {status} {label}: expected={expected} actual={actual}")
        else:
            print(f"  {status} {label}")
    return failed


SCHEMA = StructType(
    [
        StructField("block_number", LongType()),
        StructField("block_hash", StringType()),
        StructField("parent_hash", StringType()),
        StructField("miner", StringType()),
        StructField("gas_used", LongType()),
        StructField("gas_limit", LongType()),
        StructField("transaction_count", LongType()),
        StructField("timestamp", LongType()),
        StructField("total_value_wei", StringType()),
        StructField("extra_data", StringType()),
    ]
)


TEST_BLOCKS = [
    (
        1_000_001,
        "0xabc001",
        "0xparent001",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB01",
        8_000_000,
        15_000_000,
        150,
        1710327045,
        "1000000000000000000",
        "Normal block data",
    ),
    (
        1_000_002,
        "0xabc002",
        "0xparent002",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB02",
        14_550_000,
        15_000_000,
        180,
        1710327046,
        "2000000000000000000",
        "High gas block",
    ),
    (
        1_000_003,
        "0xabc003",
        "0xparent003",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB03",
        0,
        15_000_000,
        0,
        1710327047,
        "0",
        "Empty",
    ),
    (
        1_000_004,
        "0xabc004",
        "0xparent004",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB04",
        5_000_000,
        15_000_000,
        100,
        1710327048,
        "500000000000000000",
        "Contact: user@example.com for support",
    ),
    (
        1_000_005,
        "0xabc005",
        "0xparent005",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB05",
        7_500_000,
        15_000_000,
        200,
        1710327049,
        "3000000000000000000",
        "Another normal block",
    ),
    (
        1_000_006,
        "0xabc006",
        "0xparent006",
        "0x0000000000000000000000000000000000000000",
        6_000_000,
        15_000_000,
        120,
        1710327050,
        "800000000000000000",
        "Block with zero miner",
    ),
    (
        1_000_007,
        "0xabc007",
        "0xparent007",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB07",
        12_000_000,
        15_000_000,
        600,
        1710327051,
        "5000000000000000000",
        "High transaction count block",
    ),
    (
        1_000_008,
        "0xabc008",
        "0xparent008",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB08",
        4_000_000,
        15_000_000,
        80,
        1710327052,
        "200000000000000000",
        "SSN leaked: 123-45-6789",
    ),
    (
        1_000_009,
        "0xabc009",
        "0xparent009",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB09",
        3_500_000,
        15_000_000,
        90,
        1710327053,
        "150000000000000000",
        "Card: 4111-1111-1111-1111",
    ),
    (
        1_000_010,
        "0xabc010",
        "0xparent010",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB10",
        5_500_000,
        15_000_000,
        110,
        1710327054,
        "400000000000000000",
        f"Key: {TEST_AWS_KEY}",
    ),
    (
        1_000_011,
        "0xabc011",
        "0xparent011",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB11",
        14_800_000,
        15_000_000,
        300,
        1710327055,
        "6000000000000000000",
        "Alert admin@company.org immediately",
    ),
    (
        1_000_012,
        "0xabc012",
        "0xparent012",
        "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB12",
        4_500_000,
        15_000_000,
        95,
        1710327056,
        "250000000000000000",
        f"Token: {TEST_JWT}",
    ),
]


EXPECTED = {
    1_000_001: ("ALLOW", []),
    1_000_002: ("QUARANTINE", ["HIGH_GAS_USAGE"]),
    1_000_003: ("QUARANTINE", ["EMPTY_BLOCK"]),
    1_000_004: ("QUARANTINE", ["PII_EMAIL"]),
    1_000_005: ("ALLOW", []),
    1_000_006: ("QUARANTINE", ["ZERO_MINER"]),
    1_000_007: ("QUARANTINE", ["HIGH_TX_COUNT"]),
    1_000_008: ("QUARANTINE", ["PII_SSN"]),
    1_000_009: ("QUARANTINE", ["PII_CREDIT_CARD"]),
    1_000_010: ("QUARANTINE", ["CREDENTIAL_AWS_KEY"]),
    1_000_011: ("QUARANTINE", ["HIGH_GAS_USAGE", "PII_EMAIL"]),
    1_000_012: ("QUARANTINE", ["CREDENTIAL_JWT"]),
}


def detect_sensitive_col(name: str):
    return (
        f.when(f.col(name).rlike(r"AKIA[0-9A-Z]{16}"), f.lit("CREDENTIAL_AWS_KEY"))
        .when(
            f.col(name).rlike(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
            f.lit("CREDENTIAL_JWT"),
        )
        .when(f.col(name).rlike(r"0x[a-fA-F0-9]{64}"), f.lit("CREDENTIAL_PRIVATE_KEY"))
        .when(f.col(name).rlike(r"\b\d{3}-\d{2}-\d{4}\b"), f.lit("PII_SSN"))
        .when(f.col(name).rlike(r"\b(\d{4}[-\s]?){3}\d{4}\b"), f.lit("PII_CREDIT_CARD"))
        .when(
            f.col(name).rlike(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"),
            f.lit("PII_EMAIL"),
        )
        .otherwise(None)
    )


def run_transform_tests(spark: SparkSession) -> int:
    df = spark.createDataFrame(TEST_BLOCKS, SCHEMA)

    rules = [
        ("gas_used > gas_limit * 0.95", "HIGH_GAS_USAGE"),
        ("transaction_count > 500", "HIGH_TX_COUNT"),
        ("transaction_count = 0", "EMPTY_BLOCK"),
        (
            "miner = '0x0000000000000000000000000000000000000000'",
            "ZERO_MINER",
        ),
    ]

    reason_cols: list[str] = []
    out = df
    for cond, reason in rules:
        flag = f"_flag_{reason.lower()}"
        out = out.withColumn(
            flag, f.when(f.expr(cond), f.lit(reason)).otherwise(f.lit(None))
        )
        reason_cols.append(flag)

    out = out.withColumn("_sensitive_extra_data", detect_sensitive_col("extra_data"))
    reason_cols.append("_sensitive_extra_data")

    out = out.withColumn(
        "validation_reasons",
        f.expr(f"filter(array({','.join(reason_cols)}), x -> x is not null)"),
    ).withColumn(
        "decision",
        f.when(f.size(f.col("validation_reasons")) > 0, f.lit("QUARANTINE")).otherwise(
            f.lit("ALLOW")
        ),
    )

    rows = out.select("block_number", "decision", "validation_reasons").collect()
    failed = 0
    for row in rows:
        expected_decision, expected_reasons = EXPECTED[row.block_number]
        actual_reasons = sorted(list(row.validation_reasons or []))
        ok = row.decision == expected_decision and actual_reasons == sorted(
            expected_reasons
        )
        status = "ok" if ok else "FAIL"
        if not ok:
            failed += 1
            print(
                f"  {status} block={row.block_number} "
                f"expected={expected_decision}/{expected_reasons} "
                f"actual={row.decision}/{actual_reasons}"
            )
        else:
            print(
                f"  {status} block={row.block_number} "
                f"{row.decision} {actual_reasons}"
            )
    return failed


def main() -> int:
    print("pattern tests")
    pattern_failed = run_pattern_tests()

    print("\ntransform tests")
    spark = (
        SparkSession.builder.appName("rtm-realtime-mode-tests")
        .master("local[*]")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    transform_failed = run_transform_tests(spark)
    spark.stop()

    total = pattern_failed + transform_failed
    print(
        f"\n{pattern_failed} pattern failure(s), {transform_failed} transform failure(s)"
    )
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
