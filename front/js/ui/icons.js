// Inline SVG icons (stroke = currentColor). Each returns trusted markup.
import { raw } from '../lib/html.js';

const svg = (size, body, cls = '') =>
  raw(
    `<svg${cls ? ` class="${cls}"` : ''} xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`,
  );

export const iconUser = () => svg(16, '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>', 'input-icon');
export const iconLock = () => svg(16, '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>', 'input-icon');
export const iconEye = () => svg(16, '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>');
export const iconEyeOff = () =>
  svg(16, '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>');
export const iconLogout = () => svg(15, '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>');
export const iconHome = () => svg(18, '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h5v-6h4v6h5V10"/>');
export const iconShield = () => svg(18, '<path d="M12 3 4 6v6c0 4.5 3.2 8 8 9 4.8-1 8-4.5 8-9V6l-8-3z"/><polyline points="9 12 11 14 15 10"/>');
export const iconUsers = () => svg(18, '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>');
export const iconPlay = () => svg(16, '<polygon points="5 3 19 12 5 21 5 3"/>');
export const iconStop = () => svg(16, '<rect x="6" y="6" width="12" height="12"/>');
export const iconChevron = () => svg(16, '<polyline points="6 9 12 15 18 9"/>');
export const iconCheck = () => svg(16, '<polyline points="20 6 9 17 4 12"/>');
export const iconPlus = () => svg(16, '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>');
