export default function ErrorBanner({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return <p style={{ color: "var(--danger)", marginTop: "0.5rem" }}>{message}</p>;
}
