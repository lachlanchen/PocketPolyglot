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
    "serene golden pavilion reflected on still water, black pine, restrained winter light, quiet Kyoto garden atmosphere, refined literary architecture cover, no fire, no violence",
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
  "lushi-chunqiu":
    "Warring States scholarly compendium, bronze ritual vessel, bamboo slips arranged like seasonal calendars, court scholars in a quiet study, cosmological order and practical governance atmosphere, restrained lacquer black, jade green, and warm bronze palette",
  hanfeizi:
    "Legalist Warring States classic, austere court archive, bronze law tablets, bamboo slips, black lacquer desk, cold strategic intelligence and political realism, restrained ink black, bronze, jade gray, and muted cinnabar palette",
  guiguzi:
    "mysterious Warring States strategy and persuasion classic, secluded mountain pass, bamboo slips, shadowed scholar's cave, diplomatic tokens, mist and hidden pathways, subtle tactical atmosphere, deep ink, muted jade, weathered parchment, and restrained gold",
  "sunzi-bingfa":
    "ancient Chinese military classic, bamboo slips, bronze sword guard, misted mountain passes, strategic map lines without readable text, calm disciplined command atmosphere, restrained ink black, bronze, and muted cinnabar palette",
  wuzi:
    "Warring States military classic, austere command tent, bamboo slips, old campaign map lines without readable text, bronze spearhead and inkstone, disciplined strategic atmosphere, muted bronze, black ink, and weathered parchment palette",
  "sunbin-bingfa":
    "Sun Bin military classic, bamboo slips, old chariot wheel shadow, strategic valley map lines without readable text, Warring States tactical atmosphere, restrained bronze, ink black, and muted jade palette",
  simafa:
    "ancient ritual military method, bronze command tablets, orderly army standards without readable symbols, court archive and bamboo slips, restrained Zhou-era discipline, dark ink, aged parchment, and muted cinnabar palette",
  weiliaozi:
    "ancient Chinese military strategy, fortress gate silhouette, bamboo slips, bronze seal, night watch fires on distant walls, disciplined political-strategy atmosphere, restrained black, bronze, and deep red palette",
  "shui-jing-zhu":
    "ancient Chinese river geography, winding waterways through misty mountains, annotated silk map fragments, scholar-geographer's desk with bamboo slips and inkstone, Northern Wei historical atmosphere, refined ink-wash and restrained mineral pigments",
  chuci:
    "Chu lacquerware elegance, deep southern river mist, orchid and angelica, phoenix-feather curves, bronze bells, silk manuscript fragments, Qu Yuan's exile-poetry atmosphere, dark cinnabar, black, jade green, and restrained gold",
  shijing:
    "ancient songs and fields of the Zhou world, reeds by a riverbank, millet and mulberry leaves, bronze ritual vessel, simple court music, old bamboo-slip anthology, tender folk-song atmosphere, restrained jade green, warm earth, pale gold, and ink-wash texture",
  huainanzi:
    "Huainanzi cosmological philosophy, Han dynasty scholarly court, bronze astrolabe, yin-yang cosmogram without readable letters, bamboo slips, jade bi disk, misted mountains and constellations, synthesis of governance, nature, and Daoist thought, deep ink, warm bronze, lapis blue, and restrained gold",
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
  "harry-potter-6":
    "old magical astronomy tower at twilight, half-lit potion book, silver-green candlelight, dark lake and castle silhouettes, melancholy coming-of-age fantasy atmosphere, restrained emerald, indigo, and antique gold palette",
  "harry-potter-7":
    "final dark magical quest, broken wand, forest clearing, ancient castle in distant dawn, silver stag light over mist, solemn heroic fantasy conclusion, restrained indigo, ash gray, and pale gold palette",
  "a-game-of-thrones":
    "grim medieval fantasy court intrigue, iron throne silhouette without readable symbols, snow-dark northern forest, dragon-scale texture, red comet glow, austere black, steel, and crimson palette",
  "the-count-of-monte-cristo":
    "Mediterranean prison fortress and sea cliffs, hidden treasure chest glow, elegant nineteenth-century adventure intrigue, moonlit blue and antique gold palette",
  "notre-dame-de-paris":
    "Gothic cathedral towers and rose window light over medieval Paris, stone gargoyles, candlelit shadows, tragic romantic grandeur, deep ultramarine and warm amber palette",
  "les-miserables":
    "nineteenth-century Paris streets at dawn, barricade silhouettes, worn cobblestones, humane revolutionary drama, misty blue-gray atmosphere with small warm lantern lights",
  "tagore-gitanjali":
    "Bengal devotional poetry, river at dawn, lotus and flowering branches, quiet manuscript page, warm gold and soft blue, contemplative spiritual lyric mood, no readable text",
  "tagore-stray-birds":
    "Tagore aphoristic lyric poems, small birds crossing a wide dawn sky, Bengal riverbank, lotus leaves, floating manuscript pages without readable text, light contemplative mood, pale gold, sky blue, and soft green palette",
  "gibran-the-prophet":
    "Kahlil Gibran's The Prophet, coastal hill town at dawn, cedar branches, open parchment without readable words, quiet spiritual address and luminous Mediterranean air, restrained gold, blue, and warm stone palette",
  "yeats-collected-poems-spark":
    "W. B. Yeats collected poems, Irish lake island twilight, swans over dark water, tower silhouette, Celtic twilight mysticism, refined symbolist lyric atmosphere, silver gray, deep green, muted gold, and ink-blue palette",
  "shelley-selected-poems-gpt55-low":
    "Percy Bysshe Shelley selected poems, west wind over storm-lit sea, cloud and skylark motifs, Romantic revolutionary lyric energy, luminous horizon, restrained indigo, pearl gray, and pale gold palette",
  "ovid-art-of-love-spark":
    "Ovid Ars Amatoria, ancient Roman poetic love manual, marble garden, laurel, folded parchment without readable letters, elegant classical wit and sensual restraint, warm terracotta, ivory, soft rose, and antique gold palette",
  "keats-poems-spark":
    "John Keats poems, Grecian urn silhouette, nightingale in dusky branches, autumn fruit and laurel, sensuous Romantic lyric atmosphere, warm amber, moss green, ivory, and deep violet palette",
  "wilde-poetry-spark":
    "Oscar Wilde poetry, aesthetic movement elegance, peacock feather color, lily, velvet theater curtain abstraction, refined decadent wit without readable text, emerald, indigo, antique gold, and ivory palette",
  "xu-zhimo-poems-spark":
    "Xu Zhimo poetry, Cambridge river bridge at dusk, willow leaves, drifting cloud, Chinese modern lyric romance, ink wash blended with soft watercolor, pale blue, warm gold, and gentle green palette",
  "tsangyang-gyatso-poems-spark":
    "Tsangyang Gyatso poems, Tibetan plateau moonlight, prayer flags as abstract color without readable script, distant monastery silhouette, intimate lyric longing and spiritual solitude, lapis blue, saffron, snow white, and muted crimson palette",
  "english-poetry-anthology-spark":
    "English poetry anthology, open old poetry book without readable words, layered seasons, quill, rose, storm cloud, moonlit field, broad lyrical tradition, restrained editorial collage in deep blue, warm parchment, and muted gold",
  "positioning-battle-for-your-mind":
    "brand positioning and strategy, abstract market map, compass, clean geometric pathways, layered perception diagrams without readable words, thoughtful business strategy atmosphere, restrained blue, graphite, ivory, and warm gold palette",
  "mans-search-for-meaning":
    "abstract philosophical memoir background about resilience and purpose, quiet dawn path toward an open horizon, small warm lantern, distant mountains, empty landscape, humane contemplative atmosphere, no people, no historical scenes, no uniforms, no fences",
};

