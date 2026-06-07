"use client";

import { memo, useEffect, useRef } from "react";

const PRIDE_COLORS = ["#e40303", "#ff8c00", "#ffed00", "#008026", "#004dff", "#750787"];

const VERT = `#version 300 es
in vec2 position;
void main() { gl_Position = vec4(position, 0.0, 1.0); }`;

// Horizontal aurora: pride colours run left→right, intensity builds a soft
// vertical glow centred in the bar. Gradual blur makes the left end diffuse
// and the right end sharp, consistent with the vertical desktop sidebar aurora.
const FRAG = `#version 300 es
precision highp float;
uniform float uTime;
uniform vec3  uColorStops[6];
uniform vec2  uResolution;
uniform float uBlend;
out vec4 fragColor;

vec3 permute(vec3 x){ return mod(((x*34.0)+1.0)*x,289.0); }
float snoise(vec2 v){
  const vec4 C=vec4(0.211324865405187,0.366025403784439,-0.577350269189626,0.024390243902439);
  vec2 i=floor(v+dot(v,C.yy));
  vec2 x0=v-i+dot(i,C.xx);
  vec2 i1=(x0.x>x0.y)?vec2(1.,0.):vec2(0.,1.);
  vec4 x12=x0.xyxy+C.xxzz; x12.xy-=i1;
  i=mod(i,289.0);
  vec3 p=permute(permute(i.y+vec3(0.,i1.y,1.))+i.x+vec3(0.,i1.x,1.));
  vec3 m=max(.5-vec3(dot(x0,x0),dot(x12.xy,x12.xy),dot(x12.zw,x12.zw)),0.);
  m=m*m; m=m*m;
  vec3 x2=2.*fract(p*C.www)-1.;
  vec3 h=abs(x2)-.5; vec3 ox=floor(x2+.5); vec3 a0=x2-ox;
  m*=1.79284291400159-0.85373472095314*(a0*a0+h*h);
  vec3 g; g.x=a0.x*x0.x+h.x*x0.y; g.yz=a0.yz*x12.xz+h.yz*x12.yw;
  return 130.*dot(m,g);
}

void main(){
  vec2 uv = gl_FragCoord.xy / uResolution;

  // Colour ramp along X (red→orange→yellow→green→blue→violet).
  float t  = uv.x;
  float fi = clamp(t * 5.0, 0.0, 4.999);
  int   ix = int(fi);
  float fr = fract(fi);
  vec3 colA, colB;
  if      (ix == 0) { colA = uColorStops[0]; colB = uColorStops[1]; }
  else if (ix == 1) { colA = uColorStops[1]; colB = uColorStops[2]; }
  else if (ix == 2) { colA = uColorStops[2]; colB = uColorStops[3]; }
  else if (ix == 3) { colA = uColorStops[3]; colB = uColorStops[4]; }
  else              { colA = uColorStops[4]; colB = uColorStops[5]; }
  vec3 ramp = mix(colA, colB, fr);

  // Noise samples along X — makes the aurora boundary undulate vertically over time.
  float n  = snoise(vec2(uv.x * 2.5 + uTime * 0.08, uTime * 0.18)) * 0.5;
       n  += snoise(vec2(uv.x * 5.0 - uTime * 0.05, uTime * 0.12 + 3.0)) * 0.25;

  // Aurora concentrated in the bottom ~40% of the bar, fading upward.
  // pow(yi, 2.0) has zero slope at yi=0 so the boundary dissolves smoothly.
  // No floor: above the boundary intensity is exactly 0, no ghost film.
  float yi = clamp(((1.0 - uv.y) - 0.4) * 2.0 + n * 0.18, 0.0, 1.0);
  float intensity = pow(yi, 2.0) * uBlend;

  fragColor = vec4(ramp, intensity);
}`;

function hexToRgb(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16) / 255,
    parseInt(hex.slice(3, 5), 16) / 255,
    parseInt(hex.slice(5, 7), 16) / 255,
  ];
}

export const SidebarAuroraHorizontal = memo(function SidebarAuroraHorizontal() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: false, antialias: true });
    if (!gl) {
      console.error("SidebarAuroraHorizontal: WebGL2 not available");
      return;
    }

    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    function compileShader(type: number, src: string) {
      const s = gl!.createShader(type);
      if (!s) return null;
      gl!.shaderSource(s, src);
      gl!.compileShader(s);
      if (!gl!.getShaderParameter(s, gl!.COMPILE_STATUS)) {
        console.error("SidebarAuroraHorizontal shader error:", gl!.getShaderInfoLog(s));
        return null;
      }
      return s;
    }

    const vert = compileShader(gl.VERTEX_SHADER, VERT);
    const frag = compileShader(gl.FRAGMENT_SHADER, FRAG);
    if (!vert || !frag) return;

    const prog = gl.createProgram();
    if (!prog) return;
    gl.attachShader(prog, vert);
    gl.attachShader(prog, frag);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error("SidebarAuroraHorizontal link error:", gl.getProgramInfoLog(prog));
      return;
    }
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const posLoc = gl.getAttribLocation(prog, "position");
    gl.enableVertexAttribArray(posLoc);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

    const uTime  = gl.getUniformLocation(prog, "uTime");
    const uStops = gl.getUniformLocation(prog, "uColorStops");
    const uRes   = gl.getUniformLocation(prog, "uResolution");
    const uBlend = gl.getUniformLocation(prog, "uBlend");

    gl.uniform3fv(uStops, new Float32Array(PRIDE_COLORS.flatMap(hexToRgb)));
    gl.uniform1f(uBlend, 0.75);

    function resize() {
      const parent = canvas!.parentElement;
      if (!parent) return;
      const { width: w, height: h } = parent.getBoundingClientRect();
      canvas!.width  = Math.floor(w);
      canvas!.height = Math.floor(h);
      canvas!.style.width  = `${w}px`;
      canvas!.style.height = `${h}px`;
      gl!.viewport(0, 0, Math.floor(w), Math.floor(h));
      gl!.uniform2f(uRes, w, h);
    }

    const ro = new ResizeObserver(resize);
    ro.observe(canvas.parentElement!);
    resize();

    let rafId = 0;
    const tick = (ts: number) => {
      rafId = requestAnimationFrame(tick);
      gl!.uniform1f(uTime, ts * 0.001);
      gl!.clear(gl!.COLOR_BUFFER_BIT);
      gl!.drawArrays(gl!.TRIANGLES, 0, 3);
    };
    rafId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
    };
  }, []);

  return (
    <div
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        borderRadius: "16px",
        pointerEvents: "none",
      }}
    >
      <canvas
        ref={canvasRef}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      />
    </div>
  );
});
