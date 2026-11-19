# Roadmap: AI Researcher v2

This rebuild happens in six phases, one at a time, on the `v2` branch.
Each phase ends with a commit and an explanation of every new file.
When all phases are done, `v2` is merged into `main`.

---

## Phase 1: Backend restructure + fixes

**Goal:** Turn the single `main.py` into a clean, organized backend that is
easy to read, test and explain, and fix the problems in the current version.

- [x] Split `main.py` into a `backend/app/` package (core, api/routes, schemas, services, db)
- [x] Settings in one place with `pydantic-settings`; clear error if `GOOGLE_API_KEY` is missing
- [x] Replace the deprecated `google-generativeai` SDK with `google-genai`
- [x] Remove LangChain: call ChromaDB, Gemini and `pypdf` directly
- [x] Gemini embeddings for both storing and searching; ChromaDB never creates its own
- [x] Custom chunker: paragraphs first, then sentences, cut mid-text only as a last resort, with overlap (works with Hebrew)
- [x] ChromaDB collection uses cosine distance
- [x] Page-number citations with every answer
- [x] "I couldn't find this in the documents" when no chunk is relevant enough
- [x] Duplicate uploads blocked using the file's SHA-256 hash, which is also the document id
- [x] Proper HTTP status codes with `HTTPException`
- [x] Uploads are read in memory; the uploaded filename is never used as a file path
- [x] Pydantic models for every request and response
- [x] Wait and retry when Gemini's free-tier rate limit is reached
- [x] CORS allows only the frontend address from settings
- [x] Routes: `POST /documents`, `GET /documents`, `DELETE /documents/{id}`, `POST /chat`, `GET /health`
- [x] `requirements.txt` trimmed to the packages actually used
- [x] `.env.example` showing which settings are needed
- [x] Remove `app.py` (Streamlit), to be replaced in Phase 3

## Phase 2: Backend tests (pytest, LLM mocked)

**Goal:** Prove the backend works with automatic tests that run fast, cost
nothing, and never call the real Gemini API.

- [x] Set up `pytest` and a `tests/` folder
- [x] Replace Gemini with a fake ("mock") in tests so results are predictable
- [x] Use a temporary database folder so tests never touch real data
- [x] Build small test PDFs inside the tests, including a Hebrew page
- [x] Test text chunking on its own (paragraphs, sentences, long sentences, overlap, Hebrew)
- [x] Test PDF upload: success, duplicate, wrong file type, empty file, too large
- [x] Test listing and deleting documents
- [x] Test asking a question: answer and page sources are returned
- [x] Test "not found": nothing relevant, or no documents uploaded yet (the LLM is not called)
- [x] Test the relevance filters and that only the excerpts the LLM used become sources
- [x] Test Gemini failures: rate limit (429, with retries) and other errors (502)
- [x] All tests pass with one command: `pytest`

### How to run tests

From the `backend/` folder, with the virtual environment active:

```
pip install -r requirements-dev.txt
pytest
```

To also see which lines of code the tests run (coverage):

```
pytest --cov=app --cov-report=term-missing
```

The tests need no API key and no internet: Gemini is replaced by a fake, and
each test uses its own empty database in a temporary folder.

## Phase 3: Saved conversations + React frontend

**Goal:** Save chats so they can be reopened and continued days later, then
replace Streamlit with a real web app built with React and TypeScript (using
Vite). Phase 3 has two steps; 3a is built and tested before 3b starts.

### Step 3a: Backend support for saved conversations

