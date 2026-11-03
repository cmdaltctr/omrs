/**
 * The stored `eq01` chunks that hold maths (Kingma and Welling, arXiv 1312.6114),
 * read once from the fixture file. The header says what each text holds.
 */
import raw from "./fixtures/eq01-chunks.json?raw";

export interface Eq01Chunk {
  chunk_id: string;
  source: string;
  /** Formulas in this chunk, as counted when the fixture was built. */
  formulas: number;
  display_formulas: number;
  text: string;
}

const parsed = JSON.parse(raw) as { _header: { formulas: number; display_formulas: number }; chunks: Eq01Chunk[] };

export const EQ01_HEADER = parsed._header;
export const EQ01_CHUNKS: Eq01Chunk[] = parsed.chunks;
