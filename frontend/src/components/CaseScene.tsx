"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { visitLabel, type JourneyGraph } from "@/lib/journeyGraph";
import type { PersonaState } from "@/lib/types";
import { personaColors } from "./PersonaSprite";

interface Props {
  graph: JourneyGraph;
  personas: PersonaState[];
  chapter: number;
  playing: boolean;
  replay: number;
  onUnavailable: () => void;
  onComplete: () => void;
}

function textSprite(text: string, color: string, width = 3.2) {
  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 100;
  const context = canvas.getContext("2d")!;
  context.font = "600 46px Arial";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillStyle = color;
  context.fillText(text, 320, 50, 620);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false }));
  sprite.scale.set(width, width / 6.4, 1);
  return sprite;
}

export default function CaseScene({ graph, personas, chapter, playing, replay, onUnavailable, onComplete }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const playback = useRef(playing);
  const updatePlayback = useRef<(() => void) | null>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const canvas = document.createElement("canvas");
    // Probe before constructing Three's renderer so unsupported devices do not log renderer errors.
    const context = canvas.getContext("webgl2", { antialias: true, alpha: false });
    if (!context) { onUnavailable(); return; }
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ canvas, context, antialias: true }); }
    catch { onUnavailable(); return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.setClearColor(0x0b1724);
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", `${graph.nodes.length} page stations, ${graph.transitions.length} recorded transitions. Full journeys and outcomes are available in the text alternative below.`);
    element.appendChild(canvas);

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-13, 13, 8, -8, .1, 100);
    camera.position.set(1, 13, 15);
    camera.lookAt(0, 0, 0);
    const light = new THREE.DirectionalLight(0xb0e8ff, 3);
    light.position.set(-3, 12, 7);
    scene.add(light, new THREE.AmbientLight(0x8faec9, 2));
    const grid = new THREE.GridHelper(34, 34, 0x284c50, 0x172d3b);
    grid.position.y = -.35;
    scene.add(grid);

    const positions = new Map(graph.nodes.map(node => [node.path, new THREE.Vector3((node.x - 600) / 48, 0, (node.y - 210) / 35)]));
    const xs = positions.size ? [...positions.values()].map(p => p.x) : [0];
    const zs = positions.size ? [...positions.values()].map(p => p.z) : [0];
    const center = new THREE.Vector3((Math.min(...xs) + Math.max(...xs)) / 2, 0, (Math.min(...zs) + Math.max(...zs)) / 2);
    const bounds = { halfX: (Math.max(...xs) - Math.min(...xs)) / 2, halfZ: (Math.max(...zs) - Math.min(...zs)) / 2 };
    camera.position.set(center.x + 1, 13, center.z + 15);
    camera.lookAt(center);
    const rings: THREE.Mesh[] = [];
    for (const [index, node] of graph.nodes.entries()) {
      const position = positions.get(node.path)!;
      const station = new THREE.Mesh(
        new THREE.CylinderGeometry(.43, .65, .36, 6),
        new THREE.MeshStandardMaterial({ color: 0x2a465d, metalness: .5, roughness: .5 }),
      );
      station.position.copy(position);
      scene.add(station);
      const cap = new THREE.Mesh(new THREE.CylinderGeometry(.3, .3, .035, 6), new THREE.MeshBasicMaterial({ color: 0x87bfff }));
      cap.position.copy(position).y = .2;
      scene.add(cap);
      const title = textSprite(node.label, "#edf4fb", 3.15);
      title.position.copy(position).add(new THREE.Vector3(0, -.05, 1.05));
      const count = textSprite(`${String(index + 1).padStart(2, "0")} / ${visitLabel(graph, node)}`, "#a2b3c6", 2.5);
      count.position.copy(position).add(new THREE.Vector3(0, -.1, 1.6));
      scene.add(title, count);
      if (node.friction && chapter > 0) {
        const color = { high: 0xff929d, medium: 0xf5d472, low: 0xa2b3c6 }[node.friction.severity];
        const ring = new THREE.Mesh(new THREE.TorusGeometry(.86, .045, 6, 40), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .85 }));
        ring.rotation.x = Math.PI / 2;
        ring.position.copy(position).y = .24;
        scene.add(ring);
        rings.push(ring);
        const badge = textSprite(`${node.friction.count} ${node.friction.count === 1 ? "finding" : "findings"}`, `#${color.toString(16)}`, 2.3);
        badge.position.copy(position).add(new THREE.Vector3(0, 1.4, 0));
        scene.add(badge);
      }
    }
    const paths = graph.transitions.map((transition, order) => {
      const index = Math.max(0, personas.findIndex(persona => persona.persona_id === transition.persona_id));
      const from = positions.get(transition.from)!;
      const to = positions.get(transition.to)!;
      const control = from.clone().lerp(to, .5);
      control.y = 1.4 + index * .4;
      control.z += transition.kind === "back" ? 1.5 : -.5;
      const curve = new THREE.QuadraticBezierCurve3(from, control, to);
      const color = personaColors[personas[index]?.persona_type] || "#a2b3c6";
      if (chapter > 0) {
        const material = transition.kind === "back"
          ? new THREE.LineDashedMaterial({ color, transparent: true, opacity: .55, dashSize: .13, gapSize: .1 })
          : new THREE.LineBasicMaterial({ color, transparent: true, opacity: .55 });
        const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(36)), material);
        line.computeLineDistances();
        scene.add(line);
      }
      return { ...transition, curve, order };
    });
    const particles = personas.flatMap((persona, index) => {
      const start = positions.get(graph.starts[persona.persona_id]);
      if (!start) return [];
      const particle = new THREE.Mesh(new THREE.IcosahedronGeometry(.15, 1), new THREE.MeshBasicMaterial({ color: personaColors[persona.persona_type] }));
      particle.position.copy(start).add(new THREE.Vector3(0, .4 + index * .18, 0));
      scene.add(particle);
      return [{ particle, start, index, paths: paths.filter(path => path.persona_id === persona.persona_id) }];
    });
    if (chapter === 2) {
      const slots = new Map<string, number>();
      for (const end of graph.ends) {
        const position = end.node ? positions.get(end.node) : null;
        if (!position) continue;
        const persona = personas.find(p => p.persona_id === end.persona_id);
        const offset = slots.get(end.node!) || 0;
        slots.set(end.node!, offset + 1);
        const color = persona ? personaColors[persona.persona_type] : "#a2b3c6";
        const marker = new THREE.Mesh(new THREE.OctahedronGeometry(.16), new THREE.MeshBasicMaterial({ color }));
        marker.position.copy(position).add(new THREE.Vector3(-.45 + offset * .35, .65, .45));
        scene.add(marker);
      }
      particles.forEach(({ particle }) => { particle.visible = false; });
    }
    let elapsed = 0;
    let lastTime = 0;
    let frame = 0;
    let visible = false;
    let disposed = false;
    const duration = 16000;
    function paint() {
      renderer.render(scene, camera);
      canvas.dataset.progress = String(Math.min(1, elapsed / duration));
    }
    function tick(time: number) {
      frame = 0;
      if (disposed || !visible || document.hidden || !playback.current || chapter !== 1) return;
      if (lastTime) elapsed += Math.min(time - lastTime, 100);
      lastTime = time;
      const cursor = Math.min(1, elapsed / duration) * paths.length;
      for (const { particle, start, index, paths: route } of particles) {
        particle.position.copy(start).add(new THREE.Vector3(0, .4 + index * .18, 0));
        for (const segment of route) {
          if (cursor < segment.order) break;
          particle.position.copy(segment.curve.getPoint(Math.min(1, cursor - segment.order)));
          particle.position.y += .18;
        }
      }
      rings.forEach(ring => ring.scale.setScalar(1 + Math.sin(elapsed / 600) * .06));
      paint();
      if (elapsed < duration) frame = requestAnimationFrame(tick);
      else onComplete();
    }
    function syncPlayback() {
      cancelAnimationFrame(frame);
      frame = 0;
      lastTime = 0;
      if (!disposed && visible && !document.hidden && playback.current && chapter === 1 && elapsed < duration) frame = requestAnimationFrame(tick);
      canvas.dataset.paused = String(!frame);
    }
    updatePlayback.current = syncPlayback;
    function resize() {
      const width = element!.clientWidth;
      const height = element!.clientHeight;
      if (!width || !height) return;
      const aspect = width / height;
      // Frame the recorded graph itself (plus label margin) instead of a fixed world size.
      const halfWidth = Math.max(bounds.halfX + 2.4, (bounds.halfZ * .6 + 1.9) * aspect, 6);
      camera.left = -halfWidth;
      camera.right = halfWidth;
      camera.top = halfWidth / aspect;
      camera.bottom = -halfWidth / aspect;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      paint();
    }
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(element);
    const intersection = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; syncPlayback(); });
    intersection.observe(element);
    document.addEventListener("visibilitychange", syncPlayback);
    function contextLost(event: Event) { event.preventDefault(); onUnavailable(); }
    canvas.addEventListener("webglcontextlost", contextLost);
    resize();
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      updatePlayback.current = null;
      intersection.disconnect();
      resizeObserver.disconnect();
      document.removeEventListener("visibilitychange", syncPlayback);
      canvas.removeEventListener("webglcontextlost", contextLost);
      scene.traverse(object => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Sprite) {
          if ("geometry" in object) object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach(material => {
            if ("map" in material && material.map instanceof THREE.Texture) material.map.dispose();
            material.dispose();
          });
        }
      });
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    };
  }, [graph, personas, chapter, replay, onUnavailable, onComplete]);

  useEffect(() => {
    playback.current = playing;
    updatePlayback.current?.();
  }, [playing, chapter, replay]);

  return <div className="case-canvas" ref={host} />;
}
