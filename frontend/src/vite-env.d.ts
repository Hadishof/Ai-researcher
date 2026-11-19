/// <reference types="vite/client" />

// The settings this app reads from frontend/.env (only names starting with VITE_ reach the browser).
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
