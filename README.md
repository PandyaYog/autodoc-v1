# AutoDoc — AI-Powered Code Documentation Generator

AutoDoc is a full-stack web application that automatically generates professional PDF documentation for any codebase. Upload a ZIP of your project, and AutoDoc uses a **Code Knowledge Graph (CKG)** combined with **Google Gemini AI** to produce structured, human-readable documentation — ready to download in minutes.

---

## What It Does

- 📂 **Parses your entire codebase** — Python, JavaScript, TypeScript, React, Next.js, HTML, CSS, JSON, YAML, and more
- 🔗 **Builds a Code Knowledge Graph** — maps functions, classes, imports, and dependencies across all files
- 🧠 **AI-Powered Summarization** — uses Gemini LLM to write precise, context-aware descriptions for every code node
- 📄 **Generates a PDF** — professionally formatted, download-ready documentation in one click
- ⚡ **Async pipeline** — non-blocking background task system with real-time status polling
- 🌗 **Dark / Light mode** — smooth theme switching with localStorage persistence

---

## Project Structure

```
autodoc-ai/
├── autodoc/               # FastAPI backend
│   ├── api/               # Route handlers (generate, status, download)
│   ├── core/              # CKG builder, traversal, AI summarizer, PDF renderer
│   ├── models/            # Pydantic request/response models
│   ├── services/          # Task store, pipeline runner
│   └── main.py            # App entry point with CORS & middleware
├── frontend/              # React + Vite frontend
│   ├── src/
│   │   ├── components/    # Shared UI (Navbar, Button, Toast, DropZone, PDFPreview)
│   │   ├── context/       # ThemeContext, ToastContext
│   │   ├── pages/         # LandingPage, UploadPage, ProcessingPage, ResultsPage, ErrorPage
│   │   ├── services/      # axios API layer
│   │   └── config/        # API endpoints, PDF.js worker config
│   └── ...
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Prerequisites

- Python **3.10+**
- Node.js **18+** and npm
- A **Google Gemini API key** — get one free at [aistudio.google.com](https://aistudio.google.com)

---

## Running the Backend

### Option 1 — Python (Local Development)

```bash
# 1. Clone the repo
git clone https://github.com/PandyaYog/autodoc-v1.git
cd autodoc-v1

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create the environment file
cp .env.example .env            
```

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

```bash
# 5. Start the backend
uvicorn autodoc.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive API docs: `http://localhost:8000/docs`

---

### Option 2 — Docker

```bash
# 1. Build the image
docker build -t autodoc-ai .

# 2. Run the container 
docker run -p 8000:8000 -e GEMINI_API_KEY=your_gemini_api_key_here autodoc-ai
```

The backend will be live at `http://localhost:8000`.

---

## Running the Frontend

```bash
# From the project root
cd frontend

# Install dependencies 
npm install

# Create the frontend environment file
echo "VITE_API_BASE_URL=http://localhost:8000" > .env

# Start the dev server
npm run dev
```

The app will open at `http://localhost:5173`.

> **Note:** Both the backend and frontend must be running at the same time for the full pipeline to work.

---

## How to Use

1. **Open** `http://localhost:5173` in your browser
2. **Click** "Upload Your Project" or "Try It Free"
3. **Drag & drop** (or click to browse) your project ZIP file — max 100 MB
4. **Click** "Generate Documentation" and wait while AutoDoc analyzes your code
5. **Download** the generated PDF from the Results page

> Complex projects with many files may take 3–5 minutes. Keep the tab open while processing.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/generate` | Upload a ZIP and start the documentation pipeline |
| `GET` | `/api/v1/status/{task_id}` | Poll task status (`pending` / `processing` / `completed` / `failed`) |
| `GET` | `/api/v1/download/{task_id}` | Download the generated PDF |
| `GET` | `/health` | Health check |

Full interactive docs available at `http://localhost:8000/docs` when the server is running.

---

## Environment Variables

### Backend (`.env` in project root)

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | ✅ Yes | Your Google Gemini API key |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |
| `MAX_UPLOAD_SIZE_MB` | No | Max ZIP upload size in MB (default: `100`) |

### Frontend (`frontend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_BASE_URL` | ✅ Yes | Backend URL (default: `http://localhost:8000`) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python, FastAPI, Uvicorn |
| **AI** | Google Gemini (via `google-genai`) |
| **PDF Generation** | WeasyPrint |
| **Code Parsing** | Tree-sitter |
| **Frontend** | React 19, Vite |
| **PDF Preview** | react-pdf / pdf.js |
| **HTTP Client** | axios |
| **Icons** | lucide-react |
| **Containerization** | Docker |

---

## Contributing

Contributions are welcome and encouraged! If you have ideas, bug reports, or want to add support for more languages or output formats, feel free to open an issue or submit a pull request.

```bash
# Fork the repo, then:
git checkout -b feature/your-feature-name
# ... make your changes ...
git commit -m "feat: describe your change"
git push origin feature/your-feature-name
# Open a Pull Request on GitHub
```

Please keep PRs focused and include a clear description of what was changed and why.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
