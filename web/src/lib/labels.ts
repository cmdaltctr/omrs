/** Display labels that keep the server's meaning. Copy is British English. */

const SCORE_KINDS: Record<string, string> = {
  dense_similarity_v1: "Dense similarity",
  rrf_v1: "Reciprocal rank fusion",
  reranker_sigmoid_v1: "Reranker sigmoid",
};

/** Names the score kind and keeps the raw identifier, so scores are never compared across kinds by mistake. */
export function scoreKindLabel(kind: string): string {
  return `${SCORE_KINDS[kind] ?? "Unknown score kind"} (${kind})`;
}

export function formatScore(score: number): string {
  return score.toFixed(4);
}

/**
 * Machine-local availability. `null` means the server cannot tell (for example
 * a relative stored path); it never means the source is lost.
 */
export function availabilityLabel(orphaned: boolean | null | undefined): string {
  if (orphaned === true) return "Missing on this machine";
  if (orphaned === false) return "Present on this machine";
  return "Unknown on this machine";
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** "Chunk 3 of 4" from a zero-based index; null parts are left out. */
/** "Page 5", or "Pages 5–6" for a merged row that spans pages (first to last label). */
export function pageText(pageLabel: string | null | undefined, pageLabels?: string[]): string | null {
  if (pageLabels !== undefined && pageLabels.length > 1) return `Pages ${pageLabels[0]}–${pageLabels[pageLabels.length - 1]}`;
  return pageLabel ? `Page ${pageLabel}` : null;
}

export function chunkPosition(index: number | null, count: number | null): string {
  if (index === null) return "Position unknown";
  return count === null ? `Chunk ${index + 1}` : `Chunk ${index + 1} of ${count}`;
}
