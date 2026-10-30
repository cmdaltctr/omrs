const TONES = {
  info: "rounded-small border border-status-info bg-status-info/10 px-3 py-2 text-ui text-status-info-label",
  warning: "rounded-small border border-status-warning bg-status-warning/10 px-3 py-2 text-ui text-status-warning-label",
} as const;

/** Fixed words on the llama.cpp card: the facts of a Chat server choice (`info`) or a warning. */
export function ServerCallout({ text, tone = "info" }: { text: string; tone?: keyof typeof TONES }) {
  return (
    <p role="note" className={TONES[tone]}>
      {text}
    </p>
  );
}
