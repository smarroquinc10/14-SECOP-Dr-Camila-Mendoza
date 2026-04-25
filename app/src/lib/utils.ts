import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** Tailwind class-merge helper (shadcn convention). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Colombian peso formatter. */
export const moneyCO = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

/** YYYY-MM-DD formatter (drops the time component SECOP returns). */
export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  return String(iso).slice(0, 10);
}

/** Slice a long string with ellipsis. */
export function truncate(s: string | undefined | null, n: number): string {
  if (!s) return "";
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

/** Convert SECOP's confidence string to a Tailwind color class. */
export function confidenceColor(c?: string | null): string {
  switch (c) {
    case "HIGH":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "MEDIUM":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "LOW":
      return "bg-rose-50 text-rose-700 border-rose-200";
    default:
      return "bg-stone-50 text-stone-700 border-stone-200";
  }
}
