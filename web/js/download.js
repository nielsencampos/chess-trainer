// Saves a file the page made, the same way in a browser and in the desktop app's window.

/**
 * Saves a blob as a file with the given name.
 *
 * The object URL is revoked a minute later, not at once: WebKit (the macOS desktop window)
 * reads a blob download after the click returns, and fails on a URL already revoked.
 * @param {Blob} blob  The file's content.
 * @param {string} name  The file name to suggest.
 */
export function saveFile(blob, name) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 60_000);
}
