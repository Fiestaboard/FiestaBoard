/**
 * Compat shim for `next/image` on React Router v7 + Vite.
 *
 * 5 files in this codebase use `next/image`: login, picks, integrations
 * pages mostly for first-party assets. There is no Vite-side image
 * optimization pipeline (and no Node server to serve optimized images
 * from), so we render a plain `<img>` and drop the Next-only props.
 *
 * Critically:
 *  - `width` and `height` pass through as DOM attributes (good — keeps
 *    layout from shifting).
 *  - `priority` becomes `loading="eager"`; otherwise we default to
 *    `loading="lazy"` (matches Next's default).
 *  - `src` accepts both string and Vite's imported asset object — the
 *    object form (`import logo from "./logo.png"`) is unused in this
 *    codebase so we treat src as a string.
 *  - `fill` is unimplemented because no call sites use it.
 *
 * The `alt` attribute is required (matches Next.js's contract — caught
 * by eslint-plugin-jsx-a11y too).
 */
import type { ImgHTMLAttributes } from "react";

type NextImageProps = Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "alt" | "loading"> & {
  src: string;
  alt: string;
  width?: number | string;
  height?: number | string;
  priority?: boolean;
  loading?: "eager" | "lazy";
  // Next-only props we accept and discard:
  quality?: number;
  placeholder?: "blur" | "empty";
  blurDataURL?: string;
  sizes?: string;
  fill?: boolean;
  unoptimized?: boolean;
};

export default function Image({
  src,
  alt,
  width,
  height,
  priority,
  loading,
  quality: _quality,
  placeholder: _placeholder,
  blurDataURL: _blurDataURL,
  sizes: _sizes,
  fill: _fill,
  unoptimized: _unoptimized,
  ...rest
}: NextImageProps) {
  return (
    <img
      src={src}
      alt={alt}
      width={width}
      height={height}
      loading={loading ?? (priority ? "eager" : "lazy")}
      decoding="async"
      {...rest}
    />
  );
}
