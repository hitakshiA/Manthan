import { twMerge } from "tailwind-merge";

type ClassValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | { [k: string]: boolean | undefined | null }
  | ClassValue[];

function flatten(value: ClassValue): string[] {
  if (!value) return [];
  if (typeof value === "string") return [value];
  if (typeof value === "number") return [String(value)];
  if (Array.isArray(value)) return value.flatMap(flatten);
  if (typeof value === "object") {
    return Object.entries(value)
      .filter(([, v]) => Boolean(v))
      .map(([k]) => k);
  }
  return [];
}

/**
 * Combines class values and dedupes Tailwind conflicts.
 * Mirrors clsx + tailwind-merge without an extra dep.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(inputs.flatMap(flatten).join(" "));
}
