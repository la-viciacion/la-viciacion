// The password recovery link of the email: `#/reset-password?token=...`. The token travels in the
// URL fragment, so it is never sent to a server nor left in an access log.

export const RESET_ROUTE = '#/reset-password';

export const isResetRoute = (hash) => hash === RESET_ROUTE || hash.startsWith(`${RESET_ROUTE}?`);

/** The token of a recovery link, or null when the hash has none. */
export function resetTokenFromHash(hash) {
  const query = hash.split('?')[1] ?? '';
  return new URLSearchParams(query).get('token') || null;
}
