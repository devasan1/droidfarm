import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import App from "./App";
import Phones from "./pages/Phones";
import Proxies from "./pages/Proxies";
import Apks from "./pages/Apks";
import Trash from "./pages/Trash";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<Navigate to="/phones" replace />} />
          <Route path="phones" element={<Phones />} />
          <Route path="proxies" element={<Proxies />} />
          <Route path="apks" element={<Apks />} />
          <Route path="trash" element={<Trash />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
