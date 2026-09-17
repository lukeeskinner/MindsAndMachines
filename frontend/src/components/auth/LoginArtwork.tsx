import { useEffect, useRef, useState } from "react";
import type { LoginScene } from "./loginScene";

const texture = Array.from({ length: 34 }, (_, y) =>
  Array.from({ length: 64 }, (_, x) => " .:+ox8@"[Math.floor((Math.sin(x * 0.2 + y * 0.13) + 1) * 3.5)]).join(""),
).join("\n");

export function LoginArtwork() {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<LoginScene | null>(null);
  const [ready, setReady] = useState(false);
  const [reduced, setReduced] = useState(() =>
    typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const playing = useRef(!reduced);
  playing.current = !reduced;

  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const element = host.current;
    if (!element || typeof WebGL2RenderingContext === "undefined" || typeof ResizeObserver === "undefined") return;
    let cancelled = false;
    // Three.js is loaded only for this artwork; signing in never waits on it.
    void import("./loginScene").then(({ createLoginScene }) => {
      if (cancelled) return;
      scene.current = createLoginScene(element, setReady);
      scene.current.setPlaying(playing.current);
      setReady(true);
    }).catch(() => { if (!cancelled) setReady(false); });
    return () => { cancelled = true; scene.current?.dispose(); scene.current = null; };
  }, []);

  useEffect(() => { scene.current?.setPlaying(!reduced); }, [reduced]);

  return (
    <div className="auth-artwork" data-rendered={ready}>
      <pre className="auth-ascii-texture" aria-hidden="true">{texture}</pre>
      <div className="auth-art-fallback" aria-hidden="true" />
      <div className="auth-art-canvas" ref={host} aria-hidden="true" />
    </div>
  );
}
