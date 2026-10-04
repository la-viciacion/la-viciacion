// Hands a text to the browser as a file to save.

/** Save `text` as `filename` (the download starts at once; nothing is uploaded anywhere). */
export function saveFile(filename, text, type = 'application/octet-stream') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
