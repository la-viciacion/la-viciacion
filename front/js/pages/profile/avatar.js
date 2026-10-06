// Profile picture: pick a file, crop and shrink it in the browser, upload it, and swap it in
// the profile header and the navbar without reloading.
import { api, forgetAvatars } from '../../lib/api.js';
import { flash } from './flash.js';

const AVATAR_SIZE = 256;

// Center-crop to a square and shrink, so the stored avatar stays small.
function resizeImage(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const src = URL.createObjectURL(file);
    img.onload = () => {
      const side = Math.min(img.width, img.height);
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = AVATAR_SIZE;
      canvas.getContext('2d').drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, AVATAR_SIZE, AVATAR_SIZE);
      URL.revokeObjectURL(src);
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('No se pudo procesar la imagen'))), 'image/jpeg', 0.9);
    };
    img.onerror = () => { URL.revokeObjectURL(src); reject(new Error('El archivo no es una imagen válida')); };
    img.src = src;
  });
}

// Swap a placeholder (or old image) for the new picture, keeping its classes.
function showAvatar(el, url) {
  if (!el) return;
  const img = document.createElement('img');
  img.src = url;
  img.alt = '';
  img.className = el.className.replace(/\s*(navbar|pf)-avatar-placeholder/, '').trim();
  if (el.id) img.id = el.id;
  el.replaceWith(img);
}

export function initAvatar(main, { path }) {
  main.querySelector('#pfAvatarInput').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    const msg = main.querySelector('#pfAvatarMsg');
    if (!['image/jpeg', 'image/png'].includes(file.type)) return flash(msg, 'Solo se admiten imágenes JPG o PNG');
    flash(msg, 'Subiendo…', true);
    try {
      const small = await resizeImage(file);
      const form = new FormData();
      form.append('file', small, 'avatar.jpg');
      await api(path, { method: 'PATCH', body: form });
      forgetAvatars();
      const url = URL.createObjectURL(small);
      showAvatar(main.querySelector('#pfAvatar'), url);
      showAvatar(document.querySelector('.navbar-avatar'), url);
      flash(msg, 'Foto actualizada', true);
    } catch (err) {
      flash(msg, err.message);
    }
  });
}
