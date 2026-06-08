"use client";

import { useLayoutEffect, useRef, useState } from "react";

interface FadeContentProps {
  children: React.ReactNode;
  blur?: boolean;
  duration?: number;
  delay?: number;
  threshold?: number;
  className?: string;
  translateY?: number;
}

export default function FadeContent({
  children,
  blur = false,
  duration = 0.6,
  delay = 0,
  threshold = 0.1,
  className = "",
  translateY = 20,
}: FadeContentProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);

  // If the element is already on-screen at mount, kick the animation off on
  // the next frame — IntersectionObserver fires asynchronously and would leave
  // a ~20-30ms gap of invisible content between mount and animation start
  // (perceived as a flicker right after a route transition, since the new
  // PageFadeWrapper mounts with opacity:0 and stays there until the observer
  // catches up). Off-screen mounts still fall back to the observer so this
  // keeps working as a scroll-into-view effect elsewhere.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const vh = window.innerHeight || document.documentElement.clientHeight;
    const vw = window.innerWidth || document.documentElement.clientWidth;
    const onScreen = rect.bottom > 0 && rect.right > 0 && rect.top < vh && rect.left < vw;

    if (onScreen) {
      const raf = requestAnimationFrame(() => setInView(true));
      return () => cancelAnimationFrame(raf);
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.unobserve(el);
        }
      },
      { threshold },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: inView ? 1 : 0,
        filter: blur ? (inView ? "blur(0px)" : "blur(10px)") : undefined,
        transform: inView ? "translateY(0)" : `translateY(${translateY}px)`,
        transition: `opacity ${duration}s ease, filter ${duration}s ease, transform ${duration}s ease`,
        transitionDelay: `${delay}s`,
      }}
    >
      {children}
    </div>
  );
}
