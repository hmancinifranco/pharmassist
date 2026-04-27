/**
 * Build a Google Maps search URL from latitude and longitude.
 *
 * @param lat - Latitude coordinate.
 * @param lon - Longitude coordinate.
 * @returns URL in format https://www.google.com/maps/search/?api=1&query={lat},{lon}
 */
export function buildGoogleMapsUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`;
}
