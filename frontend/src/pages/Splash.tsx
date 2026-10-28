import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { StarMark, ZellijField } from "../components/Zellij";

const SPLASH_MS = 2600;
const SPLASH_MS_REDUCED = 900;

export default function Splash() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const target = user ? "/app" : "/login";

  useEffect(() => {
    if (loading) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const id = window.setTimeout(() => navigate(target, { replace: true }), reduced ? SPLASH_MS_REDUCED : SPLASH_MS);
    return () => window.clearTimeout(id);
  }, [loading, navigate, target]);

  return (
    <div className="splash">
      <ZellijField className="splash__field" />
      <div className="splash__center">
        <StarMark size={148} draw />
        <h1 className="splash__name">
          Business Project
          <br />
          Assistance
        </h1>
        <p className="splash__tagline">Budgets, tasks and a second pair of eyes on the numbers.</p>
      </div>
      <button type="button" className="splash__skip" onClick={() => navigate(target, { replace: true })}>
        Skip
      </button>
    </div>
  );
}
