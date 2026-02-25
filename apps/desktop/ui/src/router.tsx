import React from "react";
import { createBrowserRouter } from "react-router-dom";
import { App } from "./routes/App";
import { Overlay } from "./routes/Overlay";

export const router = createBrowserRouter([
  { path: "/app", element: <App /> },
  { path: "/overlay", element: <Overlay /> },
  { path: "*", element: <App /> },
]);
