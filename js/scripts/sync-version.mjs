import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const version = readFileSync(join(root, "VERSION"), "utf8").trim();
const packageJsonPath = join(dirname(fileURLToPath(import.meta.url)), "..", "package.json");
const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf8"));
packageJson.version = version;
writeFileSync(packageJsonPath, `${JSON.stringify(packageJson, null, 2)}\n`);

const constantsPath = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "constants.ts");
let constants = readFileSync(constantsPath, "utf8");
constants = constants.replace(
  /export const VERSION = "[^"]+";/,
  `export const VERSION = "${version}";`,
);
writeFileSync(constantsPath, constants);

console.log(`Synced version ${version}`);
