# Task 2: Frontend (screens): complete guide

**Branch:** `feature/frontend-ui`
**You own:** `frontend/`, `tests/e2e/`.
**Don't edit:** `backend/`, `ml/`.
**Stack (team decision):** React + Vite + plain JavaScript (JSX) + plain CSS, with `react-router-dom`.
Don't add TypeScript, Tailwind or a UI component library.

This file covers your work **until the project is finished**. Work through the milestones in order.
If something is unclear or blocked, tell the team lead; don't guess.

---

## 0. What you're building

A **clean, white, enterprise-style dashboard** where an inspector:

```text
Dashboard ─► Cabinet page ─► Parts list (expected BOM) ─► New inspection ─► Results ─► Review
    │              │                                                          │
    │              └─► History (quality passport) + QR code                   └─► Report / CSV export
    └─► Analytics
```

The screens contain **no inspection logic**. They send data to the backend, show what comes back, and
send review decisions. All data shapes are in **`docs/contracts.md` (version 0.2)**.

## 1. What already exists

| File | Does |
|---|---|
| `src/api.js` | Every backend call; turns backend errors into readable messages |
| `src/components/Layout.jsx` | Header, navigation, footer |
| `src/components/ImageWithBoxes.jsx` | Draws boxes on a photo. Converts original-photo pixels to percentages so boxes stay in place at any size |
| `src/components/SyntheticBanner.jsx` | Purple "SYNTHETIC DATA" banner |
| `src/pages/Dashboard.jsx` | Backend and model status, cabinet list |
| `src/pages/NewInspection.jsx` | Picks the drawing and photos, uploads them |
| `src/pages/Results.jsx` | Photo + boxes, findings table, status filter, review form |
| `src/pages/CabinetHistory.jsx` | History list |
| `src/mocks/inspection.synthetic.json` | Fake data, only at `/inspections/synthetic` |

Run it: `cd frontend && npm install && npm run dev`, then open http://localhost:5173/inspections/synthetic.

## 2. Ground rules for every screen

