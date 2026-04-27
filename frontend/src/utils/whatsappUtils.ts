import { cleanPhone } from './phoneUtils';

/**
 * Build a WhatsApp deep link URL with a pre-filled message.
 *
 * @param phone - Phone number (will be cleaned to digits only).
 * @param message - Message text to pre-fill.
 * @returns URL in format https://wa.me/{digits}?text={encoded_message}
 */
export function buildWhatsAppUrl(phone: string, message: string): string {
  const cleaned = cleanPhone(phone);
  const encoded = encodeURIComponent(message);
  return `https://wa.me/${cleaned}?text=${encoded}`;
}
