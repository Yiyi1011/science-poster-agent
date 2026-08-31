import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import StoryboardEditor from "./StoryboardEditor";
import Studio from "./Studio";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {new URLSearchParams(window.location.search).get("view") === "storyboard" ? <StoryboardEditor /> : new URLSearchParams(window.location.search).get("view") === "legacy" ? <App /> : <Studio />}
  </React.StrictMode>,
);
