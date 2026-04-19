import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SITE_URL = "https://fintechapis.help";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const dataFile = path.join(repoRoot, "data", "apis.seed.json");
const indexFile = path.join(repoRoot, "index.html");
const sitemapFile = path.join(repoRoot, "sitemap.xml");
const robotsFile = path.join(repoRoot, "robots.txt");

const apis = JSON.parse(readFileSync(dataFile, "utf8"));
const latestDate = getLatestDate([dataFile, indexFile]);

const routes = buildRoutes(apis, latestDate);

mkdirSync(path.dirname(sitemapFile), { recursive: true });

writeFileSync(sitemapFile, buildSitemapXml(routes), "utf8");
writeFileSync(robotsFile, buildRobotsTxt(), "utf8");

console.log(`Generated sitemap for ${routes.length} URL${routes.length === 1 ? "" : "s"}.`);

function buildRoutes(apiRecords, lastmod) {
  const routes = [
    {
      loc: `${SITE_URL}/`,
      changefreq: "weekly",
      priority: "1.0",
      lastmod
    }
  ];

  if (Array.isArray(apiRecords) && apiRecords.length > 0) {
    routes[0].lastmod = lastmod;
  }

  return routes;
}

function buildSitemapXml(routes) {
  const body = routes
    .map(
      (route) => `  <url>
    <loc>${escapeXml(route.loc)}</loc>
    <lastmod>${route.lastmod}</lastmod>
    <changefreq>${route.changefreq}</changefreq>
    <priority>${route.priority}</priority>
  </url>`
    )
    .join("\n");

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${body}
</urlset>
`;
}

function buildRobotsTxt() {
  return `User-agent: *
Allow: /

Sitemap: ${SITE_URL}/sitemap.xml
`;
}

function getLatestDate(files) {
  return files
    .map((file) => statSync(file).mtime.toISOString().slice(0, 10))
    .sort()
    .at(-1);
}

function escapeXml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}
