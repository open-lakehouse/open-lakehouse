"""Send sample Ethereum block events to a Kafka topic.

Used to feed the realtime-mode RTM pipeline with a deterministic mix of
clean blocks and blocks that should be quarantined (high gas usage, empty
blocks, PII in `extra_data`, leaked credentials).

Usage:

    poetry run python demos/realtime-mode/produce_test_data.py
    poetry run python demos/realtime-mode/produce_test_data.py --num-messages 500
    poetry run python demos/realtime-mode/produce_test_data.py --seeded   # 12 deterministic blocks then exit

Reads bootstrap servers from KAFKA_BOOTSTRAP_SERVERS (default localhost:9092).
Reads topic from KAFKA_TOPIC (default ethereum-blocks).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

from kafka import KafkaProducer


BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "ethereum-blocks")


SEEDED_BLOCKS: list[dict] = [
    {
        "_label": "clean",
        "gas_used": 8_000_000,
        "tx_count": 150,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB01",
        "extra_data": "Normal block data",
    },
    {
        "_label": "high_gas",
        "gas_used": 14_550_000,
        "tx_count": 180,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB02",
        "extra_data": "Heavy block",
    },
    {
        "_label": "empty_block",
        "gas_used": 0,
        "tx_count": 0,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB03",
        "extra_data": "no txns",
    },
    {
        "_label": "pii_email",
        "gas_used": 5_000_000,
        "tx_count": 100,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB04",
        "extra_data": "Contact: user@example.com for support",
    },
    {
        "_label": "clean",
        "gas_used": 7_500_000,
        "tx_count": 200,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB05",
        "extra_data": "Another normal block",
    },
    {
        "_label": "zero_miner",
        "gas_used": 6_000_000,
        "tx_count": 120,
        "miner": "0x0000000000000000000000000000000000000000",
        "extra_data": "Block with zero miner",
    },
    {
        "_label": "high_tx",
        "gas_used": 12_000_000,
        "tx_count": 600,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB07",
        "extra_data": "High transaction count block",
    },
    {
        "_label": "pii_ssn",
        "gas_used": 4_000_000,
        "tx_count": 80,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB08",
        "extra_data": "SSN leaked: 123-45-6789",
    },
    {
        "_label": "pii_credit_card",
        "gas_used": 3_500_000,
        "tx_count": 90,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB09",
        "extra_data": "Card: 4111-1111-1111-1111",
    },
    {
        "_label": "credential_aws_key",
        "gas_used": 5_500_000,
        "tx_count": 110,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB10",
        "extra_data": "Key: " + "AKIA" + "IOSFODNN7EXAMPLE",
    },
    {
        "_label": "high_gas+pii_email",
        "gas_used": 14_800_000,
        "tx_count": 300,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB11",
        "extra_data": "Alert admin@company.org immediately",
    },
    {
        "_label": "credential_jwt",
        "gas_used": 4_500_000,
        "tx_count": 95,
        "miner": "0x742d35Cc6634C0532925a3b844Bc9e7595f8dB12",
        "extra_data": "Token: "
        + ".".join(
            [
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
                "eyJzdWIiOiIxMjM0NTY3ODkwIn0",
                "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            ]
        ),
    },
]


def random_hex(byte_len: int) -> str:
    return "0x" + os.urandom(byte_len).hex()


def make_block(block_number: int, payload: dict) -> dict:
    gas_limit = 15_000_000
    return {
        "block_number": block_number,
        "block_hash": random_hex(32),
        "parent_hash": random_hex(32),
        "miner": payload["miner"],
        "gas_used": payload["gas_used"],
        "gas_limit": gas_limit,
        "transaction_count": payload["tx_count"],
        "timestamp": int(time.time()),
        "total_value_wei": str(random.randint(0, 10**18)),
        "extra_data": payload["extra_data"],
    }


def random_payload(block_number: int) -> dict:
    r = random.random()
    if r < 0.10:
        extra = f"Contact: user{block_number}@example.com"
    elif r < 0.15:
        extra = "SSN: 123-45-6789"
    elif r < 0.20:
        extra = "Card: 4111-1111-1111-1111"
    else:
        extra = "Normal transaction data"

    gas_used = random.randint(500_000, 1_800_000)
    if random.random() < 0.05:
        gas_used = int(15_000_000 * 0.96)

    tx_count = random.randint(10, 200)
    if random.random() < 0.05:
        tx_count = 0

    return {
        "gas_used": gas_used,
        "tx_count": tx_count,
        "miner": "0x" + os.urandom(20).hex(),
        "extra_data": extra,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Produce test Ethereum block events to Kafka for the RTM demo.",
    )
    parser.add_argument(
        "--num-messages",
        "-n",
        type=int,
        default=100,
        help="Number of random messages to send (0 = infinite). Ignored with --seeded.",
    )
    parser.add_argument(
        "--delay",
        "-d",
        type=float,
        default=0.1,
        help="Seconds between messages (default 0.1 = 10 msg/sec).",
    )
    parser.add_argument(
        "--seeded",
        action="store_true",
        help=(
            "Send the 12 deterministic blocks defined in SEEDED_BLOCKS and exit. "
            "Used by the demo's expected-output check."
        ),
    )
    parser.add_argument(
        "--start-block",
        type=int,
        default=4_000_000,
        help="Starting block_number for the random stream.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    producer = KafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: str(k).encode("utf-8"),
        acks="all",
    )

    print(f"bootstrap : {BOOTSTRAP}")
    print(f"topic     : {TOPIC}")

    if args.seeded:
        print(f"sending {len(SEEDED_BLOCKS)} seeded blocks")
        for i, payload in enumerate(SEEDED_BLOCKS, start=1):
            block_number = args.start_block + i
            block = make_block(block_number, payload)
            producer.send(TOPIC, key=block_number, value=block)
            print(f"  block_number={block_number} label={payload['_label']}")
        producer.flush()
        producer.close()
        return 0

    sent = 0
    block_number = args.start_block
    try:
        while args.num_messages == 0 or sent < args.num_messages:
            block = make_block(block_number, random_payload(block_number))
            producer.send(TOPIC, key=block_number, value=block)
            sent += 1
            block_number += 1
            if sent % 10 == 0:
                print(f"sent {sent}")
            time.sleep(args.delay)
    except KeyboardInterrupt:
        print(f"interrupted after {sent} messages")
    finally:
        producer.flush()
        producer.close()
        print(f"flushed; total messages sent: {sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
