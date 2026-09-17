// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import type { Config } from "tailwindcss";

// Palette mirrors openlakehouse.io: near-black navy background, dark navy cards,
// and the signature magenta accent (rgb(217,90,226)).
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#1e243e", // cards
          dark: "#080a17", // page background
          light: "#2a325a", // raised / hover
        },
        accent: {
          DEFAULT: "#d95ae2", // signature magenta
          hover: "#c840d2",
        },
      },
      fontFamily: {
        // openlakehouse.io uses the system UI sans — no custom webfont.
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
