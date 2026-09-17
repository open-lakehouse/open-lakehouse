// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import DOMPurify from "isomorphic-dompurify";

/**
 * HTML sanitizer for notebook output rendered via dangerouslySetInnerHTML.
 *
 * Uses DOMPurify (a DOM-based sanitizer) rather than regex, so it also closes
 * the classes regex can't: HTML-entity-encoded schemes (e.g. &#106;avascript:),
 * leading-whitespace/control-char URLs, and unclosed/malformed tags. DOMPurify
 * removes scripts, event-handler attributes, javascript: URLs, and scriptable
 * data: URIs by default, while keeping data:image/* on <img> for notebook image
 * output. We additionally forbid embedding/interactive tags.
 */
export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    FORBID_TAGS: [
      "script",
      "iframe",
      "embed",
      "object",
      "form",
      "input",
      "textarea",
      "select",
      "button",
    ],
  });
}
