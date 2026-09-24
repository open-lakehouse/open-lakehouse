#!/bin/bash

# Download required JARs for open-lakehouse (Spark 4.1, Iceberg 1.10, Delta 4.3)
#
# Integrity model (docs/testing.md — supply chain): each jar is verified by
# sha256 against a committed lockfile (scripts/tools/jars.sha256), not just by
# size. A size check cannot catch a re-published or tampered artifact of similar
# size; a sha256 can. A checksum MISMATCH is always fatal (the file is deleted).
#
# Flags:
#   --verify-only        verify already-downloaded jars (size + sha256), no fetch
#   --lock               (re)download everything, then WRITE jars.sha256 from the
#                        actual bytes. Run on a networked machine to generate or
#                        refresh the lock after a version bump; commit the result.
#   --strict-checksums   a jar with no lock entry is a FAILURE (default: warn), so
#                        CI can require the lock to cover every pinned jar.

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARS_DIR="${SCRIPT_DIR}/../../jars"
mkdir -p "${JARS_DIR}"
JARS_DIR="$(cd "${JARS_DIR}" && pwd)"
LOCK_FILE="${SCRIPT_DIR}/jars.sha256"

VERIFY_ONLY=false
LOCK_MODE=false
STRICT_CHECKSUMS=false
MAX_RETRIES=3
RETRY_DELAY=5

# Maven repository base. Defaults to public Maven Central so vanilla runs work
# unchanged; override for an internal mirror without editing this file:
#   MAVEN_BASE_URL=<mirror>/maven2 ./scripts/tools/download-jars.sh
MAVEN_BASE_URL="${MAVEN_BASE_URL:-https://repo1.maven.org/maven2}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Parse arguments
for arg in "$@"; do
    case $arg in
        --verify-only) VERIFY_ONLY=true ;;
        --lock) LOCK_MODE=true ;;
        --strict-checksums) STRICT_CHECKSUMS=true ;;
    esac
done

# JAR definitions (simpler format for compatibility)
# Format: "filename|url|min_size_bytes"
JAR_LIST=(
    "iceberg-spark-runtime-4.0_2.13-1.10.0.jar|${MAVEN_BASE_URL}/org/apache/iceberg/iceberg-spark-runtime-4.0_2.13/1.10.0/iceberg-spark-runtime-4.0_2.13-1.10.0.jar|40000000"
    "hadoop-aws-3.4.1.jar|${MAVEN_BASE_URL}/org/apache/hadoop/hadoop-aws/3.4.1/hadoop-aws-3.4.1.jar|800000"
    "aws-java-sdk-bundle-1.12.780.jar|${MAVEN_BASE_URL}/com/amazonaws/aws-java-sdk-bundle/1.12.780/aws-java-sdk-bundle-1.12.780.jar|350000000"
    "bundle-2.24.6.jar|${MAVEN_BASE_URL}/software/amazon/awssdk/bundle/2.24.6/bundle-2.24.6.jar|400000000"
    "postgresql-42.7.4.jar|${MAVEN_BASE_URL}/org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar|1000000"
    # Delta 4.3.1 — ABI-verified on Spark 4.1/Java21 (I-02) and required for
    # catalog-managed Delta via the UC 0.5.x connector family below. NOTE:
    # 4.3.0 NPEs through the UC Spark connector (AbstractDeltaCatalogClient reads a
    # null catalog-options map); 4.3.1 fixes it. 4.0.x breaks with NoSuchMethodError
    # on org.apache.spark.internal.LogKey — do not downgrade.
    "delta-spark_2.13-4.3.1.jar|${MAVEN_BASE_URL}/io/delta/delta-spark_2.13/4.3.1/delta-spark_2.13-4.3.1.jar|8000000"
    "delta-storage-4.3.1.jar|${MAVEN_BASE_URL}/io/delta/delta-storage/4.3.1/delta-storage-4.3.1.jar|70000"
    # Unity Catalog OSS Spark connector family (0.5.x). The connector lets Spark
    # write Delta tables that register in UC (catalogs `unity` / `managed_demo`);
    # the client jar is its runtime dep, and the hadoop jar provides the
    # credential-vending Hadoop configs (UCCredentialHadoopConfs). connector tops
    # out at 0.4.1 (no 0.5.x published) but pairs with the 0.5.1 client + hadoop —
    # this exact set is what makes catalog-managed Delta work (PR #13 / I-45).
    "unitycatalog-spark_2.13-0.4.1.jar|${MAVEN_BASE_URL}/io/unitycatalog/unitycatalog-spark_2.13/0.4.1/unitycatalog-spark_2.13-0.4.1.jar|20000"
    "unitycatalog-client-0.5.1.jar|${MAVEN_BASE_URL}/io/unitycatalog/unitycatalog-client/0.5.1/unitycatalog-client-0.5.1.jar|400000"
    "unitycatalog-hadoop-0.5.1.jar|${MAVEN_BASE_URL}/io/unitycatalog/unitycatalog-hadoop/0.5.1/unitycatalog-hadoop-0.5.1.jar|40000"
    # Spark SQL Kafka connector — needed by any Structured Streaming job that
    # reads/writes Kafka (the realtime-mode demo, any streaming SDP source).
    # `spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.1.0`
    # is the textbook path but fails on the stock apache/spark:4.1.0 image —
    # Ivy can't write to user.home=/nonexistent. Pre-downloading here lets
    # spark-submit use --jars instead.
    "spark-sql-kafka-0-10_2.13-4.1.0.jar|${MAVEN_BASE_URL}/org/apache/spark/spark-sql-kafka-0-10_2.13/4.1.0/spark-sql-kafka-0-10_2.13-4.1.0.jar|400000"
    "spark-token-provider-kafka-0-10_2.13-4.1.0.jar|${MAVEN_BASE_URL}/org/apache/spark/spark-token-provider-kafka-0-10_2.13/4.1.0/spark-token-provider-kafka-0-10_2.13-4.1.0.jar|50000"
    "kafka-clients-3.9.0.jar|${MAVEN_BASE_URL}/org/apache/kafka/kafka-clients/3.9.0/kafka-clients-3.9.0.jar|8000000"
    "commons-pool2-2.12.0.jar|${MAVEN_BASE_URL}/org/apache/commons/commons-pool2/2.12.0/commons-pool2-2.12.0.jar|100000"
)

