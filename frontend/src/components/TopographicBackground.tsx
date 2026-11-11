"use client";

import React, { useEffect, useRef } from "react";
import * as THREE from "three";

interface TopographicBackgroundProps {
  className?: string;
  intensity?: number;
  interactive?: boolean;
}

const VERTEX_SHADER = `
  uniform float u_time;
  uniform vec2 u_mouse;
  uniform float u_intensity;

  varying vec2 v_uv;
  varying float v_elevation;
  varying vec3 v_position;

  // Ashima Arts Simplex 3D Noise GLSL implementation
  vec4 permute(vec4 x){return mod(((x*34.0)+1.0)*x, 289.0);}
  vec4 taylorInvSqrt(vec4 r){return 1.79284291400159 - 0.85373472095314 * r;}

  float snoise(vec3 v){
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);

    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);

    vec3 x1 = x0 - i1 + 1.0 * C.xxx;
    vec3 x2 = x0 - i2 + 2.0 * C.xxx;
    vec3 x3 = x0 - 1.0 + 3.0 * C.xxx;

    i = mod(i, 289.0);
    vec4 p = permute(permute(permute(
               i.z + vec4(0.0, i1.z, i2.z, 1.0))
             + i.y + vec4(0.0, i1.y, i2.y, 1.0))
             + i.x + vec4(0.0, i1.x, i2.x, 1.0));

    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;

    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);

    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);

    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);

    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);

    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));

    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;

    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);

    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
    p0 *= norm.x;
    p1 *= norm.y;
    p2 *= norm.z;
    p3 *= norm.w;

    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
  }

  void main() {
    v_uv = uv;
    vec3 pos = position;

    // Multi-octave procedural displacement
    float n1 = snoise(vec3(pos.xy * 0.038, u_time * 0.08));
    float n2 = snoise(vec3(pos.xy * 0.075 + vec2(23.7, 41.2), u_time * 0.12)) * 0.5;
    float n3 = snoise(vec3(pos.xy * 0.14, u_time * 0.16)) * 0.25;

    // Interactive mouse displacement ripple
    float distToMouse = length(pos.xy - u_mouse * 32.0);
    float mouseWave = sin(distToMouse * 0.25 - u_time * 1.2) * exp(-distToMouse * 0.07) * 2.2;

    float elevation = (n1 + n2 + n3) * 4.2 * u_intensity + mouseWave;
    pos.z += elevation;

    v_elevation = elevation;
    v_position = pos;

    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

const FRAGMENT_SHADER = `
  uniform float u_time;
  uniform float u_intensity;
  uniform float u_contour_density;

  varying vec2 v_uv;
  varying float v_elevation;
  varying vec3 v_position;

  void main() {
    // Primary topographic contour lines
    float contour = fract((v_elevation + 12.0) * u_contour_density);
    float line = smoothstep(0.0, 0.08, contour) * (1.0 - smoothstep(0.08, 0.16, contour));

    // Major interval contour lines (every 5th line)
    float majorContour = fract((v_elevation + 12.0) * (u_contour_density * 0.2));
    float majorLine = smoothstep(0.0, 0.05, majorContour) * (1.0 - smoothstep(0.05, 0.12, majorContour));

    // Cyber-quant palette
    vec3 baseDark = vec3(0.015, 0.024, 0.038);
    vec3 cyanGlow = vec3(0.024, 0.714, 0.831);    // Cyan #06b6d4
    vec3 emeraldGlow = vec3(0.063, 0.725, 0.506); // Emerald #10b981
    vec3 indigoGlow = vec3(0.24, 0.32, 0.75);     // Deep Indigo

    // Height-based color interpolation
    float normalizedHeight = clamp((v_elevation + 4.0) / 8.5, 0.0, 1.0);
    vec3 elevationColor = mix(indigoGlow, cyanGlow, normalizedHeight);
    elevationColor = mix(elevationColor, emeraldGlow, pow(normalizedHeight, 2.2));

    // Edge radial falloff vignette so the plane blends seamlessly into obsidian
    float radialDist = length(v_uv - vec2(0.5)) * 2.0;
    float edgeFade = smoothstep(1.0, 0.28, radialDist);

    // Camera depth attenuation
    float depthFade = clamp(1.0 - (-v_position.y - 12.0) / 65.0, 0.15, 1.0);

    // Composite illumination
    vec3 finalColor = baseDark;
    finalColor += elevationColor * (line * 0.75 + majorLine * 1.35);
    finalColor += cyanGlow * 0.05 * normalizedHeight;

    float alpha = (line * 0.42 + majorLine * 0.62 + 0.06) * edgeFade * depthFade * u_intensity;

    gl_FragColor = vec4(finalColor, alpha);
  }
