"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import JupyterLaunchButton from "@/components/jupyter-launch-button";

const messages: Record<string, [string, string]> = {
  unavailable: [
    "Jupyter isn't running",
    "Start the notebook service, then try again.",
  ],
  credentials: [
    "Jupyter needs reconnecting",
    "The dashboard's sign-in details don't match the running notebook server.",
  ],
  unconfigured: [
    "Jupyter needs sign-in details",
    "Configure the dashboard with the same token as your notebook server, or sign in directly.",
  ],
  disabled: [
    "Automatic sign-in isn't enabled",
    "You can open Jupyter and sign in directly.",
  ],
};

function JupyterLaunchStatus() {
  const params = useSearchParams();
  const [loginUrl, setLoginUrl] = useState("http://localhost:8889/lab");
  useEffect(() => {
    const url = new URL(window.location.href);
    url.port = "8889";
    url.pathname = "/lab";
    url.search = "";
    url.hash = "";
    setLoginUrl(url.toString());
  }, []);
  const [title, detail] = messages[params.get("error") || ""] || [
    "Open JupyterLab",
    "Connect to your running notebook server.",
  ];
  return (
    <div className="card mx-auto mt-10 max-w-lg space-y-4">
      <h1 className="text-xl font-semibold text-white">{title}</h1>
      <p className="text-sm text-slate-400">{detail}</p>
      <div className="flex items-center gap-4">
        <JupyterLaunchButton
          formTarget="_self"
          path={params.get("path") || ""}
          className="btn-primary"
        >
          Try again
        </JupyterLaunchButton>
        <a
          href={loginUrl}
          className="text-sm text-accent hover:underline"
          rel="noreferrer"
        >
          Open sign-in page
        </a>
      </div>
    </div>
  );
}

export default function JupyterPage() {
  return (
    <Suspense
      fallback={<p className="text-slate-400">Connecting to Jupyter…</p>}
    >
      <JupyterLaunchStatus />
    </Suspense>
  );
}