# Get file size (cross-platform)
get_file_size() {
    local file=$1
    if [[ "$OSTYPE" == "darwin"* ]]; then
        stat -f%z "$file" 2>/dev/null || echo 0
    else
        stat -c%s "$file" 2>/dev/null || echo 0
    fi
}

# Verify file size
verify_size() {
    local file=$1
    local min_size=$2

    if [ ! -f "$file" ]; then
        return 1
    fi

    local actual_size=$(get_file_size "$file")
    if [ "$actual_size" -ge "$min_size" ]; then
        return 0
    else
        echo -e "   ${RED}File too small: ${actual_size} bytes (expected >= ${min_size})${NC}"
        return 1
    fi
}

# Compute a file's sha256 (cross-platform: coreutils sha256sum or macOS shasum).
sha256_of() {
    local file=$1
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$file" | awk '{print $1}'
    else
        echo ""   # no tool → verify_checksum treats as "cannot verify"
    fi
}

# The expected sha256 for a jar from the lockfile (sha256sum format:
# "<hash>  <filename>"). Empty if the jar has no lock entry.
lock_sha() {
    [ -f "$LOCK_FILE" ] || { echo ""; return; }
    awk -v n="$1" '$2==n {print $1; exit}' "$LOCK_FILE"
}

# Verify a jar against the lock. 0 = ok (matched, or no entry in non-strict mode);
# 1 = fatal (mismatch, or missing entry under --strict-checksums, or no hash tool
# when an entry exists).
verify_checksum() {
    local file=$1 name=$2
    local want; want="$(lock_sha "$name")"

    if [ -z "$want" ]; then
        if [ "$STRICT_CHECKSUMS" = true ]; then
            echo -e "   ${RED}No sha256 lock entry for ${name} (--strict-checksums)${NC}"
            return 1
        fi
        echo -e "   ${YELLOW}⚠ no sha256 lock entry for ${name} — run --lock to pin it${NC}"
        return 0
    fi

    local got; got="$(sha256_of "$file")"
    if [ -z "$got" ]; then
        echo -e "   ${RED}Cannot compute sha256 (no sha256sum/shasum) but lock expects one${NC}"
        return 1
    fi
    if [ "$got" = "$want" ]; then
        return 0
    fi
    echo -e "   ${RED}sha256 MISMATCH for ${name}${NC}"
    echo -e "   ${RED}  expected ${want}${NC}"
    echo -e "   ${RED}  actual   ${got}${NC}"
    return 1
}

