import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const inputPath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(projectRoot, "artifacts", "solar-weather-poster-v2.svg");
const outputPath = process.argv[3]
  ? path.resolve(process.argv[3])
  : inputPath.replace(/\.svg$/i, ".png");

const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

const result = spawnSync(edgePath, [
  "--headless=new",
  "--disable-gpu",
  "--no-sandbox",
  "--hide-scrollbars",
  "--window-size=1200,1600",
  `--screenshot=${outputPath}`,
  pathToFileURL(inputPath).href,
], { encoding: "utf8", timeout: 30000 });

if (result.error) throw result.error;
if (result.status !== 0) throw new Error(result.stderr || `Edge exited with ${result.status}`);
process.stdout.write(JSON.stringify({ input: inputPath, output: outputPath, width: 1200, height: 1600 }));
