"use client";

import { useEffect, useRef, useState } from "react";

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

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.unobserve(el);
        }
      },
      { threshold }
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