# Download with retry
download_with_retry() {
    local url=$1
    local output=$2
    local attempt=1

    while [ $attempt -le $MAX_RETRIES ]; do
        echo -e "   Attempt $attempt/$MAX_RETRIES..."

        if command -v wget >/dev/null 2>&1; then
            if wget -q -O "$output.tmp" "$url" 2>&1; then
                mv "$output.tmp" "$output"
                return 0
            fi
        elif command -v curl >/dev/null 2>&1; then
            if curl -sSL -o "$output.tmp" "$url" 2>&1; then
                mv "$output.tmp" "$output"
                return 0
            fi
        else
            echo -e "   ${RED}Neither wget nor curl available${NC}"
            return 1
        fi

        echo -e "   ${YELLOW}Download failed, retrying in ${RETRY_DELAY}s...${NC}"
        rm -f "$output.tmp"
        sleep $((RETRY_DELAY * attempt))
        attempt=$((attempt + 1))
    done

    echo -e "   ${RED}Download failed after $MAX_RETRIES attempts${NC}"
    return 1
}

# Verify-only mode
if [ "$VERIFY_ONLY" = true ]; then
    echo "Verifying JARs in ${JARS_DIR}..."
    has_errors=0

    for jar_entry in "${JAR_LIST[@]}"; do
        IFS='|' read -r jar_name url min_size <<< "$jar_entry"
        jar_path="${JARS_DIR}/${jar_name}"

        if [ ! -f "$jar_path" ]; then
            echo -e "${RED}✗${NC} $jar_name (missing)"
            has_errors=1
        elif ! verify_size "$jar_path" "$min_size"; then
            echo -e "${RED}✗${NC} $jar_name (invalid size)"
            has_errors=1
        elif ! verify_checksum "$jar_path" "$jar_name"; then
            echo -e "${RED}✗${NC} $jar_name (sha256 failed)"
            has_errors=1
        else
            echo -e "${GREEN}✓${NC} $jar_name (OK)"
        fi
    done

    exit $has_errors
fi

# Download mode
echo "Downloading JARs to ${JARS_DIR}..."
cd "${JARS_DIR}"

total=${#JAR_LIST[@]}
current=0
failed=0

for jar_entry in "${JAR_LIST[@]}"; do
    current=$((current + 1))
    IFS='|' read -r jar_name url min_size <<< "$jar_entry"

    echo -e "\n${YELLOW}[$current/$total]${NC} $jar_name"

    # Skip if already exists and valid (size AND sha256 — a cached but tampered
    # file must not be trusted just because it is present).
    if [ -f "$jar_name" ] && verify_size "$jar_name" "$min_size" \
        && verify_checksum "$jar_name" "$jar_name"; then
        echo -e "   ${GREEN}Already exists and valid${NC}"
        continue
    fi

    # Download
    echo -e "   Downloading..."
    if download_with_retry "$url" "$jar_name"; then
        if ! verify_size "$jar_name" "$min_size"; then
            echo -e "   ${RED}✗${NC} Downloaded file appears corrupt (size)"
            rm -f "$jar_name"
            failed=$((failed + 1))
        elif ! verify_checksum "$jar_name" "$jar_name"; then
            echo -e "   ${RED}✗${NC} Downloaded file failed sha256 verification"
            rm -f "$jar_name"
            failed=$((failed + 1))
        else
            echo -e "   ${GREEN}✓${NC} Download complete"
        fi
    else
        failed=$((failed + 1))
    fi
done

echo ""
echo "================================"

if [ $failed -ne 0 ]; then
    echo -e "${RED}$failed JAR(s) failed to download${NC}"
    echo "Run script again to retry failed downloads"
    exit 1
fi

echo -e "${GREEN}All JARs downloaded successfully!${NC}"
echo ""
echo "Total size:"
du -sh "${JARS_DIR}"

# --lock: (re)generate the committed sha256 lock from the bytes we just verified.
if [ "$LOCK_MODE" = true ]; then
    echo ""
    echo "Writing sha256 lock → ${LOCK_FILE}"
    {
        echo "# sha256 lock for open-lakehouse pinned JARs (docs/testing.md)."
        echo "# Generated by: scripts/tools/download-jars.sh --lock"
        echo "# Regenerate after any version bump and commit the diff."
    } > "${LOCK_FILE}.tmp"
    for jar_entry in "${JAR_LIST[@]}"; do
        IFS='|' read -r jar_name _url _min_size <<< "$jar_entry"
        h="$(sha256_of "${JARS_DIR}/${jar_name}")"
        [ -n "$h" ] && printf '%s  %s\n' "$h" "$jar_name" >> "${LOCK_FILE}.tmp"
    done
    # Keep the header, sort the entries for a stable, diff-friendly lock.
    { grep '^#' "${LOCK_FILE}.tmp"; grep -v '^#' "${LOCK_FILE}.tmp" | sort; } > "${LOCK_FILE}"
    rm -f "${LOCK_FILE}.tmp"
    echo -e "${GREEN}Lock written with $(grep -vc '^#' "${LOCK_FILE}") entries.${NC}"
fi

exit 0
