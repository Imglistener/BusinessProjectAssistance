import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { apiGet } from "./api/client";

function Home() {
  const [status, setStatus] = useState("checking...");

  useEffect(() => {
    apiGet<{ status: string }>("/health")
      .then((r) => setStatus(r.status))
      .catch(() => setStatus("backend unreachable"));
  }, []);

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1>Business Project Assistance</h1>
      <p>API status: {status}</p>
      <p>Next: login/signup, organization setup, dashboard.</p>
    </main>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  );
}
