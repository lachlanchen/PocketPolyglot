#!/usr/bin/env node
// Generate textless cover backgrounds through AgInTiFlow, then compose stable book covers.

import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const ROOT = path.resolve(path.dirname(__filename), "../..");
const DEFAULT_AGINTI_ROOT = path.resolve(ROOT, "../Agent/AgInTiFlow");

const THEME_HINTS = {
  "shiji-aginti":
    "ancient Chinese historian's desk, bamboo slips, bronze vessel, jade ornament, ink wash mountains, dignified Han dynasty atmosphere",
  "genji-modern":
    "Heian court elegance, moonlit palace screens, wisteria, silk fan, subtle gold and indigo pigments, classical Japanese refinement",
  "the-old-capital":
    "Kyoto old capital, cedar trunks, violets, woven kimono pattern, quiet temple wood and spring light",
  "izu-no-odori":
    "Izu mountain road after rain, travel cloak, lantern glow, distant dancer silhouette, lyrical early modern Japanese atmosphere",
  kinkakuji:
    "gold pavilion reflected on dark water, black pine, restrained winter light, psychological modernist tension",
  "rashomon-stories":
    "ancient Kyoto gate in rain, worn timber, twilight clouds, moral ambiguity, literary short-story atmosphere",
  kojiki:
    "ancient Japanese myth scroll, magatama beads, sea foam, torii shadow, sacred old paper and mineral pigments",
  "nihon-shoki":
    "ancient Japanese imperial chronicle, sacred court scrolls, bronze mirror, mountain shrine mist, early Yamato myth-history atmosphere, refined mineral pigments on aged paper",
  "woman-in-the-dunes":
    "abstract sand dunes, buried wooden house geometry, rope, wind-carved texture, existential modern Japanese mood",
  "chumon-no-ooi-ryoriten":
    "mysterious forest restaurant entrance, polished brass signs without readable text, whimsical yet uncanny children's tale mood",
  "ginga-tetsudo":
    "night train crossing a river of stars, deep blue sky, lantern-lit carriage, quiet celestial railway",
  "sishu-jizhu":
    "Confucian classics, bamboo slips, inkstone, Song dynasty study, austere scholarly texture",
  "shui-jing-zhu":
    "ancient Chinese river geography, winding waterways through misty mountains, annotated silk map fragments, scholar-geographer's desk with bamboo slips and inkstone, Northern Wei historical atmosphere, refined ink-wash and restrained mineral pigments",
  chuci:
    "Chu lacquerware elegance, deep southern river mist, orchid and angelica, phoenix-feather curves, bronze bells, silk manuscript fragments, Qu Yuan's exile-poetry atmosphere, dark cinnabar, black, jade green, and restrained gold",
  shijing:
    "ancient songs and fields of the Zhou world, reeds by a riverbank, millet and mulberry leaves, bronze ritual vessel, simple court music, old bamboo-slip anthology, tender folk-song atmosphere, restrained jade green, warm earth, pale gold, and ink-wash texture",
  "tangshi-sanbai":
    "Tang dynasty poetry anthology, moonlit pavilion, distant frontier mountains, river boat, plum blossom and wine cup, scholar's desk with brush and folded paper, luminous regulated-verse elegance, mineral blue, ink black, moon silver, and restrained cinnabar",
  "platform-sutra":
    "Chan Buddhist scripture atmosphere, quiet monastery hall, lotus pond at dawn, empty meditation seat, old sutra paper, incense smoke, warm gold and ink-black restraint, contemplative Southern school Zen feeling",
  "vimalakirti-sutra":
    "Mahayana Buddhist scripture atmosphere, refined lay sage's room, lotus light, celestial canopy abstraction, old Sanskrit and Chinese sutra-paper texture without readable letters, luminous compassion and nonduality, mineral blue, gold, and dark ink",
  mudanting:
    "Ming dynasty Kunqu dream-romance atmosphere, moonlit peony garden, quiet pavilion, silk sleeves implied by flowing forms, refined theatrical beauty, tender longing and resurrection imagery, rose, jade green, old gold, and ink-wash restraint",
  xixiangji:
    "Yuan drama Western Chamber atmosphere, moonlit monastery courtyard, red paper lantern glow without readable writing, scholar's travel desk, folded fan, distant chamber screen, elegant romantic tension, cinnabar, indigo, warm gold, and old paper texture",
  manyoshu:
    "Nara-era poetry anthology atmosphere, pampas grass and autumn wind, old travel road, sea cliffs, mountain mist, court manuscript paper, understated ancient Japanese lyric feeling, mineral blue, pale grass green, warm earth, and soft ink texture",
  "kokin-wakashu":
    "Heian waka anthology atmosphere, cherry blossoms over layered paper, court poetry screens, soft garden water, refined seasonal elegance, subtle gold dust, pale pink, celadon, and deep ink with no readable calligraphy",
  bible:
    "ancient scripture atmosphere, open parchment scrolls, olive branch, desert dawn light, quiet stone path, restrained indigo, warm gold, and deep ink, contemplative sacred-book mood without readable letters",
  "red-rising-1":
    "Mars mine tunnels, red dust, rising rebellion, distant domed city, cinematic science-fiction atmosphere, austere red and black palette",
  "red-rising-2":
    "golden imperial fleet above Mars, dramatic sunlit armor silhouettes, political intrigue, orbital grandeur, refined science-fiction editorial mood",
  "red-rising-3":
    "morning star over Mars, fractured red horizon, liberation fleet, hopeful yet severe science-fiction atmosphere, restrained crimson and gold",
  "japanese-history":
    "layered Japanese history, Jomon pottery texture, Heian screen, samurai silhouette, Meiji modern linework, museum-quality historical design",
  "spring-snow":
    "Taisho-era elegance, falling snow, white camellia, aristocratic mansion garden, restrained romantic melancholy, refined Japanese literary cover",
  "inugami-curse":
    "misty lakeside estate, old family crest impression without readable symbols, dark water, inheritance mystery, classic Japanese detective atmosphere",
  "i-am-a-cat":
    "Meiji study room, scholar's desk, amused cat perspective, ink books and tatami, witty Japanese literary mood",
  botchan:
    "Meiji school town, hot-spring steam, energetic young teacher, tramline and classroom geometry, lively satirical Japanese novel atmosphere",
  "gone-with-the-wind":
    "American Civil War era Southern estate silhouette, wind-swept red earth, magnolia and distant flames, sweeping historical romance mood",
  "one-hundred-years-of-solitude":
    "Macondo under tropical rain and golden afternoon light, yellow butterflies, old colonial house, banana leaves, magical realist atmosphere, warm ochre and emerald palette",
  "wuthering-heights":
    "windswept Yorkshire moor, storm clouds, heather, lonely stone farmhouse silhouette, gothic romantic tension, restrained slate green and violet-gray palette",
  "jane-eyre":
    "Victorian manor corridor, rain against tall windows, governess silhouette, candlelit library, restrained gothic romance atmosphere, deep green and warm amber palette",
  "a-game-of-thrones":
    "grim medieval fantasy court intrigue, iron throne silhouette without readable symbols, snow-dark northern forest, dragon-scale texture, red comet glow, austere black, steel, and crimson palette",
  "the-count-of-monte-cristo":
    "Mediterranean prison fortress and sea cliffs, hidden treasure chest glow, elegant nineteenth-century adventure intrigue, moonlit blue and antique gold palette",
  "notre-dame-de-paris":
    "Gothic cathedral towers and rose window light over medieval Paris, stone gargoyles, candlelit shadows, tragic romantic grandeur, deep ultramarine and warm amber palette",
  "les-miserables":
    "nineteenth-century Paris streets at dawn, barricade silhouettes, worn cobblestones, humane revolutionary drama, misty blue-gray atmosphere with small warm lantern lights",
};

