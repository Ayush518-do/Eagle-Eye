# Frontend (Part 4)

React + Vite + JSX + plain CSS. Task list: [`../docs/team/part4-frontend.md`](../docs/team/part4-frontend.md).

```text
frontend/src/
├── App.jsx                      # routes
├── api.js                       # every backend call; shows backend error messages
├── components/
│   ├── Layout.jsx               # header, nav, footer
│   ├── ImageWithBoxes.jsx       # draws finding boxes on a photo (scales from original pixels)
│   └── SyntheticBanner.jsx
├── pages/
│   ├── Dashboard.jsx            # backend + model status, cabinet list
│   ├── NewInspection.jsx        # upload drawing + photos to POST /api/uploads
│   ├── Results.jsx              # photo with boxes, findings table, filter, review panel
│   └── CabinetHistory.jsx       # quality passport
└── mocks/inspection.synthetic.json   # UI-only sample, shown with a SYNTHETIC banner
```

```bash
npm install
npm run dev        # http://localhost:5173
npm run build
```

Routes: `/`, `/inspect`, `/inspections/:id` (`/inspections/synthetic` = sample), `/cabinets/:id`.

Cabinet list, inspection, review and passport screens call endpoints Part 3 has not built yet;
they show the backend's error until then.
