"use client";

import type { ButtonHTMLAttributes } from "react";

export default function JupyterLaunchButton({
  path = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { path?: string }) {
  return (
    <form
      action="/api/jupyter-launch"
      method="post"
      target="_blank"
      rel="noopener"
      className="contents"
      onClick={(event) => event.stopPropagation()}
    >
      <input type="hidden" name="path" value={path} />
      <button {...props} type="submit">
        {children}
      </button>
    </form>
  );
}
