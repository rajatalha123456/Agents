import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import { AuthProvider } from "./context/AuthContext";
import Assets from "./pages/Assets";
import CashFlows from "./pages/CashFlows";
import Chat from "./pages/Chat";
import Dashboard from "./pages/Dashboard";
import ForecastDetail from "./pages/ForecastDetail";
import Login from "./pages/Login";
import Register from "./pages/Register";
import WhatIf from "./pages/WhatIf";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<Dashboard />} />
          <Route path="/assets" element={<Assets />} />
          <Route path="/cash-flows" element={<CashFlows />} />
          <Route path="/forecast" element={<ForecastDetail />} />
          <Route path="/what-if" element={<WhatIf />} />
          <Route path="/chat" element={<Chat />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
