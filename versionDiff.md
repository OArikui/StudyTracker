# Version diff — StudyTracker ViewerPack v0.8.1

## v0.8.0 → v0.8.1

- Fixed launch API to accept the host-provided `database_path`.
- Removed Viewer-local DB path settings and the independent database picker.
- Bound the Viewer to the DB path resolved by StudyTracker.
- Bumped the add-on version to 0.8.1.

# Version diff — StudyTracker ViewerV0 v0.8.0

## v0.7.1 → v0.8.0

### Timeline and timestamp editing
- Replaced the continuous date-time x-axis with a 24-hour time-of-day axis and one row per calendar day.
- Added wheel zoom, Shift+wheel horizontal pan, drag-to-zoom, and reset-to-24-hours. Removed position/zoom sliders.
- Added timestamp editing for time, location, unit alias, subject, and material.

### Record editing and audit trail
- Added record editing for times, Active/Passive, subject/material, learning position/unit, planned/actual range, and notes.
- Writes a before/after snapshot for record, timestamp, and actual-range edits to `viewer_edit_history`.
- Added database triggers to reject UPDATE and DELETE of audit rows. This is an application/database-level guard, not cryptographic protection against a person who can alter the SQLite file or drop triggers.
- Relinks timestamp records when a segment start time changes.

### Charts and filters
- Added subject and unit-alias selectors to trend charts, plus line/bar display toggles.
- Added wheel zoom and Shift+wheel pan to the hourly study-rate chart, with the unit label retained.
- Increased trend-chart height and axis margins.
- Added active/passive row coloring and a right-side session-duration bar.
- Added period choices Today, This Week, and Custom, with editable start/end dates connected to preset ranges.
- Added back/forward navigation for previously visited tabs and version labels in the header/footer.

### Packaging
- Synchronized package directory and imports as `viewer_v0`, matching `main.py`, tests, and the console entry point.
- Bumped application/package version to 0.8.0.
