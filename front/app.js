// Legacy entry point. Browsers (and old service workers) that still hold the
// pre-refactor index.html ask for /app.js; forward them to the current app so
// they keep working until their caches refresh. Safe to delete later.
import './js/main.js';
