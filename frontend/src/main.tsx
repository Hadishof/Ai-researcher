// Entry point: loads fonts and styles, then draws <App /> inside <div id="root"> (index.html).

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Self-hosted fonts: the font files are bundled with the app, no external CDN.
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans-hebrew/400.css";
import "@fontsource/ibm-plex-sans-hebrew/500.css";
import "@fontsource/ibm-plex-sans-hebrew/600.css";
import "@fontsource/ibm-plex-mono/400.css";

import "./styles/tokens.css";
import "./styles/app.css";

import App from "./App";

createRoot(document.getElementById("root")!).render(
  // StrictMode: extra checks while developing (it has no effect in the built app).
  <StrictMode>
    <App />
  </StrictMode>,
);
