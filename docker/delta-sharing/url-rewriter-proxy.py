#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Containerized Lakehouse Platform Contributors
"""
OpenSharing Response URL Re-signing Proxy

This proxy intercepts responses from the OpenSharing server and replaces the
pre-signed S3 URLs it emits with freshly signed URLs pointing at this stack's
SeaweedFS S3 endpoint.

Why re-sign rather than swap the host: the Delta Sharing server has an upstream
bug (T-4.8, delta-io/delta-sharing#753) — its S3FileSigner ignores
fs.s3a.endpoint and always signs URLs for s3.amazonaws.com. Simply rewriting the
hostname would invalidate the SigV4 signature, so the proxy computes a brand-new
signature for the target endpoint, which SeaweedFS then verifies (see the
seaweedfs-ops skill: signed-host == delivered-host on the local path; modes B/C
via X-Forwarded-Host / Host override for a public tunnel).

The S3 endpoint, scheme, and credentials are read from environment variables.
"""

import hashlib
import hmac
import logging
import os
import re
import ssl
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Connection pool for upstream OpenSharing requests
_session = requests.Session()
_retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
_session.mount(
    "https://", HTTPAdapter(max_retries=_retry, pool_connections=10, pool_maxsize=20)
)
_session.mount(
    "http://", HTTPAdapter(max_retries=_retry, pool_connections=10, pool_maxsize=20)
)
_session.verify = False  # Self-signed cert for upstream OpenSharing

# Configuration from environment variables
UPSTREAM_HOST = os.getenv("DELTA_SHARING_HOST", "localhost")
UPSTREAM_PORT = int(os.getenv("DELTA_SHARING_PORT", "8444"))  # Internal port
PROXY_PORT = int(os.getenv("PROXY_PORT", "8443"))  # External port
# The public S3 endpoint the CLIENT will reach. Default = the host-published
# SeaweedFS port, so `./lakehouse share` works locally with no tunnel. Override
# to a public tunnel host (with S3_PUBLIC_SCHEME=https) for external sharing.
S3_PUBLIC_ENDPOINT = os.getenv("S3_PUBLIC_ENDPOINT", "localhost:8333")
S3_PUBLIC_SCHEME = os.getenv("S3_PUBLIC_SCHEME", "http")
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Regex to match pre-signed S3 URLs in JSON responses
# Matches virtual-hosted style: https://bucket.s3.amazonaws.com/key?X-Amz-...
# Matches path style: https://s3.amazonaws.com/bucket/key?X-Amz-...
# Matches internal SeaweedFS: http://seaweedfs:8333/bucket/key?X-Amz-...
PRESIGNED_URL_PATTERN = re.compile(
    r'"(https?://(?:[a-zA-Z0-9\-]+\.s3\.amazonaws\.com|s3\.amazonaws\.com|seaweedfs:8333)/[^"]*X-Amz-Signature=[^"]*)"'
)


