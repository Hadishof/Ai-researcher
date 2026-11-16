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

## Phase 3: React + TypeScript frontend

**Goal:** Replace Streamlit with a real web app built with React and
TypeScript (using Vite), with a chat, an upload panel and a sources list.

- [ ] Create the app in a `frontend/` folder with Vite
- [ ] Chat window: send questions, show answers, keep the conversation on screen
- [ ] Correct right-to-left display for Hebrew messages
- [ ] Upload panel: pick a PDF, upload it, show progress and errors
- [ ] List of uploaded documents, each with a delete button and a confirmation step
- [ ] Sources list under each answer (file name and page)
- [ ] Shared TypeScript types matching the backend's responses
- [ ] Backend address set in one config place, not hard-coded

## Phase 4: Evaluation harness

**Goal:** Measure how good the system's answers really are, instead of
guessing, using a fixed set of questions with known answers.

- [ ] Create an `eval/` folder
- [ ] Pick one or more sample PDFs that can be shared publicly
- [ ] Write about 30 questions (Hebrew and English) with the correct answer and the page it comes from
- [ ] Script that checks retrieval accuracy: did the search find the right page?
- [ ] Script that checks answer faithfulness: does the answer stick to the document and not make things up?
- [ ] Save the results to a file so runs can be compared over time
- [ ] Use the results to tune chunk size, number of retrieved chunks and the relevance limit (`MAX_DISTANCE`)
- [ ] Benchmark our custom chunker against LangChain's RecursiveCharacterTextSplitter on the evaluation set (LangChain is used only inside `eval/`, never in the backend)

## Phase 5: Docker + docker-compose + GitHub Actions CI

**Goal:** Make the whole project start with one command on any computer, and
run the tests automatically on GitHub after every push.

- [ ] `Dockerfile` for the backend
- [ ] `Dockerfile` for the frontend
- [ ] `docker-compose.yml` that starts both together, with the database saved between restarts
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