function parseArgs(argv) {
  const args = {
    books: [],
    force: false,
    dryRun: false,
    keepRaw: false,
    provider: process.env.AGINTI_AUX_PROVIDER || "grsai",
    model: process.env.AGINTI_AUX_MODEL || "nano-banana-2",
    agintiRoot: process.env.AGINTIFLOW_ROOT || DEFAULT_AGINTI_ROOT,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const item = argv[i];
    if (item === "--book") args.books.push(argv[++i]);
    else if (item === "--force") args.force = true;
    else if (item === "--dry-run") args.dryRun = true;
    else if (item === "--keep-raw") args.keepRaw = true;
    else if (item === "--provider") args.provider = argv[++i];
    else if (item === "--model") args.model = argv[++i];
    else if (item === "--aginti-root") args.agintiRoot = argv[++i];
    else if (item === "--help" || item === "-h") {
      console.log("Usage: node scripts/books/generate_aginti_cover_assets.mjs [--book ID ...] [--force] [--dry-run] [--keep-raw] [--provider grsai|venice] [--model MODEL]");
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${item}`);
    }
  }
  return args;
}

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  const text = fs.readFileSync(filePath, "utf8");
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (!match) continue;
    const key = match[1];
    if (process.env[key]) continue;
    let value = match[2].trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function normalizePlan(plan, bookId) {
  return {
    bookId,
    planPath: plan.__path,
    titleZh: plan.book_title_zh || bookId,
    titleJa: plan.book_title_ja || plan.book_title_zh || bookId,
    author: plan.author || "",
    description: plan.book_description || "",
  };
}

function discoverPlans(selectedBooks) {
  const planFiles = fs
    .readdirSync(path.join(ROOT, "books"), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(ROOT, "books", entry.name, "book-plan.json"))
    .filter((file) => fs.existsSync(file));
  const plans = [];
  for (const file of planFiles) {
    const plan = readJson(file);
    if (plan.launchable !== true) continue;
    plan.__path = file;
    plans.push(normalizePlan(plan, plan.book_id || path.basename(path.dirname(file))));
  }
  const shijiPlanPath = path.join(ROOT, "books", "shiji", "book-plan.json");
  if (fs.existsSync(shijiPlanPath)) {
    const shiji = readJson(shijiPlanPath);
    shiji.__path = shijiPlanPath;
    plans.push(normalizePlan(shiji, "shiji-aginti"));
  }
  const unique = new Map(plans.map((plan) => [plan.bookId, plan]));
  const selected = selectedBooks.length ? selectedBooks : [...unique.keys()];
  return selected
    .map((bookId) => {
      const plan = unique.get(bookId);
      if (!plan) throw new Error(`No launchable plan found for ${bookId}`);
      return plan;
    })
    .sort((a, b) => a.bookId.localeCompare(b.bookId));
}

function promptFor(plan) {
  const hint = THEME_HINTS[plan.bookId] || plan.description || `${plan.titleJa} / ${plan.titleZh}`;
  return [
    "Create a refined textless background illustration for a pocket-size bilingual Chinese-Japanese literary book cover.",
    `Book: ${plan.titleJa} / ${plan.titleZh}. Author: ${plan.author || "unknown"}.`,
    `Visual direction: ${hint}.`,
    "Vertical A6 book cover composition, elegant East Asian printmaking and subtle modern editorial design.",
    "Leave a calm central area suitable for overlaid vertical title typography.",
    "No readable words, no letters, no calligraphy, no captions, no logo, no watermark, no frame text.",
    "High-resolution, rich but restrained color, suitable for XeLaTeX cover art.",
  ].join("\n");
}

function newestGeneratedImage(dir) {
  const files = fs
    .readdirSync(dir)
    .filter((name) => /\.(png|jpe?g|webp)$/i.test(name))
    .map((name) => path.join(dir, name))
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  return files[0] || "";
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  loadEnvFile(path.join(ROOT, ".aginti", ".env"));
  loadEnvFile(path.join(args.agintiRoot, ".env"));
  loadEnvFile(path.join(args.agintiRoot, ".aginti", ".env"));

  const modulePath = path.join(args.agintiRoot, "src", "auxiliary-tools.js");
  const { generateImage } = await import(pathToFileURL(modulePath).href);
  const plans = discoverPlans(args.books);
  const generated = [];

  for (const plan of plans) {
    const coverDir = path.join(ROOT, "assets", "covers", plan.bookId);
    const coverPath = path.join(coverDir, "cover.png");
    const backgroundPath = path.join(coverDir, "background.png");
    if (!args.force && fs.existsSync(coverPath)) {
      console.log(`skip ${plan.bookId}: ${path.relative(ROOT, coverPath)} exists`);
      continue;
    }
    await fsp.mkdir(coverDir, { recursive: true });
    const prompt = promptFor(plan);
    const rawDir = path.join("assets", "covers", plan.bookId, "aginti-raw");
    console.log(`generate ${plan.bookId}`);
    const result = await generateImage(
      {
        provider: args.provider,
        model: args.model,
        prompt,
        outputDir: rawDir,
        outputStem: "background",
        aspectRatio: "3:4",
        imageSize: "2K",
        dryRun: args.dryRun,
      },
      {
        commandCwd: ROOT,
        allowFileTools: true,
        workspaceWritePolicy: "allow",
        sandboxMode: "host",
      },
    );
    if (args.dryRun) {
      console.log(`dry-run ${plan.bookId}: ${result.manifestPath}`);
      continue;
    }
    if (!result.ok) throw new Error(`generate_image failed for ${plan.bookId}: ${JSON.stringify(result)}`);
    const imagePath = result.imagePaths?.[0] ? path.join(ROOT, result.imagePaths[0]) : newestGeneratedImage(path.join(ROOT, rawDir));
    if (!imagePath || !fs.existsSync(imagePath)) throw new Error(`No generated image found for ${plan.bookId}`);
    await fsp.copyFile(imagePath, backgroundPath);

    const compose = spawnSync(
      "python3",
      [
        "scripts/books/compose_book_cover.py",
        "--plan",
        path.relative(ROOT, plan.planPath),
        "--background",
        path.relative(ROOT, backgroundPath),
        "--output",
        path.relative(ROOT, coverPath),
        "--book-id",
        plan.bookId,
      ],
      { cwd: ROOT, encoding: "utf8" },
    );
    if (compose.status !== 0) {
      process.stderr.write(compose.stdout || "");
      process.stderr.write(compose.stderr || "");
      throw new Error(`Cover composition failed for ${plan.bookId}`);
    }
    process.stdout.write(compose.stdout || "");
    await fsp.writeFile(
      path.join(coverDir, "cover-prompt.txt"),
      `${prompt}\n`,
      "utf8",
    );
    if (!args.keepRaw) {
      await fsp.rm(path.join(ROOT, rawDir), { recursive: true, force: true });
    }
    generated.push(path.relative(ROOT, coverPath));
  }

  console.log(JSON.stringify({ generated }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
