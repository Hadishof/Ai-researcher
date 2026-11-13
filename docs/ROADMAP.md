# Roadmap: AI Researcher v2

This rebuild happens in six phases, one at a time, on the `v2` branch.
Each phase ends with a commit and an explanation of every new file.
When all phases are done, `v2` is merged into `main`.

---

## Phase 1: Backend restructure + fixes

**Goal:** Turn the single `main.py` into a clean, organized backend that is
easy to read, test and explain, and fix the problems in the current version.

- [ ] Split `main.py` into a small package (settings, API routes, PDF ingestion, retrieval, answer generation)
- [ ] Load settings (API key, model names, database folder) from one place, and fail with a clear message if the API key is missing
- [ ] Replace the deprecated `google-generativeai` SDK with `google-genai`
- [ ] Decide whether to keep LangChain or call ChromaDB and Gemini directly (simpler, fewer dependencies)
- [ ] Return proper HTTP error codes instead of `{"error": ...}` with status 200
- [ ] Save uploads to a safe temporary file instead of using the uploaded filename directly
- [ ] Accept only PDF files and reject empty or unreadable ones
- [ ] Avoid duplicate chunks when the same PDF is uploaded twice
- [ ] Return the sources (file name and page number) with every answer
- [ ] Ask questions with `POST` and a JSON body instead of a URL query string
- [ ] Fix the broken character in the Hebrew/English prompt
- [ ] Limit CORS to the frontend's address instead of allowing everything
- [ ] Trim `requirements.txt` to only the packages the project actually uses
- [ ] Add a `.env.example` file showing which settings are needed

## Phase 2: Backend tests (pytest, LLM mocked)

**Goal:** Prove the backend works with automatic tests that run fast, cost
nothing, and never call the real Gemini API.

- [ ] Set up `pytest` and a `tests/` folder
- [ ] Replace Gemini with a fake ("mock") in tests so results are predictable
- [ ] Test PDF upload: success, wrong file type, empty file
- [ ] Test asking a question: answer and sources are returned
- [ ] Test asking when no documents are uploaded yet
- [ ] Test clearing the knowledge base
- [ ] Test text chunking on its own
- [ ] Use a temporary database folder so tests never touch real data
- [ ] All tests pass with one command: `pytest`

## Phase 3: React + TypeScript frontend

**Goal:** Replace Streamlit with a real web app built with React and
TypeScript (using Vite), with a chat, an upload panel and a sources list.

- [ ] Create the app in a `frontend/` folder with Vite
- [ ] Chat window: send questions, show answers, keep the conversation on screen
- [ ] Correct right-to-left display for Hebrew messages
- [ ] Upload panel: pick a PDF, upload it, show progress and errors
- [ ] Button to clear the knowledge base, with a confirmation step
- [ ] Sources list under each answer (file name and page)
- [ ] Shared TypeScript types matching the backend's responses
- [ ] Backend address set in one config place, not hard-coded
- [ ] Remove `app.py` and Streamlit from the project

## Phase 4: Evaluation harness

**Goal:** Measure how good the system's answers really are, instead of
guessing, using a fixed set of questions with known answers.

- [ ] Create an `eval/` folder
- [ ] Pick one or more sample PDFs that can be shared publicly
- [ ] Write about 30 questions (Hebrew and English) with the correct answer and the page it comes from
- [ ] Script that checks retrieval accuracy: did the search find the right page?
- [ ] Script that checks answer faithfulness: does the answer stick to the document and not make things up?
- [ ] Save the results to a file so runs can be compared over time
- [ ] Use the results to tune chunk size and number of retrieved chunks

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
