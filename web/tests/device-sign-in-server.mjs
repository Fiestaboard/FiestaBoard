// Isolated production-bundle fixture. Never reads or deletes repository data.
import { readFile } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
const root = path.resolve("build/client");
const prefix = "/test-prefix";
const upstreamBase = new URL(process.env.DEVICE_API_BASE_URL ?? "http://127.0.0.1:4429");
const mime = {
  ".js": "application/javascript",
  ".css": "text/css",
  ".html": "text/html",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};
http
  .createServer(async (req, res) => {
    const url = new URL(req.url, "http://127.0.0.1:4430");
    const base = url.pathname.startsWith(prefix + "/") || url.pathname === prefix ? prefix : "";
    const pathname = url.pathname.slice(base.length) || "/";
    if (pathname.startsWith("/api/")) {
      const upstream = http.request(
        {
          hostname: upstreamBase.hostname,
          port: upstreamBase.port,
          path: upstreamBase.pathname.replace(/\/$/, "") + pathname.slice(4) + url.search,
          method: req.method,
          headers: req.headers,
        },
        (response) => {
          res.writeHead(response.statusCode, response.headers);
          response.pipe(res);
        },
      );
      upstream.on("error", () => {
        res.writeHead(502);
        res.end();
      });
      req.pipe(upstream);
      return;
    }
    try {
      let filename = path.resolve(root, "." + pathname);
      if (!filename.startsWith(root + path.sep)) filename = path.join(root, "index.html");
      let body;
      try {
        body = await readFile(filename);
      } catch {
        filename = path.join(root, "index.html");
        body = await readFile(filename);
      }
      const ext = path.extname(filename);
      if (base && [".html", ".js", ".css"].includes(ext)) {
        let text = body.toString();
        if (ext === ".html") text = text.replaceAll('"basename":"/"', '"basename":"' + base + '/"');
        text = text
          .replaceAll('"/assets/', '"' + base + "/assets/")
          .replaceAll('"/icons/', '"' + base + "/icons/")
          .replaceAll('"/sw.js', '"' + base + "/sw.js")
          .replaceAll("'/sw.js", "'" + base + "/sw.js")
          .replaceAll('"/registerSW.js', '"' + base + "/registerSW.js")
          .replaceAll("scope: '/'", "scope: '" + base + "/'");
        body = Buffer.from(text);
      }
      res.writeHead(200, { "Content-Type": mime[ext] ?? "application/octet-stream", "Cache-Control": "no-store" });
      res.end(body);
    } catch {
      res.writeHead(500);
      res.end();
    }
  })
  .listen(4430, "127.0.0.1");
