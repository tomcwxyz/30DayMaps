// Store and remove print files in Vercel Blob, so Prodigi can fetch them by URL.
//   node blob.mjs put <file> <pathname>   -> {"url": "..."}
//   node blob.mjs del <url> [<url> ...]   -> {}
// Needs BLOB_READ_WRITE_TOKEN. Blob URLs are public but carry a long random suffix,
// and print files are deleted once the order has shipped.
import { put, del } from "@vercel/blob";
import { readFile } from "node:fs/promises";

const [command, ...args] = process.argv.slice(2);
const token = process.env.BLOB_READ_WRITE_TOKEN;
if (!token) { console.error("BLOB_READ_WRITE_TOKEN is not set"); process.exit(2); }

if (command === "put" && args.length === 2) {
  const [file, pathname] = args;
  const type = file.endsWith(".pdf") ? "application/pdf" : "image/png";
  const blob = await put(pathname, await readFile(file), { access: "public", addRandomSuffix: true, contentType: type, token });
  process.stdout.write(JSON.stringify({ url: blob.url }));
} else if (command === "del" && args.length > 0) {
  await del(args, { token });
  process.stdout.write("{}");
} else {
  console.error("Usage: blob.mjs put <file> <pathname> | del <url>...");
  process.exit(2);
}
