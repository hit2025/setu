import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Spinner, ToastProvider } from "./components/ui";
import { Cases } from "./pages/Cases";
import { Handover } from "./pages/Handover";
import { Login } from "./pages/Login";
import { Policy } from "./pages/Policy";
import { Workspace } from "./pages/Workspace";
import "./styles.css";

function Routed() {
  const { user, ready } = useAuth();
  if (!ready) return <div style={{ display: "grid", placeItems: "center", height: "100vh" }}><Spinner size={24} /></div>;
  if (!user) return <Login />;
  return (
    <Routes>
      <Route path="/" element={<Cases />} />
      <Route path="/cases/:id" element={user.role === "engineer" || user.role === "coordinator" ? <RedirectToHandover /> : <Workspace />} />
      <Route path="/handover/:id" element={<Handover />} />
      <Route path="/policy" element={<Policy />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function RedirectToHandover() {
  const id = window.location.pathname.split("/").pop();
  return <Navigate to={`/handover/${id}`} replace />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <Routed />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
