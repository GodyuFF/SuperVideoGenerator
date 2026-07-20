/** React 应用入口 */

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import "./styles/design-system.css";
import "./styles/asset-detail.css";
import "./styles/resizable-drawer.css";
import "./styles/editor-studio.css";
import "./styles/splash-screen.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
