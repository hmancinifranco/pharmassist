/**
 * Clean a phone number string by removing all non-digit characters.
 * Preserves digit order from the original string.
 *
 * Example: "+54 9 11 1234-5678" → "5491112345678"
 */
export function cleanPhone(phone: string): string {
  return phone.replace(/\D/g, '');
}
