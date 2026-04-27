import { useRef, useEffect, useCallback } from 'react';

export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

interface ParticleSphereProps {
  state: VoiceState;
  audioLevel: number; // 0..1
  size?: number;
}

// Particle stored in spherical coords, projected to 2D
interface Particle {
  theta: number;
  phi: number;
  baseRadius: number;
  speed: number;
  size: number;
  opacity: number;
}

const PARTICLE_COUNT = 200;
const BASE_RADIUS_RATIO = 0.3; // fraction of canvas size

function createParticles(): Particle[] {
  const particles: Particle[] = [];
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    // Fibonacci sphere distribution for even spacing
    const y = 1 - (i / (PARTICLE_COUNT - 1)) * 2; // -1..1
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    const theta = goldenAngle * i;
    const phi = Math.acos(y);

    particles.push({
      theta,
      phi,
      baseRadius: 0.9 + Math.random() * 0.2, // slight variation
      speed: 0.3 + Math.random() * 0.7,
      size: 1.2 + Math.random() * 1.8,
      opacity: 0.4 + Math.random() * 0.6,
    });
  }
  return particles;
}

// Color palettes per state
const STATE_COLORS: Record<VoiceState, { r: number; g: number; b: number }> = {
  idle: { r: 100, g: 140, b: 200 },       // soft blue-grey
  listening: { r: 21, g: 101, b: 192 },    // primary blue — user is talking
  thinking: { r: 0, g: 180, b: 160 },      // teal — agent is processing
  speaking: { r: 156, g: 39, b: 176 },     // purple — AI is responding
};

export default function ParticleSphere({ state, audioLevel, size = 280 }: ParticleSphereProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>(createParticles());
  const rotationRef = useRef({ x: 0, y: 0 });
  const animFrameRef = useRef<number>(0);
  const stateRef = useRef(state);
  const audioRef = useRef(audioLevel);

  stateRef.current = state;
  audioRef.current = audioLevel;

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.width / dpr;
    const h = canvas.height / dpr;
    const cx = w / 2;
    const cy = h / 2;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.scale(dpr, dpr);

    const currentState = stateRef.current;
    const level = audioRef.current;
    const color = STATE_COLORS[currentState];
    const baseR = w * BASE_RADIUS_RATIO;

    // Rotation speeds per state
    const rotSpeed = currentState === 'thinking' ? 0.008 : 0.002;
    rotationRef.current.y += rotSpeed;
    if (currentState === 'thinking') {
      rotationRef.current.x += 0.003;
    }

    const cosRx = Math.cos(rotationRef.current.x);
    const sinRx = Math.sin(rotationRef.current.x);
    const cosRy = Math.cos(rotationRef.current.y);
    const sinRy = Math.sin(rotationRef.current.y);

    // Audio reactivity: expand sphere on activity
    const audioExpand = currentState === 'idle' ? 0 : level * 0.35;
    const breathe = Math.sin(Date.now() * 0.001) * 0.02; // subtle idle breathing
    const radiusMultiplier = 1 + audioExpand + breathe;

    // Vibration on audio
    const vibration = (currentState === 'listening' || currentState === 'speaking') ? level * 3 : 0;

    const particles = particlesRef.current;

    // Sort by depth for proper layering
    const projected: { x: number; y: number; z: number; idx: number }[] = [];

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      const r = baseR * p.baseRadius * radiusMultiplier;

      // Spherical to cartesian
      let x = r * Math.sin(p.phi) * Math.cos(p.theta);
      let y = r * Math.cos(p.phi);
      let z = r * Math.sin(p.phi) * Math.sin(p.theta);

      // Rotate Y
      const x1 = x * cosRy - z * sinRy;
      const z1 = x * sinRy + z * cosRy;
      // Rotate X
      const y1 = y * cosRx - z1 * sinRx;
      const z2 = y * sinRx + z1 * cosRx;

      // Add vibration
      const vx = vibration ? (Math.random() - 0.5) * vibration : 0;
      const vy = vibration ? (Math.random() - 0.5) * vibration : 0;

      projected.push({ x: x1 + vx, y: y1 + vy, z: z2, idx: i });
    }

    // Sort back-to-front
    projected.sort((a, b) => a.z - b.z);

    for (const proj of projected) {
      const p = particles[proj.idx];
      // Depth-based opacity and size
      const depthFactor = (proj.z + baseR * 1.5) / (baseR * 3);
      const alpha = p.opacity * Math.max(0.15, Math.min(1, depthFactor));
      const dotSize = p.size * (0.5 + depthFactor * 0.8);

      ctx.beginPath();
      ctx.arc(cx + proj.x, cy + proj.y, dotSize, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${color.r}, ${color.g}, ${color.b}, ${alpha})`;
      ctx.fill();
    }

    // Soft glow in center
    const glowAlpha = 0.05 + level * 0.08;
    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseR * 0.8);
    gradient.addColorStop(0, `rgba(${color.r}, ${color.g}, ${color.b}, ${glowAlpha})`);
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);

    ctx.restore();
    animFrameRef.current = requestAnimationFrame(draw);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;

    animFrameRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [size, draw]);

  return (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label="Indicador visual del asistente de voz"
      style={{ display: 'block' }}
    />
  );
}
