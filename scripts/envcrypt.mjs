// Encrypts .env into .env.enc (safe to commit) and back, with a passphrase.
//   node scripts/envcrypt.mjs lock     .env -> .env.enc
//   node scripts/envcrypt.mjs unlock   .env.enc -> .env (an existing, different .env is kept as .env.bak)
// Use the secrets.ps1 / secrets.sh wrappers: they fall back to Docker when Node isn't installed.
// The passphrase is asked for (hidden); ENV_PASSPHRASE is read instead when set, for scripts.
//
// Format: "bpa-env-v1" line, then base64 of salt (16) | iv (12) | GCM tag (16) | ciphertext.
// Key: scrypt(passphrase, salt, N=2^17, r=8, p=1). A wrong passphrase or an edited file fails the GCM check.
import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from "node:crypto";
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import readline from "node:readline";

const ROOT = resolve(import.meta.dirname, "..");
const PLAIN = resolve(ROOT, ".env");
const LOCKED = resolve(ROOT, ".env.enc");
const HEADER = "bpa-env-v1";
const MIN_LENGTH = 12;

function key(passphrase, salt) {
  return scryptSync(passphrase.normalize("NFC"), salt, 32, { N: 2 ** 17, r: 8, p: 1, maxmem: 256 * 1024 * 1024 });
}

function encrypt(text, passphrase) {
  const salt = randomBytes(16);
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(passphrase, salt), iv);
  const data = Buffer.concat([cipher.update(text, "utf8"), cipher.final()]);
  const blob = Buffer.concat([salt, iv, cipher.getAuthTag(), data]).toString("base64");
  return `${HEADER}\n${blob.match(/.{1,76}/g).join("\n")}\n`;
}

function decrypt(file, passphrase) {
  const [header, ...lines] = file.trim().split(/\r?\n/);
  if (header !== HEADER) throw new Error(".env.enc isn't in the expected format.");
  const raw = Buffer.from(lines.join(""), "base64");
  const salt = raw.subarray(0, 16);
  const iv = raw.subarray(16, 28);
  const tag = raw.subarray(28, 44);
  const decipher = createDecipheriv("aes-256-gcm", key(passphrase, salt), iv);
  decipher.setAuthTag(tag);
  try {
    return Buffer.concat([decipher.update(raw.subarray(44)), decipher.final()]).toString("utf8");
  } catch {
    throw new Error("Wrong passphrase, or .env.enc was changed.");
  }
}

/** Ask without echoing what's typed. */
function ask(prompt) {
  if (!process.stdin.isTTY) {
    throw new Error("No terminal to ask for the passphrase. Run it in a terminal, or set ENV_PASSPHRASE.");
  }
  return new Promise((done) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });
    rl._writeToOutput = (s) => {
      if (s.startsWith(prompt)) rl.output.write(prompt);
    };
    rl.question(prompt, (answer) => {
      rl.close();
      process.stdout.write("\n");
      done(answer);
    });
  });
}

async function passphrase(confirm) {
  if (process.env.ENV_PASSPHRASE) return process.env.ENV_PASSPHRASE;
  const first = await ask("Passphrase: ");
  if (confirm) {
    if (first.length < MIN_LENGTH) throw new Error(`Use at least ${MIN_LENGTH} characters; a few random words work well.`);
    if ((await ask("Same passphrase again: ")) !== first) throw new Error("The two passphrases don't match.");
  }
  return first;
}

async function main(command) {
  if (command === "lock") {
    if (!existsSync(PLAIN)) throw new Error("There's no .env to encrypt.");
    const text = readFileSync(PLAIN, "utf8");
    writeFileSync(LOCKED, encrypt(text, await passphrase(true)));
    console.log("Wrote .env.enc. Commit it; .env itself stays out of git.");
  } else if (command === "unlock") {
    if (!existsSync(LOCKED)) throw new Error("There's no .env.enc to decrypt.");
    const text = decrypt(readFileSync(LOCKED, "utf8"), await passphrase(false));
    if (existsSync(PLAIN) && readFileSync(PLAIN, "utf8") !== text) {
      renameSync(PLAIN, `${PLAIN}.bak`);
      console.log("Your previous .env is kept as .env.bak.");
    }
    writeFileSync(PLAIN, text);
    console.log("Wrote .env.");
  } else {
    throw new Error("Use: lock (.env -> .env.enc) or unlock (.env.enc -> .env).");
  }
}

main(process.argv[2]).catch((e) => {
  console.error(e.message);
  process.exit(1);
});
