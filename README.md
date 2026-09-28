# AGNITI Web IDE — first web build

This is a separate web interface. It does not edit the existing AGNITI compiler source files.

## Contents

- `index.html`, `style.css`, `app.js`: browser IDE
- `manifest.json`, `service-worker.js`: installable/offline-shell groundwork
- `compiler/lexer.py`, `compiler/parser.py`, `compiler/code_generator.py`: compiler source copies used by the browser IDE

The Python compiler files were copied into this folder; the web app does not write back to the original project.

## Run locally

Because browsers restrict loading local Python files from `file://`, start a local static server from this folder:

```powershell
python -m http.server 8000
```

Then open `http://localhost:8000`.

The first load needs internet access to download Pyodide from its CDN. After loading, the AGNITI pipeline runs inside the browser's Python/WebAssembly runtime. Program output and generated Python appear in separate panels.

## Important limitations in this preview

- The browser runtime is not the same as running `runner.py` as a subprocess on Windows. `input()` prompts, process execution, and some OS/file behaviours may differ.
- The browser's file system is isolated from your Windows project.
- Public hosting can serve this folder as a static site. To publish, upload the web folder to a public GitHub repository and connect it to GitHub Pages or Cloudflare Pages.
- Publicly shareable saved programs need a separate storage/backend feature; this preview only opens local files and downloads saved `.agn` files.
- The PWA/offline shell is groundwork; Pyodide's runtime assets still need to be cached deliberately for full offline execution.
