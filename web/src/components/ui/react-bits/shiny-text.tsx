"use client";

import React from "react";

interface ShinyTextProps {
  text: string;
  disabled?: boolean;
  speed?: number;
  className?: string;
}

export default function ShinyText({
  text,
  disabled = false,
  speed = 3,
  className = "",
}: ShinyTextProps) {
  return (
    <span
      className={`inline-block bg-clip-text [-webkit-background-clip:text] [-webkit-text-fill-color:transparent] ${
        disabled ? "" : "animate-shiny-text"
      } ${className}`}
      style={{
        backgroundImage:
          "linear-gradient(120deg, currentColor 0%, currentColor 35%, rgba(255,255,255,0.9) 50%, currentColor 65%, currentColor 100%)",
        backgroundSize: "200% auto",
        animationDuration: `${speed}s`,
        color: "inherit",
      }}
    >
      {text}
    </span>
  );
}
