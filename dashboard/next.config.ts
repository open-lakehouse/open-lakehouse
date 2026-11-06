// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async redirects() {
    // The old static Storage page became the Data Lake browser.
    return [{ source: "/storage", destination: "/datalake", permanent: false }];
  },
};

export default nextConfig;
