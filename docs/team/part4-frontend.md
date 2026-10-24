# Part 4 — Frontend: upload, results, review, history

Branch: `feature/frontend-ui` · Folder: `frontend/` · Consumes: contract C

**Goal:** the screens an inspector uses: create a cabinet, upload the drawing and photos, see findings
drawn on the photo, review them, and see the history.

Stack stays React + Vite + JSX + plain CSS (agreed: no TypeScript or Tailwind migration). Add
`react-router-dom` for multiple screens.

## Tasks

- [ ] 1. Add `frontend/vite.config.js` with `@vitejs/plugin-react`. Without it the page crashes with
      "React is not defined" (found in the prototype).
- [ ] 2. `src/api.js`: one place for all calls; base URL from `VITE_API_URL`. Show the backend's error
      message to the user instead of failing silently.
- [ ] 3. Screens:
      - Dashboard: list of cabinets and latest inspection status.
      - New inspection: pick cabinet, upload drawing and photos, show progress while it runs.
      - Results: photo with boxes from `evidence[].bbox`, scaled to the displayed size; colour by status;
        findings table beside it; filter by status.
      - Review: confirm or reject a finding with a note; show the decision history.
      - Cabinet history (quality passport): all inspections and reinspections in order.
- [ ] 4. Show uncertainty clearly: `needs_review` and `inconclusive` must look different from `verified`
      and from `potential_mismatch`.
- [ ] 5. Until Part 3's endpoints exist, use a local file `src/mocks/inspection.synthetic.json` in contract C
      format, with a visible "SYNTHETIC DATA" banner when it is used. Remove before the demo.
- [ ] 6. Browser smoke test (`tests/e2e/`, Playwright): open the app, upload a file, reach the results screen.
- [ ] 7. Check it works at laptop and phone width.

## Done when

- Results from a real backend run are shown with correctly placed boxes.
- `npm run build` passes and the smoke test passes.
