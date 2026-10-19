// Click on a screenshot to see it at full size; click again or press Esc to close.
document$.subscribe(() => {
  document.querySelectorAll(".md-typeset img.screenshot").forEach((img) => {
    img.style.cursor = "zoom-in";
    img.addEventListener("click", () => {
      const dialog = document.createElement("dialog");
      dialog.className = "screenshot-zoom";
      const big = document.createElement("img");
      big.src = img.currentSrc || img.src;
      big.alt = img.alt;
      dialog.append(big);
      dialog.addEventListener("click", () => dialog.close());
      dialog.addEventListener("close", () => dialog.remove());
      document.body.append(dialog);
      dialog.showModal();
    });
  });
});