- [x] SQLite database (Python's built-in `sqlite3`, plain SQL, no ORM) in `backend/data/`, path in settings, ignored by git
- [x] Tables `conversations` and `messages`; deleting a conversation deletes its messages (`ON DELETE CASCADE`)
- [x] All SQL in one repository file: `app/db/conversation_store.py`; tables created automatically
- [x] Routes: `POST /conversations`, `GET /conversations`, `GET /conversations/{id}`, `PATCH /conversations/{id}`, `DELETE /conversations/{id}`, `DELETE /conversations`
- [x] `POST /chat` requires a `conversation_id` and saves the question and the answer (with sources)
- [x] Title set automatically from the first question; can be renamed
- [x] Follow-up questions: Gemini rewrites them into a standalone question (using the last few messages) before searching
- [x] Each conversation chooses its own documents (table `conversation_documents`), so information from different documents never mixes between chats
- [x] `POST /conversations` accepts the first documents; `PUT /conversations/{id}/documents` replaces the selection
- [x] `/chat` searches only the conversation's documents (ChromaDB metadata filter); no documents selected gives a clear 400
- [x] When the selected documents disagree, the answer says so and states what each document says
- [x] Documents stay in one shared library; deleting chats never deletes documents
- [x] `GET /documents` shows how many conversations have each document selected
- [x] Deleting a document removes it from every conversation; old answers keep their sources, marked as "deleted"
- [x] A duplicate upload (409) also returns the existing document's id and filename
- [x] Tests for the store, every new route, cascade delete, delete-all, the rewrite step, per-chat documents and deleted-document sources

### Step 3b: React + TypeScript frontend

- [x] Create the app in a `frontend/` folder with Vite
- [x] Sidebar: new chat, list of saved chats, rename, delete (with confirmation), delete all (with confirmation)
- [x] Chat area: full history of the open chat, a distinct "not found" style, sources as small chips under each answer
- [x] The chat's documents as chips at the top, with a checkbox list to add or remove documents
- [x] A new chat asks to select or upload documents first; a PDF uploaded while a chat is open is added to it (also when it was already in the library)
- [x] Enter sends, Shift+Enter adds a new line, auto-scroll to the newest message
- [x] Correct right-to-left display for Hebrew messages
- [x] Documents panel: upload a PDF with clear error messages, list documents, delete with a warning when chats use the document
- [x] Light and dark mode: follows the system, can be switched, the choice is remembered
- [x] Calm, precise design: one accent color, IBM Plex fonts (self-hosted), colors as CSS variables, WCAG AA contrast
- [x] All backend calls in one file, with TypeScript types matching the backend's responses
- [x] Backend address from `VITE_API_URL`, not hard-coded
- [x] Frontend tests with Vitest and React Testing Library (backend mocked)

## Phase 4: Evaluation harness

**Goal:** Measure how good the system's answers really are, instead of
guessing, using a fixed set of questions with known answers.

Phase 4 has three steps, each built and checked before the next starts.

### Step 4a: Dataset, dev/test split and metrics (no Gemini)

- [x] Create an `eval/` folder
- [x] Five synthetic sample PDFs that can be shared publicly, committed in `eval/data/`
- [x] 59 questions (Hebrew and English) with the expected facts and the pages they come from, in `eval/data/dataset.jsonl`
- [x] Question types: factual, distractor, cross-lingual, not found, follow-up, and conflict (two documents disagree, so the answer must report both instead of mixing them)
- [x] Every row is validated when loaded (field names, types, and rules that connect fields)
- [x] Fixed, stratified dev/test split (40 dev / 19 test, by question type and language) in `eval/data/split.json`: settings are tuned only on dev, and test is used only for the final numbers
- [x] Metric functions: Hit@1/3/5 and MRR by (file, page), pages found for conflicts, fact matching (case-insensitive, ignoring thousands separators), breakdown by language and type
- [x] Tests for the metrics, the dataset loader and the split

### Step 4b: Retrieval experiments (embeddings only, no answers generated)

- [x] The relevance filters (`filter_results`) and the answer step (`answer_from_chunks`) are separate backend functions, so the evaluation runs the app's own code
- [x] Disk cache for embeddings, so re-runs do not call Gemini again
- [x] Separate temporary ChromaDB for evaluation, never the real data
- [x] Exact number of Gemini calls printed before a run (`--dry-run`); run only some experiments or questions; pause between requests
- [x] Chunk size 500 / 1000 / 1500 (same overlap ratio)
- [x] `MAX_DISTANCE` sweep: correct pages lost vs "not found" questions correctly blocked
- [x] Relative margin sweep
- [x] Benchmark our custom chunker against LangChain's RecursiveCharacterTextSplitter at each size (LangChain is used only inside `eval/`, never in the backend)
- [x] Results in `eval/results/` (JSON with every detail, and a markdown summary)

### Step 4c: Full run with answers

- [ ] One full run with the best settings from the dev set, including follow-up rewriting
- [ ] Answer correctness against the expected facts (an LLM judge for faithfulness, i.e. whether the answer adds made-up claims, is left for later)
- [ ] "Not found" accuracy, conflict handling and follow-up handling
- [ ] Results saved to a JSON file and a markdown summary, with every failed question listed; test set as the headline numbers

### How to run the evaluation

From the `eval/` folder, with the virtual environment active:

```
pip install -r requirements-eval.txt
pytest                                          # metric tests, no API key needed
python run_eval.py retrieval --dry-run          # how many Gemini calls a run needs
python run_eval.py retrieval --pace 60          # retrieval experiments on the dev set
```

Embeddings are cached in `eval/.cache/`, so running the experiments again
costs no Gemini calls. `--experiments`, `--chunk-sizes`, `--ids` and `--limit`
run only part of the experiments or questions.

The split is created once with `python split.py` and then never changes
(the script refuses to overwrite a different split).

## Phase 5: Docker + docker-compose + GitHub Actions CI

**Goal:** Make the whole project start with one command on any computer, and
run the tests automatically on GitHub after every push.

- [ ] `Dockerfile` for the backend
- [ ] `Dockerfile` for the frontend
- [ ] `docker-compose.yml` that starts both together, with both databases (ChromaDB and SQLite) saved between restarts
- [ ] API key passed in through environment variables, never built into the image
- [ ] GitHub Actions workflow that runs the backend tests on every push and pull request
- [ ] The same workflow checks that the frontend builds
- [ ] Test status badge ready for the README

## Phase 6: Professional README, then deploy

**Goal:** Write a README that anyone can understand, then put the app online
so people can try it.

- [ ] Plain, simple language that a non-technical reader can follow
- [ ] Straight to the point: short sections, no filler
- [ ] No emojis
- [ ] Few numbers; describe results in words that are easy to understand
- [ ] Short explanation of what the project does and why it is useful
- [ ] Architecture diagram showing how the pieces connect
- [ ] Evaluation results from Phase 4, explained simply
- [ ] Clear steps to run it locally (with and without Docker)
- [ ] Screenshot of the app
- [ ] Deploy the backend and frontend to a hosting service
- [ ] Add the live link to the README
- [ ] Merge `v2` into `main` through a pull request
