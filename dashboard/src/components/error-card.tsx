// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { AlertCircle, RefreshCw } from "lucide-react";

interface ErrorCardProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  hint?: string;
}

export function ErrorCard({ title = "Error", message, onRetry, hint }: ErrorCardProps) {
  return (
    <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <AlertCircle className="text-red-400 mt-0.5 shrink-0" size={20} />
        <div className="flex-1 min-w-0">
          <h3 className="text-red-400 font-medium">{title}</h3>
          <p className="text-slate-300 text-sm mt-1">{message}</p>
          {hint && (
            <p className="text-slate-400 text-xs mt-2">{hint}</p>
          )}
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 text-slate-200 rounded transition-colors shrink-0"
            aria-label="Retry"
          >
            <RefreshCw size={14} />
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
