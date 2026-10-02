// Password rules, mirroring the API (validate_password_requirements) so the
// forms can reject a bad password before sending it.

export const PASSWORD_HINT = '12-24 caracteres, con mayúscula, minúscula, número y un carácter especial.';

const RULES = [/^.{12,24}$/, /[A-Z]/, /[a-z]/, /\d/, /[!@#$%^&*()_+{}[\]:;<>,.?/~\\-]/];

export const isValidPassword = (password) => RULES.every((re) => re.test(password));

const SETS = ['ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghijkmnopqrstuvwxyz', '23456789', '!@#$%&*?'];

/** Random password that satisfies every rule (ambiguous characters left out). */
export function generatePassword(length = 16) {
  const rand = (n) => crypto.getRandomValues(new Uint32Array(1))[0] % n;
  const all = SETS.join('');
  const chars = SETS.map((s) => s[rand(s.length)]);
  while (chars.length < length) chars.push(all[rand(all.length)]);
  for (let i = chars.length - 1; i > 0; i--) {
    const j = rand(i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join('');
}
