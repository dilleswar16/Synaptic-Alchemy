import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/global.css";
import { Bootstrap } from "./app/Bootstrap";
import { initializeBackdrop } from "./hooks/useBackdrop";
import { initializeDesign } from "./hooks/useDesign";
import { initializeTheme } from "./hooks/useTheme";

initializeBackdrop();
initializeDesign();
initializeTheme();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Missing #root element in index.html");
}

createRoot(rootElement).render(
  <StrictMode>
    <Bootstrap />
  </StrictMode>,
);
