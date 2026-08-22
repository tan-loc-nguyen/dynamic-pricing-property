"use client";

import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-ink-200 bg-white ${className}`}>{children}</div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h1 className="text-[22px] font-semibold text-ink-900 leading-tight">{title}</h1>
        {subtitle && <p className="text-[13px] text-ink-500 mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  accepted: "bg-emerald-50 text-emerald-700 border-emerald-200",
  overridden: "bg-violet-50 text-violet-700 border-violet-200",
};
const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  accepted: "Accepted",
  overridden: "Overridden",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${
        STATUS_STYLES[status] || "bg-ink-100 text-ink-600 border-ink-200"
      }`}
    >
      {STATUS_LABELS[status] || status}
    </span>
  );
}

export function Chip({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "up" | "down" | "warn" | "info";
  title?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "bg-ink-100 text-ink-600",
    up: "bg-emerald-50 text-emerald-700",
    down: "bg-rose-50 text-rose-700",
    warn: "bg-amber-50 text-amber-700",
    info: "bg-sky-50 text-sky-700",
  };
  return (
    <span title={title} className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "secondary",
  size = "md",
  disabled,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  const variants: Record<string, string> = {
    primary: "bg-brand-600 text-white hover:bg-brand-700 border-transparent",
    secondary: "bg-white text-ink-700 hover:bg-ink-50 border-ink-200",
    ghost: "bg-transparent text-ink-600 hover:bg-ink-100 border-transparent",
    danger: "bg-white text-rose-600 hover:bg-rose-50 border-rose-200",
  };
  const sizes: Record<string, string> = {
    sm: "px-2.5 py-1 text-[12px]",
    md: "px-3.5 py-1.5 text-[13px]",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg border font-medium transition-colors disabled:opacity-45 disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <div className="text-[12px] font-medium text-ink-700">{label}</div>
      {hint && <div className="text-[11px] text-ink-400 mt-0.5 leading-snug">{hint}</div>}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-ink-200 bg-white px-2.5 py-1.5 text-[13px] text-ink-900 outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100 transition";

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="py-16 text-center">
      <div className="text-[14px] font-medium text-ink-700">{title}</div>
      {hint && <div className="text-[12px] text-ink-400 mt-1">{hint}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="py-16 text-center text-[13px] text-ink-400">
      <div className="inline-block h-4 w-4 rounded-full border-2 border-ink-200 border-t-brand-500 animate-spin mr-2 align-middle" />
      {label}
    </div>
  );
}
