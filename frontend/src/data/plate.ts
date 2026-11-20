/** An Israeli plate as it is printed: 12-345-67 for seven digits, 123-45-678 for eight.
 *  The stored number keeps its leading zeros, which are not on the plate. */
export function formatPlate(value: string): string {
  const digits = value.replace(/\D/g, "").replace(/^0+(?=\d{7})/, "");
  if (digits.length === 7) return `${digits.slice(0, 2)}-${digits.slice(2, 5)}-${digits.slice(5)}`;
  if (digits.length === 8) return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
  return value;
}
