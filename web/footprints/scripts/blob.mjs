// Private print files in Vercel Blob, for the shop's GitHub workflows.
//   node blob.mjs put <file> <pathname>      -> {"pathname": "..."}   (stored privately)
//   node blob.mjs sign <pathname> <hours>    -> {"url": "..."}        (time-limited download link)
//   node blob.mjs del <pathname> [...]       -> {}
// Needs BLOB_READ_WRITE_TOKEN (the store's read-write token). Uses @vercel/blob from
// web/footprints/package.json: run `npm ci --prefix web/footprints` first.
import { put, del, issueSignedToken, presignUrl } from "@vercel/blob";
import { readFile } from "node:fs/promises";

const [command, ...args] = process.argv.slice(2);
const token = process.env.BLOB_READ_WRITE_TOKEN;
if (!token) { console.error("BLOB_READ_WRITE_TOKEN is not set"); process.exit(2); }

if (command === "put" && args.length === 2) {
  const [file, pathname] = args;
  const type = file.endsWith(".pdf") ? "application/pdf" : "image/png";
  const blob = await put(pathname, await readFile(file), {
    access: "private", addRandomSuffix: false, allowOverwrite: true, contentType: type, token,
  });
  process.stdout.write(JSON.stringify({ pathname: blob.pathname }));
} else if (command === "sign" && args.length === 2) {
  const [pathname, hours] = args;
  const validUntil = Date.now() + Number(hours) * 3600 * 1000;
  const signed = await issueSignedToken({ pathname, operations: ["get"], validUntil, token });
  const { presignedUrl } = await presignUrl(signed, { operation: "get", pathname, access: "private", validUntil });
  process.stdout.write(JSON.stringify({ url: presignedUrl }));
} else if (command === "del" && args.length > 0) {
  await del(args, { token });
  process.stdout.write("{}");
} else {
  console.error("Usage: blob.mjs put <file> <pathname> | sign <pathname> <hours> | del <pathname>...");
  process.exit(2);
}
