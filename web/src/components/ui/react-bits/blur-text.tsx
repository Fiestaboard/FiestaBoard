"use client";

import { useEffect, useRef, useState } from "react";

interface BlurTextProps {
  text?: string;
  delay?: number;
  className?: string;
  animateBy?: "words" | "letters";
  direction?: "top" | "bottom";
  threshold?: number;
  rootMargin?: string;
  stepDuration?: number;
  onAnimationComplete?: () => void;
}

export default function BlurText({
  text = "",
  delay = 200,
  className = "",
  animateBy = "words",
  direction = "top",
  threshold = 0.1,
  rootMargin = "0px",
  stepDuration = 0.35,
  onAnimationComplete,
}: BlurTextProps) {
  const elements = animateBy === "words" ? text.split(" ") : text.split("");
  const [inView, setInView] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const completedCount = useRef(0);

  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.unobserve(el);
        }
      },
      { threshold, rootMargin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold, rootMargin]);

  return (
    <span ref={ref} className={`inline-flex flex-wrap ${className}`}>
      {elements.map((segment, index) => (
        <span
          key={index}
          style={{
            display: "inline-block",
            opacity: inView ? 1 : 0,
            filter: inView ? "blur(0px)" : "blur(10px)",
            transform: inView ? "translateY(0)" : direction === "top" ? "translateY(-30px)" : "translateY(30px)",
            transition: `opacity ${stepDuration}s ease, filter ${stepDuration}s ease, transform ${stepDuration}s ease`,
            transitionDelay: `${(index * delay) / 1000}s`,
          }}
          onTransitionEnd={(e) => {
            if (e.propertyName !== "opacity") return;
            completedCount.current++;
            if (completedCount.current === elements.length && onAnimationComplete) {
              onAnimationComplete();
            }
          }}
        >
          {segment === " " ? "\u00A0" : segment}
          {animateBy === "words" && index < elements.length - 1 && "\u00A0"}
        </span>
      ))}
    </span>
  );
}
