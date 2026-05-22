import { spawn } from "node:child_process";
import { createWriteStream } from "node:fs";
import { resolve } from "node:path";

const command = process.platform === "win32" ? "npx.cmd" : "npx";
const args = ["cypress", "run", ...process.argv.slice(2)];
const log = createWriteStream(resolve(process.cwd(), "cypress-results.log"), {
  flags: "w",
});

const child = spawn(command, args, {
  cwd: process.cwd(),
  env: process.env,
  stdio: ["ignore", "pipe", "pipe"],
});

const write = (chunk) => {
  process.stdout.write(chunk);
  log.write(chunk);
};

child.stdout.on("data", write);
child.stderr.on("data", (chunk) => {
  process.stderr.write(chunk);
  log.write(chunk);
});

child.on("error", (error) => {
  const message = `${error.stack || error.message}\n`;
  process.stderr.write(message);
  log.write(message);
  log.end(() => process.exit(1));
});

child.on("close", (code) => {
  log.end(() => process.exit(code ?? 1));
});