`;

export function TopographicBackground({
  className = "fixed inset-0 pointer-events-none z-0 overflow-hidden opacity-70",
  intensity = 1.0,
  interactive = true,
}: TopographicBackgroundProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Check WebGL availability
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: "low-power",
      });
    } catch (e) {
      console.warn("WebGL not supported for atmospheric background:", e);
      return;
    }

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      52,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );

    // Initial camera placement
    camera.position.set(0, -26, 20);
    camera.lookAt(0, 4, 0);

    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    // High-density topographic plane for GLSL displacement
    const width = 84;
    const height = 84;
    const segmentsX = 96;
    const segmentsY = 96;

    const geometry = new THREE.PlaneGeometry(width, height, segmentsX, segmentsY);

    // Custom GLSL Shader Material
    const uniforms = {
      u_time: { value: 0.0 },
      u_mouse: { value: new THREE.Vector2(0, 0) },
      u_intensity: { value: intensity },
      u_contour_density: { value: 0.8 },
    };

    const material = new THREE.ShaderMaterial({
      vertexShader: VERTEX_SHADER,
      fragmentShader: FRAGMENT_SHADER,
      uniforms: uniforms,
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
    });

    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    // Ambient floating particle dust for 3D spatial depth
    const ambientPointGeo = new THREE.BufferGeometry();
    const pointCount = 100;
    const pointPositions = new Float32Array(pointCount * 3);
    for (let i = 0; i < pointCount * 3; i += 3) {
      pointPositions[i] = (Math.random() - 0.5) * 75;
      pointPositions[i + 1] = (Math.random() - 0.5) * 75;
      pointPositions[i + 2] = Math.random() * 8 + 2;
    }
    ambientPointGeo.setAttribute(
      "position",
      new THREE.BufferAttribute(pointPositions, 3)
    );
    const pointMaterial = new THREE.PointsMaterial({
      color: 0x38bdf8,
      size: 0.5,
      transparent: true,
      opacity: 0.25 * intensity,
      blending: THREE.AdditiveBlending,
    });
    const pointsMesh = new THREE.Points(ambientPointGeo, pointMaterial);
    scene.add(pointsMesh);

    // Mouse parallax tracking
    let targetMouseX = 0;
    let targetMouseY = 0;
    let currentMouseX = 0;
    let currentMouseY = 0;

    const handleMouseMove = (e: MouseEvent) => {
      if (!interactive) return;
      targetMouseX = (e.clientX / window.innerWidth - 0.5) * 2;
      targetMouseY = (e.clientY / window.innerHeight - 0.5) * 2;
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });

    // Handle Resize
    const handleResize = () => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    // Animation loop with tab-visibility pause
    let animId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      animId = requestAnimationFrame(animate);

      if (document.hidden) return;

      const elapsed = clock.getElapsedTime();

      // Smooth mouse damping
      currentMouseX += (targetMouseX - currentMouseX) * 0.05;
      currentMouseY += (targetMouseY - currentMouseY) * 0.05;

      camera.position.x = currentMouseX * 3.5;
      camera.position.y = -26 + currentMouseY * 2.5;
      camera.lookAt(currentMouseX * 1.2, 4 + currentMouseY, 0);

      // Pass time and mouse uniforms directly to GPU GLSL shader
      material.uniforms.u_time.value = elapsed * 0.5;
      material.uniforms.u_mouse.value.set(currentMouseX, -currentMouseY);
      material.uniforms.u_intensity.value = intensity;

      // Slow ambient dust rotation
      pointsMesh.rotation.z = elapsed * 0.02;

      renderer.render(scene, camera);
    };

    animate();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("mousemove", handleMouseMove);
      resizeObserver.disconnect();

      geometry.dispose();
      material.dispose();
      ambientPointGeo.dispose();
      pointMaterial.dispose();
      renderer.dispose();

      if (renderer.domElement && container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [intensity, interactive]);

  return <div ref={containerRef} className={className} aria-hidden="true" />;
}

export default TopographicBackground;
