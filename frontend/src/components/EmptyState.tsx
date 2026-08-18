export default function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
        <rect x="6" y="14" width="28" height="20" rx="4" stroke="currentColor" strokeWidth="2" />
        <path d="M6 20h28" stroke="currentColor" strokeWidth="2" />
        <path d="M14 8l-3 6M26 8l3 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <p>{message}</p>
    </div>
  );
}
