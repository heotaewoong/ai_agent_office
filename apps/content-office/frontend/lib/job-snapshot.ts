import type { Job } from "./types";

/** Polling JSON has no cycles or methods. Compare every field, including task-only updates. */
export function reuseUnchangedJob(previous: Job | null, next: Job): Job {
  return previous && JSON.stringify(previous) === JSON.stringify(next) ? previous : next;
}
