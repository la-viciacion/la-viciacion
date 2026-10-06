# Achievement pictures

One file per achievement, named after its key: `EARLY_RISER.png` (PNG or JPG). They are the **originals**: every
time the API starts it puts them in the database (`achievements.image`), shrunk and re-encoded exactly as an upload
from the admin panel is, and only when they differ from what the database has.

- **The file wins.** An achievement with a file gets that picture at every start, replacing one uploaded by hand in
  the panel. An achievement without a file is left alone.
- To change a picture, replace its file, run `python -m src.utils.achievement_images` (from `api/`) to shrink it for
  the repository, and restart the API.
- Do not put anything else here: unknown names are logged and skipped. Details in `docs/architecture.md`.
