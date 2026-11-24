import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/global.css";
import { Bootstrap } from "./app/Bootstrap";
import { initializeDesign } from "./design/useDesign";
import { initializeDesignLab } from "./design-lab/useDesignLab";
import { initializeTheme } from "./hooks/useTheme";

initializeDesign();
initializeDesignLab();
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
