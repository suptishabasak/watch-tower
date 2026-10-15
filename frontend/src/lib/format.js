export const INTERVALS = [
  { value: 15, label: "15 minutes" },
  { value: 60, label: "1 hour" },
  { value: 360, label: "6 hours" },
  { value: 1440, label: "24 hours" },
];

export function intervalLabel(minutes) {
  return INTERVALS.find((i) => i.value === minutes)?.label ?? `${minutes} minutes`;
}

function span(seconds) {
  const abs = Math.abs(seconds);
  if (abs < 45) return "a few seconds";
  const minutes = Math.round(abs / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(abs / 3600);
  if (hours < 24) return `${hours} hr`;
  const days = Math.round(abs / 86400);
  return `${days} day${days === 1 ? "" : "s"}`;
}

export function timeAgo(iso) {
  if (!iso) return "Never";
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 45) return "Just now";
  return `${span(seconds)} ago`;
}

export function timeUntil(iso) {
  if (!iso) return "Not scheduled";
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  if (seconds <= 45) return "Due now";
  return `in ${span(seconds)}`;
}

export function fullDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function displayUrl(url) {
  return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
}