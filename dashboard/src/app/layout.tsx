// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Open Lakehouse",
  description: "Unified UI for the open-lakehouse platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