const IMAGE_TITLE_OVERRIDES = {
  "positioning-battle-for-your-mind": "Positioning / 定位 / ポジショニング",
  kinkakuji: "Japanese literary novel with a golden pavilion motif",
  "mans-search-for-meaning": "Philosophical memoir about resilience and purpose",
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
    titleEn: plan.book_title_en || "",
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
  const titleParts = [plan.titleEn, plan.titleJa, plan.titleZh].filter(Boolean);
  const imageTitle = IMAGE_TITLE_OVERRIDES[plan.bookId] || titleParts.join(" / ");
  return [
    "Create a refined textless background illustration for a pocket-size multilingual LinguaLeaf book cover.",
    `Book: ${imageTitle}. Author: ${plan.author || "unknown"}.`,
    `Visual direction: ${hint}.`,
    "Vertical A6 book cover composition, elegant East Asian printmaking and subtle modern editorial design.",
    "Leave a calm central area suitable for overlaid vertical title typography.",
    "The image itself must contain no readable words, no letters, no title, no subtitle, no calligraphy, no captions, no logo, no watermark, and no frame text.",
    "Do not include seal stamps, red stamp squares, pseudo-writing, single kanji/hanzi marks, or decorative text-like symbols.",
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
    if (result.manifestPath) {
      const manifestPath = path.join(ROOT, result.manifestPath);
      if (fs.existsSync(manifestPath)) {
        const manifest = readJson(manifestPath);
        if (manifest.status === "failed") {
          throw new Error(`generate_image failed for ${plan.bookId}: ${manifest.failureReason || "manifest status failed"}`);
        }
      }
    }
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