def _sign(key, msg):
    """HMAC-SHA256 signing helper"""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(secret_key, date_stamp, region, service):
    """Derive the AWS v4 signing key"""
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def generate_presigned_url(bucket, key, expires_in=3600):
    """
    Generate a new AWS v4 pre-signed GET URL for the SeaweedFS tunnel endpoint.
    Uses path-style access: https://tunnel-host/bucket/key
    """
    host = S3_PUBLIC_ENDPOINT
    now = datetime.now(timezone.utc)
    date_stamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    credential_scope = f"{date_stamp}/{AWS_REGION}/s3/aws4_request"
    credential = f"{AWS_ACCESS_KEY}/{credential_scope}"

    # Build canonical request for pre-signed URL (query string auth)
    canonical_uri = f'/{bucket}/{quote(key, safe="/~")}'

    # Query parameters (must be in alphabetical order for canonical request)
    query_params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": credential,
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_in),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_querystring = "&".join(
        f'{k}={quote(str(v), safe="")}' for k, v in sorted(query_params.items())
    )

    canonical_headers = f"host:{host}\n"
    signed_headers = "host"
    payload_hash = "UNSIGNED-PAYLOAD"

    canonical_request = "\n".join(
        [
            "GET",
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )

    # String to sign
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    # Calculate signature
    signing_key = _get_signature_key(AWS_SECRET_KEY, date_stamp, AWS_REGION, "s3")
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Build final URL
    final_qs = f"{canonical_querystring}&X-Amz-Signature={signature}"
    return f"{S3_PUBLIC_SCHEME}://{host}{canonical_uri}?{final_qs}"


def parse_s3_url(url):
    """Extract bucket and (percent-decoded) key from various S3 URL formats.

    urlparse(...).path is NOT percent-decoded, so unquote the key before
    returning it: generate_presigned_url re-encodes it once with quote(), and
    re-quoting an already-encoded key would double-encode '%' (e.g. %20 -> %2520),
    yielding a key that no longer matches the stored object.
    """
    parsed = urlparse(url.split("?")[0])  # Remove query string

    # Virtual-hosted style: bucket.s3.amazonaws.com/key
    if ".s3.amazonaws.com" in parsed.hostname:
        bucket = parsed.hostname.split(".s3.amazonaws.com")[0]
        return bucket, unquote(parsed.path.lstrip("/"))

    # Path-style: s3.amazonaws.com/bucket/key or seaweedfs:8333/bucket/key
    path_parts = parsed.path.lstrip("/").split("/", 1)
    if len(path_parts) >= 2:
        return path_parts[0], unquote(path_parts[1])

    return None, None


def resign_url(match):
    """Replace a pre-signed S3 URL with a freshly signed SeaweedFS tunnel URL"""
    original_url = match.group(1)
    bucket, key = parse_s3_url(original_url)

    if not bucket or not key:
        logger.warning(f"Could not parse S3 URL: {original_url[:80]}...")
        return match.group(0)  # Return unchanged

    # Extract expiration from original URL (default 3600s)
    try:
        qs = parse_qs(urlparse(original_url).query)
        expires = int(qs.get("X-Amz-Expires", ["3600"])[0])
    except (ValueError, IndexError):
        expires = 3600

    new_url = generate_presigned_url(bucket, key, expires)
    return f'"{new_url}"'


def rewrite_response_body(body, content_type):
    """Re-sign pre-signed URLs in response body"""
    if not body:
        return body

    # Only process JSON/NDJSON responses (where pre-signed URLs appear)
    if "json" not in content_type.lower() and "ndjson" not in content_type.lower():
        return body

    try:
        text = body.decode("utf-8")

        # Re-sign all pre-signed S3 URLs, counting via the substitution callback
        # (avoids a second full-body regex scan just to log the count).
        count = 0

        def _count_and_resign(match):
            nonlocal count
            count += 1
            return resign_url(match)

        text = PRESIGNED_URL_PATTERN.sub(_count_and_resign, text)

        if count:
            logger.info(
                f"✓ Re-signed {count} pre-signed URL(s) for endpoint: {S3_PUBLIC_ENDPOINT}"
            )
        return text.encode("utf-8")
    except Exception as e:
        logger.error(f"Error re-signing response: {e}")
        return body


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP request handler that proxies to OpenSharing and rewrites responses"""

    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")

    def do_GET(self):
        self.proxy_request()

    def do_POST(self):
        self.proxy_request()

    def do_HEAD(self):
        self.proxy_request()

    def proxy_request(self):
        """Forward request to upstream OpenSharing server and rewrite response"""
        try:
            # Build upstream URL
            upstream_url = f"https://{UPSTREAM_HOST}:{UPSTREAM_PORT}{self.path}"

            # Get request body if present
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else None

            # Forward request to upstream (session has verify=False for self-signed
            # cert). Drop Accept-Encoding so the upstream returns identity: `requests`
            # transparently decompresses response.content, and we re-emit that
            # decompressed body — forwarding a gzip Content-Encoding over plaintext
            # bytes would make the client fail to gunzip.
            response = _session.request(
                method=self.command,
                url=upstream_url,
                headers={
                    k: v
                    for k, v in self.headers.items()
                    if k.lower() not in ("host", "accept-encoding")
                },
                data=body,
                allow_redirects=False,
                timeout=60,
            )

            # Send response status
            self.send_response(response.status_code)

            # Rewrite response body before sending headers (Content-Length may change)
            content_type = response.headers.get("Content-Type", "")
            rewritten_body = rewrite_response_body(response.content, content_type)

            # Forward response headers with corrected Content-Length. Drop
            # content-encoding too: `requests` already decompressed the body, so the
            # bytes we emit are identity — keeping a gzip label would corrupt them.
            for key, value in response.headers.items():
                if key.lower() in (
                    "connection",
                    "transfer-encoding",
                    "content-length",
                    "content-encoding",
                ):
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(rewritten_body)))
            self.end_headers()

            self.wfile.write(rewritten_body)

        except requests.exceptions.Timeout:
            logger.error("Upstream request timed out")
            self.send_error(504, "Gateway Timeout")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Upstream connection failed: {e}")
            self.send_error(502, "Bad Gateway: upstream connection refused")
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            self.send_error(502, f"Bad Gateway: {str(e)}")


def main():
    """Start the proxy server"""
    logger.info("=" * 60)
    logger.info("OpenSharing URL Re-signing Proxy")
    logger.info("=" * 60)
    logger.info(f"Upstream: https://{UPSTREAM_HOST}:{UPSTREAM_PORT}")
    logger.info(f"Proxy listening on: https://0.0.0.0:{PROXY_PORT}")
    logger.info(f"SeaweedFS endpoint: {S3_PUBLIC_SCHEME}://{S3_PUBLIC_ENDPOINT}")
    logger.info(
        f"Re-signing: S3 pre-signed URLs → {S3_PUBLIC_ENDPOINT} (path-style, AWS v4)"
    )
    logger.info(f"Credentials: {'configured' if AWS_ACCESS_KEY else 'NOT SET'}")
    logger.info("=" * 60)

    # Create HTTPS server
    server = HTTPServer(("0.0.0.0", PROXY_PORT), ProxyHandler)

    # Wrap with SSL using self-signed certs
    cert_file = os.getenv("SSL_CERT_FILE", "/opt/delta-sharing/certs/server.crt")
    key_file = os.getenv("SSL_KEY_FILE", "/opt/delta-sharing/certs/server.key")

    if os.path.exists(cert_file) and os.path.exists(key_file):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
        logger.info(f"✓ SSL enabled with cert: {cert_file}")
    else:
        logger.warning("⚠ SSL certificates not found, running HTTP only")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down proxy server...")
        server.shutdown()


if __name__ == "__main__":
    main()
