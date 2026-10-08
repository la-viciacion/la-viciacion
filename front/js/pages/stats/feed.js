// The activity feed read back in time for the line chart: its "played" events are the only per-day figures the
// group can see. GET /activity, newest first, 100 at a time; what is read is kept while the page is open.
import { api } from '../../lib/api.js';

const PAGE = 100;
const MAX_PAGES = 40; // the feed gets slower the further back it is read: past this the chart starts later

let items = [];
let hasMore = true;
let generation = 0;
let reading = Promise.resolve(); // one read at a time, so two pills clicked in a row do not read the same page twice

export function resetFeed() {
  items = [];
  hasMore = true;
  generation += 1;
  reading = Promise.resolve();
}

/**
 * Reads back to `since` ("2026-01-01"), or to the very first event when null.
 * -> { items, truncated } (truncated: the cap stopped it before `since`), or undefined when the session ended.
 */
export function feedSince(since) {
  const mine = generation;
  const reached = () => since !== null && items.length > 0 && items.at(-1).day < since;
  const read = reading.then(async () => {
    while (mine === generation && hasMore && !reached() && items.length < PAGE * MAX_PAGES) {
      const page = await api(`/activity?limit=${PAGE}&offset=${items.length}`);
      if (!page) return undefined;
      if (mine !== generation) return undefined;
      items = items.concat(page.items);
      hasMore = page.has_more;
    }
    return mine === generation ? { items, truncated: hasMore && !reached() } : undefined;
  });
  reading = read.catch(() => {});
  return read;
}
