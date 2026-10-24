# Task 2: Frontend (screens)

**Branch:** `feature/frontend-ui` · **You own:** `frontend/` and `tests/e2e/`.
**Do not edit:** `backend/`, `ml/`.

Stack: React + Vite + plain JavaScript (JSX) + plain CSS, with `react-router-dom` for pages.
No TypeScript or Tailwind (team decision).

## What you are building

The screens an inspector uses. They don't contain inspection logic: they send files to the backend,
show what comes back, and send review decisions.

```text
Dashboard ──► Cabinet page ──► New inspection ──► Results ──► Review
   │                                                   ▲
   └───────────────► Inspection history (passport) ────┘
```

## What already works

| File | What it does |
|---|---|
| `src/api.js` | Every backend call in one place; turns backend errors into readable messages |
| `src/pages/Dashboard.jsx` | Backend and model status; cabinet list |
| `src/pages/NewInspection.jsx` | Picks the drawing and photos, uploads them to `POST /api/uploads` |
| `src/pages/Results.jsx` | Photo with coloured boxes, findings table, status filter, review form |
| `src/pages/CabinetHistory.jsx` | Inspection history for one cabinet |
| `src/components/ImageWithBoxes.jsx` | Draws boxes; converts original-photo pixels to percentages so boxes stay in place at any size |
| `src/mocks/inspection.synthetic.json` | Fake sample data; shown only at `/inspections/synthetic`, with a purple banner |

Run it: `cd frontend && npm install && npm run dev`, then open http://localhost:5173/inspections/synthetic.

## Step 1: Cabinet flow

Endpoints come from Task 1 ([`backend.md`](backend.md), table in Step 2).

1. **Dashboard:** add a "New cabinet" form (id + name → `POST /api/cabinets`). Show each cabinet
   with its latest status.
2. **Cabinet page** (`/cabinets/:id`): its design revisions, an "Upload drawing" form
   (label + PDF → `POST /api/cabinets/{id}/design-revisions`) and its inspection history.
3. **Expected parts editor:** a simple table (tag, part number, description, quantity, rating) to
   type the parts list by hand → `POST /api/design-revisions/{id}/expected-items`. This is how we
   test before the drawing parser exists.

## Step 2: Run an inspection

1. **New inspection** (`/cabinets/:id/inspect`): choose the design revision, pick 1–10 photos →
   `POST /api/cabinets/{id}/inspections`. Show each file's upload result, as `NewInspection.jsx`
   already does.
2. **Manual boxes:** on the photo, the user drags a rectangle and types the tag text (e.g. `CB11`).
   Send them as contract B with `"source": "manual"` → `POST /api/inspections/{id}/observations`.
   - Store boxes in **original-photo pixels**, not screen pixels:
     ```js
     // rect is the dragged box in screen pixels; img is the <img> element on screen
     const scale = image.width / img.clientWidth;            // image.width = original width
     const bbox = [rect.x * scale, rect.y * scale, (rect.x + rect.w) * scale, (rect.y + rect.h) * scale];
     ```
   - Test it: draw a box, reload the page and check it reappears in the same place.
3. **Run button** → `POST /api/inspections/{id}/run`, then ask `GET /api/inspections/{id}` every
   2 seconds until `state` is `done` or `failed`, and show progress meanwhile. Stop asking when the
   user leaves the page (clear the timer in the `useEffect` cleanup).

## Step 3: Results and review

`Results.jsx` already works with the fake data; connect it to the real endpoint and add:

- A summary bar from `counts`, e.g. "10 verified · 1 potential mismatch · 3 need review · 2 inconclusive".
- Photo-quality warnings (`images[].quality_flags`) in plain words, e.g. `low_sharpness` →
  "This photo may be too blurry to read labels".
- Clicking a row highlights its box, and clicking a box selects its row. This already works; keep it.
- The review form posts to `POST /api/findings/{id}/review`. Afterwards, show the new status and
  the history ("Confirmed by Archita, 10:42 — 'label shows 16 A'").
- An "Inspect again" button → reinspection endpoint, then go to the new results.

**Status display rules** (already in `styles.css`; keep them consistent):

| Status | Look | Why |
|---|---|---|
| `verified` | green, solid | matches the drawing |
| `potential_mismatch` | red, solid | something differs; a person must check |
| `needs_review` | yellow, dashed | read, but not sure |
| `inconclusive` | grey, dotted | not seen; **not** proof it is missing |

Never show `inconclusive` as "missing" or in red.

## Step 4: Polish and test

- Phone width (390 px): no sideways scrolling; the photo goes above the table.
- Loading and error states on every page. An empty page with no message is a bug.
- Browser smoke test in `tests/e2e/smoke.spec.js` with Playwright: open the dashboard, open the
  synthetic results, click a finding and check its box is highlighted.
- Remove the link to synthetic data before the demo (keep the route for development).

## Before the backend endpoints exist

Build against the fake JSON with the purple banner. For a new screen, add another file in
`src/mocks/` named `*.synthetic.json` that follows `docs/contracts.md` exactly. Then switching to the
real endpoint only changes the data source.

## Done when

- [ ] Full flow in the browser: new cabinet → expected parts → photos → manual boxes → run →
      results → review → history.
- [ ] Boxes line up with the photo at every window size.
- [ ] `npm run build` passes in CI; the smoke test passes.
- [ ] No fake data reachable from the normal navigation.

## Working with the others

- Need an endpoint or field that doesn't exist? Ask Task 1. Don't work around it in the frontend.
- If the backend's response doesn't match `docs/contracts.md`, report it. That's a bug on their side.
- Merge `develop` into your branch daily: `git pull origin develop`.
