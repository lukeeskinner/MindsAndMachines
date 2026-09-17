import {
  AmbientLight, BufferAttribute, Color, DirectionalLight, Group, Mesh,
  MeshPhysicalMaterial, MeshStandardMaterial, PerspectiveCamera, PMREMGenerator,
  Scene, SphereGeometry, SRGBColorSpace, ACESFilmicToneMapping, TorusKnotGeometry,
  WebGLRenderer,
} from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

export type LoginScene = { setPlaying: (playing: boolean) => void; dispose: () => void };

export function createLoginScene(host: HTMLElement, onReady: (ready: boolean) => void): LoginScene {
  const renderer = new WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
  const resources: { dispose: () => void }[] = [renderer];
  try {
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.toneMapping = ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    renderer.setClearColor(0x000000, 0);
    const scene = new Scene();
    const camera = new PerspectiveCamera(35, 1, 0.1, 50);
    camera.position.set(0, 0, 8.7);
    const room = new RoomEnvironment();
    const generator = new PMREMGenerator(renderer);
    let environment;
    try { environment = generator.fromScene(room, 0.04); }
    finally { room.dispose(); generator.dispose(); }
    resources.push(environment);
    scene.environment = environment.texture;
    scene.add(new AmbientLight(0xb9f7ec, 0.55));
    const key = new DirectionalLight(0xffffff, 3);
    key.position.set(-3, 4, 5);
    const rim = new DirectionalLight(0x38bdf8, 3.5);
    rim.position.set(4, -1, -2);
    scene.add(key, rim);

    const shape = new Group();
    const geometry = new TorusKnotGeometry(1.15, 0.32, 180, 28, 2, 3);
    resources.push(geometry);
    const positions = geometry.getAttribute("position");
    const colors = new Float32Array(positions.count * 3);
    const teal = new Color("#14b8a6"), sky = new Color("#38bdf8");
    for (let i = 0; i < positions.count; i++) {
      const color = teal.clone().lerp(sky, (Math.sin(positions.getY(i) * 1.3 + positions.getX(i) * 0.6) + 1) / 2);
      colors.set([color.r, color.g, color.b], i * 3);
    }
    geometry.setAttribute("color", new BufferAttribute(colors, 3));
    const material = new MeshPhysicalMaterial({
      vertexColors: true, metalness: 0, roughness: 0.8, clearcoat: 0,
      iridescence: 0, specularIntensity: 0.2, envMapIntensity: 0.65,
    });
    resources.push(material);
    const knot = new Mesh(geometry, material);
    shape.add(knot);
    shape.rotation.set(-0.28, 0.42, 0.18);
    scene.add(shape);
    const beadGeometry = new SphereGeometry(0.075, 24, 16);
    const beadMaterial = new MeshStandardMaterial({ color: 0xfacc15, metalness: 0, roughness: 0.8 });
    resources.push(beadGeometry, beadMaterial);
    const bead = new Mesh(beadGeometry, beadMaterial);
    bead.position.set(1.9, 0.7, 0.5);
    scene.add(bead);
    renderer.domElement.setAttribute("aria-hidden", "true");
    host.appendChild(renderer.domElement);

    let playing = false, visible = true, lost = false, disposed = false;
    let time = 0, last = 0, lastPaint = 0;
    let pointerX = 0, pointerY = 0, tiltX = 0, tiltY = 0;
    function render() { if (!lost && !disposed) renderer.render(scene, camera); }
    function animate(now: number) {
      if (now - lastPaint < 33) return;
      time += Math.min((now - last) / 1000, 0.05);
      last = now; lastPaint = now;
      tiltX += (pointerX - tiltX) * 0.045;
      tiltY += (pointerY - tiltY) * 0.045;
      shape.rotation.x = -0.28 + Math.sin(time * 0.18) * 0.12 + tiltY * 0.15;
      shape.rotation.y = 0.42 + Math.sin(time * 0.14) * 0.38 + tiltX * 0.3;
      shape.rotation.z = 0.18 + Math.sin(time * 0.12) * 0.08;
      shape.position.y = Math.sin(time * 0.65) * 0.075;
      bead.position.y = 0.7 + Math.sin(time * 0.7 + 1) * 0.16;
      render();
    }
    function playback() {
      last = performance.now();
      renderer.setAnimationLoop(playing && visible && !document.hidden && !lost && !disposed ? animate : null);
    }
    const resize = new ResizeObserver(() => {
      const { width, height } = host.getBoundingClientRect();
      if (!width || !height) return;
      camera.aspect = width / height;
      camera.position.z = camera.aspect < 0.85 ? 10.2 : 8.7;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      render();
    });
    const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; playback(); });
    const move = (event: PointerEvent) => {
      if (!playing || event.pointerType !== "mouse") return;
      const bounds = host.getBoundingClientRect();
      pointerX = (event.clientX - bounds.left) / bounds.width - 0.5;
      pointerY = (event.clientY - bounds.top) / bounds.height - 0.5;
    };
    const leave = () => { pointerX = 0; pointerY = 0; };
    const contextLost = (event: Event) => { event.preventDefault(); lost = true; playback(); onReady(false); };
    const contextRestored = () => { lost = false; render(); playback(); onReady(true); };
    resize.observe(host);
    intersection.observe(host);
    document.addEventListener("visibilitychange", playback);
    host.addEventListener("pointermove", move);
    host.addEventListener("pointerleave", leave);
    renderer.domElement.addEventListener("webglcontextlost", contextLost);
    renderer.domElement.addEventListener("webglcontextrestored", contextRestored);
    return {
      setPlaying(value) { playing = value; playback(); },
      dispose() {
        disposed = true;
        renderer.setAnimationLoop(null);
        resize.disconnect(); intersection.disconnect();
        document.removeEventListener("visibilitychange", playback);
        host.removeEventListener("pointermove", move);
        host.removeEventListener("pointerleave", leave);
        renderer.domElement.removeEventListener("webglcontextlost", contextLost);
        renderer.domElement.removeEventListener("webglcontextrestored", contextRestored);
        renderer.domElement.remove();
        resources.reverse().forEach(resource => resource.dispose());
      },
    };
  } catch (error) {
    renderer.domElement.remove();
    resources.reverse().forEach(resource => resource.dispose());
    throw error;
  }
}
