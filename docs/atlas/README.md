# Simple Agent — Interactive Codebase Atlas

The diagrams, walkthroughs, and code excerpts describe the Git snapshot named
in the page header. See the project README for the current module layout.
The two atlas entry pages share the workspace tool simulator in
`read-file-policy.js`. The simulator uses a virtual `/workspace` and supplied
file metadata.

## Viewing Locally

Open `docs/atlas/index.html` directly in a browser, or serve it locally with Python:

```sh
python3 -m http.server 8000 --directory docs/atlas
```

Then visit `http://127.0.0.1:8000`.

## Structure

- `index.html` — Application shell and section navigation.
- `styles.css` — Dark/light theme tokens and layout styling.
- `data/excerpts.js` — Verbatim code excerpts and Git commit metadata extracted directly from repository source files.
- `data/architecture.js` — C4 Levels 1–4 architecture graph and searchable feature inventory.
- `data/walkthroughs.js` — End-to-end execution walkthroughs, sequence diagrams, call chains, state transitions, breakpoints, and failure scenarios.
- `data/tutorials.js` — Step-by-step tutorial for adding a new `@tool` (using a safe AST-based calculator example) with an interactive safety sandbox and collapsible reference implementation.
- `data/learning.js` — Progressive hands-on coding exercises (hints and solutions hidden by default) and comprehension quizzes.
- `app.js` — Interactive C4 inspector, search/filter engine, walkthrough stepper, 4 interactive logic simulators, and learning UI.