- **All backend calls go through `src/api.js`.**
- **Every page has 3 states:** loading ("Loading…"), error (show the backend's `detail` message), and
  empty ("No inspections yet"). A blank page is a bug.
- **Box coordinates are original-photo pixels** `[x_min, y_min, x_max, y_max]`. Convert when drawing
  and when the user draws:
  ```js
  // screen → original, e.g. after the user drags a box on an <img> shown 800 px wide
  const scale = image.width / imgElement.clientWidth;   // image.width = original, e.g. 4096
  const bbox = [r.x * scale, r.y * scale, (r.x + r.w) * scale, (r.y + r.h) * scale];
  ```
- **Status styles: always the same everywhere.** Colour plus line style plus text label, so the meaning
  doesn't depend on colour alone:

  | Status | Look | Label |
  |---|---|---|
  | `verified` | green, solid | Verified |
  | `potential_mismatch` | red, solid | Potential mismatch |
  | `needs_review` | amber, dashed | Needs review |
  | `inconclusive` | grey, dotted | Inconclusive (not seen) |
  | `order_changed` (arrangement) | blue, dashed | Order changed: review |
  | `confirmed_by_reviewer` / `rejected_by_reviewer` | reviewer colour + ✓ / ✗ | Confirmed / Rejected |

  **Never show `inconclusive` as "missing" or in red.**
- **If an endpoint doesn't exist yet:** build against a file in `src/mocks/` named `*.synthetic.json`,
  copied exactly from `docs/contracts.md`, and show the purple banner while it's used.

---

## Milestone 1: White theme + core flow (must have, do first)

### 1.1 Switch to the white enterprise theme
Replace the dark colours in `src/styles.css` with variables in one place (`:root`):

```css
:root {
  --bg: #f6f7f9;  --surface: #ffffff;  --border: #e3e6eb;
  --text: #1c2430; --muted: #66717f;   --primary: #1f5eff;
  --ok: #1a7f37;   --bad: #cf222e;     --warn: #b26b00;  --info: #0969da;  --idle: #6e7781;
}
```

- Cards: white, 1 px border, 8 px radius, light shadow.
- Left sidebar navigation with: Dashboard, Cabinets, New inspection, Analytics.
- Use one font for the whole app (system font stack). Numbers in tables right-aligned.

**Check:** every existing page looks right in the white theme, at 1280 px and at 390 px width.

### 1.2 Cabinets and parts list
1. **Dashboard**: "New cabinet" form (id + name → `POST /api/cabinets`). Cabinet table with its latest
   status.
2. **Cabinet page** (`/cabinets/:id`): design revisions; "Upload drawing" (label + PDF →
   `POST /api/cabinets/{id}/design-revisions`); latest inspections.
3. **Parts list editor** (`/revisions/:id/parts`): an editable table with these columns. It loads via
   `GET` and saves via `POST /api/design-revisions/{id}/expected-items` (contract A):

   | Tag | Type | Part number | Description | Qty | Rating | Rating unsure? | Group | Position | Direction |
   |---|---|---|---|---|---|---|---|---|---|

   - **Type** is a dropdown: mcb, isolator, power_supply, redundancy_module, io_module, controller, terminal_block, other.
   - **Direction** is a dropdown: top_to_bottom, left_to_right.
   - "Paste from spreadsheet" button: tab-separated rows go straight into the table.
   - Validation: tag required and unique; position must be a whole number.

### 1.3 Run an inspection
1. **New inspection** (`/cabinets/:id/inspect`): choose the revision, pick 1–10 photos →
   `POST /api/cabinets/{id}/inspections`. Show each photo's upload result.
2. **Manual boxes**: on each photo, the user drags a rectangle, picks the kind (tag label / component)
   and types the tag (e.g. `CB11`) → contract B with `"source": "manual"` →
   `POST /api/inspections/{id}/observations`.
   - Zoom and pan the photo: labels are small on a 4096 px photo.
   - Edit and delete a box before saving.
   - **Check:** draw a box, reload the page; it reappears in the same place.
3. **Run** → `POST /api/inspections/{id}/run`, then `GET /api/inspections/{id}` every 2 s until
   `state` is `done` or `failed`. Show progress. Stop asking when the user leaves the page (clear the timer
   in `useEffect` cleanup).

### 1.4 Results (connect to the real endpoint)
- **Summary bar** from `counts` and `overall_status`, e.g.
  "Review required · 10 verified · 1 potential mismatch · 3 need review · 2 inconclusive".
- **Photo panel**: boxes from `findings[].evidence`. Clicking a box selects its row, and clicking a
  row highlights its box.
- **Findings table**: Tag, Type, Status, Expected, Read, OCR confidence, Sources. Filter by status and
  type, and sort by any column.
- **Photo-quality warnings** in plain words: `low_sharpness` → "This photo may be too blurry to read labels";
  `low_resolution` → "Photo resolution is low"; `overexposed` → "Glare may hide labels".

**Check:** full flow in the browser: new cabinet → parts list → photos → manual boxes → run → results.

---

## Milestone 2: Selected features (high priority)

### 2.1 Human review
- Review panel for the selected finding: reviewer name, note, Confirm / Reject →
  `POST /api/findings/{id}/review`.
- Show the history under it: "Confirmed by Archita · 24 Oct 10:42 · 'label shows 16 A'".
- A "Next item to review" button jumps to the next `needs_review` / `potential_mismatch` finding.

### 2.2 Arrangement / order view
A separate **Arrangement** section on the results page, one card per group from `arrangement[]`:

```text
Left breaker rail (top → bottom)                         Order changed: review required
Expected:  CB11  CB12  CB13  CB14  CB15  CB16
Found:     CB11  CB12 [CB14][CB13] CB15  CB16      ← out-of-order tags highlighted
```

- `matches` → green "Arrangement matches".
- `order_changed` → blue "Order changed: review required". **Not** red: an order change is not a defect by itself.
- `not_enough_evidence` → grey "Not enough tags read to check the order".

### 2.3 Visual highlighting polish
- Toggle layers: tag labels, components, findings only.
- Hover a box to show a tooltip with tag, type, status and sources.

### 2.4 History and reinspection
- **Cabinet history** (`/cabinets/:id/history`, contract via `quality-passport`): a timeline of
  inspections; reinspections linked to the one before; each shows its overall status and counts.
- **"Inspect again"** button on results → reinspection endpoint → go to the new inspection. Resolved
  items show "Resolved after reinspection".

### 2.5 Report and export
- **Download report** → opens `GET /api/inspections/{id}/report` in a new tab.
- **Export CSV** → downloads `export.csv`.
- Print styles (`@media print`): hide navigation, keep the photo and table, so the browser's
  "Save as PDF" gives a clean report.

---

## Milestone 3: Extras (medium priority, after M1–M2 work end to end)

### 3.1 Analytics page (`/analytics`)
From `GET /api/analytics` (contract D):

- KPI cards: inspections, pass, review required, mismatch detected.
- Bar chart: findings by type. A simple chart made of `<div>` bars in CSS is fine, so no chart library is needed.
- Table: most-flagged tags.
- Review outcomes: confirmed / rejected / pending.
- Date range filter.

### 3.2 QR traceability
- The cabinet page shows the QR image from `GET /api/cabinets/{id}/qr` with a **Print label** button
  (prints only the QR, cabinet id and name).
- Scanning the QR with a phone opens `/cabinets/{id}`. Check that the page works at phone width.

### 3.3 Dashboard
- Recent inspections table with status badges, filters by status and cabinet.
- "Needs review" counter that links to the next unreviewed item.

---

## Milestone 4: ML integration (when models are connected)

- **Source badges** on each finding: `OCR`, `Detector`, `Zero-shot`, `Manual`, plus the `evidence_score`
  as a small bar, e.g. "3 sources agree".
- Model status on the dashboard from `GET /api/model/status`: available / not available + reason.
- Manual boxes stay available as a fallback and for corrections.

## Milestone 5: Demo hardening

- Remove the synthetic link from normal navigation (keep the route for development).
- **Playwright smoke test** (`tests/e2e/smoke.spec.js`): open the dashboard, open results, click a
  finding and check its box is highlighted, and open the arrangement section.
- Check every page at 1280 px and 390 px width: no sideways scrolling.
- Keyboard: Tab reaches every button; Enter submits forms.
- `npm run build` passes in CI.

---

## Done when

- [ ] White enterprise theme on every page.
- [ ] Full flow works in the browser on real backend data: cabinet → parts list → photos → boxes → run →
      results → arrangement → review → reinspection → history → report/CSV.
- [ ] Analytics and QR pages work (M3).
- [ ] No fake data reachable from normal navigation.
- [ ] Smoke test and build pass in CI.

## Working with the others

- **Backend (Task 1)** provides every endpoint. If one is missing or its response differs from
  `docs/contracts.md`, report it to them; don't work around it in the screens.
- **Engine (Task 3)** decides statuses and the arrangement result. The screens only display them.
- Merge `develop` into your branch daily: `git pull origin develop`. Open a pull request into `develop`
  at the end of each milestone, with a screenshot of each new screen.
