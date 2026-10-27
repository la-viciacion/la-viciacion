// Foldable sections ("ach-block" cards with a "data-fold" header button): which keys are folded and the toggle itself.
// With a storage key the choice is remembered in this browser (a per-viewer convenience only: a browser that refuses
// storage just forgets); without one it lives as long as the page.

export function createFolds(storageKey = null) {
  let keys = new Set();
  if (storageKey) {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
      if (Array.isArray(saved)) keys = new Set(saved);
    } catch {
      // nothing saved, or unreadable: everything starts open
    }
  }
  const save = () => {
    if (!storageKey) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify([...keys]));
    } catch {
      // nothing to do: it is not remembered
    }
  };
  return {
    has: (key) => keys.has(key),
    clear: () => keys.clear(),
    /** Folds or unfolds `key`; true when that changed something. */
    set(key, folded) {
      if (keys.has(key) === folded) return false;
      if (folded) keys.add(key);
      else keys.delete(key);
      save();
      return true;
    },
  };
}

/** Marks a section and its header button as folded or open (the markup of the section follows `folds`). */
export function showFold(section, button, folded) {
  section.classList.toggle('folded', folded);
  button.setAttribute('aria-expanded', String(!folded));
}

/** A click on a header button: flips its key and updates the section it belongs to. */
export function toggleFold(folds, key, section, button) {
  const folded = !folds.has(key);
  folds.set(key, folded);
  showFold(section, button, folded);
}
