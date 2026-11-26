/** Novak's mark: a house with something listening inside. Colours come from tokens. */
export function Mark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <path d="M7 15.5 16 8l9 7.5V24a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1z" fill="none" stroke="var(--on-accent)" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="16" cy="18.5" r="2.6" fill="var(--on-accent)" />
    </svg>
  );
}
