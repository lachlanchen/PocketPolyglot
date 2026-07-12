# Imported Modern Queues - 2026-07-12

This records the ZhJpBook task preparation for the leadership, world classics, and history downloads first organized in `../Books`.

Original files remain in `../Books` and ignored `sources/`; only queue metadata, manifests, and this reference note are tracked.

## Queue Files

| Queue | Model | Workers | Books | Source spine | Output languages |
| --- | --- | ---: | ---: | --- | --- |
| `data/source-plan/imported-history-trilingual-queue.json` | `gpt-5.3-codex-spark low` | 10 | 2 | `en` | `en, ja, zh` |
| `data/source-plan/imported-leadership-trilingual-queue.json` | `gpt-5.5 low` | 10 | 12 | `en` | `en, ja, zh` |
| `data/source-plan/imported-world-classics-trilingual-queue.json` | `gpt-5.5 low` | 10 | 21 | `en` | `en, ja, zh` |

## Prepared Chunk Totals

All three queues were prepared with
`scripts/interlinear/prepare_modern_nonfiction_trilingual.py --update-queue`.
They are launchable but no writer workers were started.

| Queue | Status | Books | Chunks | Missing manifests |
| --- | --- | ---: | ---: | ---: |
| `imported-history-trilingual-queue.json` | `chunked_launchable` | 2 | 997 | 0 |
| `imported-leadership-trilingual-queue.json` | `chunked_launchable` | 12 | 2064 | 0 |
| `imported-world-classics-trilingual-queue.json` | `chunked_launchable` | 21 | 9515 | 0 |
| **Total** |  | **35** | **12576** | **0** |

## Books

| Queue | Priority | Book ID | English title | Source path | References |
| --- | ---: | --- | --- | --- | ---: |
| `imported-history-trilingual-queue.json` | 1 | `rise-fall-ancient-egypt` | The Rise and Fall of Ancient Egypt | `sources/world-history/ancient-egypt/en/The Rise and Fall of Ancient Egypt - Toby Wilkinson.pdf` | 0 |
| `imported-history-trilingual-queue.json` | 2 | `lost-enlightenment-central-asia` | Lost Enlightenment: Central Asia's Golden Age from the Arab Conquest to Tamerlane | `sources/world-history/central-asia/en/Lost Enlightenment - S Frederick Starr.pdf` | 0 |
| `imported-leadership-trilingual-queue.json` | 1 | `seven-habits-effective-people` | The 7 Habits of Highly Effective People | `sources/leadership/7-habits/en/The 7 Habits of Highly Effective People - Stephen R Covey and Sean Covey.epub` | 1 |
| `imported-leadership-trilingual-queue.json` | 2 | `multipliers-leadership` | Multipliers | `sources/leadership/multipliers/en/Multipliers - Liz Wiseman.pdf` | 0 |
| `imported-leadership-trilingual-queue.json` | 3 | `five-dysfunctions-team` | The Five Dysfunctions of a Team | `sources/leadership/five-dysfunctions-team/en/The Five Dysfunctions of a Team - Patrick Lencioni.pdf` | 1 |
| `imported-leadership-trilingual-queue.json` | 4 | `leadership-21-laws` | The 21 Irrefutable Laws of Leadership | `sources/leadership/21-irrefutable-laws/en/The 21 Irrefutable Laws of Leadership - John C Maxwell.pdf` | 0 |
| `imported-leadership-trilingual-queue.json` | 5 | `good-to-great-leadership` | Good to Great | `sources/leadership/good-to-great/en/Good to Great - Jim Collins.pdf` | 0 |
| `imported-leadership-trilingual-queue.json` | 6 | `radical-candor` | Radical Candor | `sources/leadership/radical-candor/en/Radical Candor - Kim Scott.pdf` | 0 |
| `imported-leadership-trilingual-queue.json` | 7 | `leadership-self-deception` | Leadership and Self-Deception | `sources/leadership/leadership-and-self-deception/en/Leadership and Self-Deception - The Arbinger Institute.pdf` | 0 |
| `imported-leadership-trilingual-queue.json` | 8 | `leadership-challenge` | The Leadership Challenge | `sources/leadership/leadership-challenge/en/The Leadership Challenge - Kouzes and Posner.epub` | 1 |
| `imported-leadership-trilingual-queue.json` | 9 | `leaders-eat-last` | Leaders Eat Last | `sources/leadership/leaders-eat-last/en/Leaders Eat Last - Simon Sinek.epub` | 0 |
| `imported-leadership-trilingual-queue.json` | 10 | `turn-the-ship-around` | Turn the Ship Around! | `sources/leadership/turn-the-ship-around/en/Turn the Ship Around - L David Marquet.epub` | 0 |
| `imported-leadership-trilingual-queue.json` | 11 | `on-becoming-a-leader` | On Becoming a Leader | `sources/leadership/on-becoming-a-leader/en/On Becoming a Leader - Warren Bennis.pdf` | 0 |
| `imported-leadership-trilingual-queue.json` | 12 | `effective-executive-drucker` | The Effective Executive | `sources/leadership/effective-executive/en/The Effective Executive - Peter F Drucker.pdf` | 0 |
| `imported-world-classics-trilingual-queue.json` | 1 | `don-quixote` | Don Quixote | `sources/world-literature/don-quixote/en/Don Quixote.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 2 | `robinson-crusoe` | Robinson Crusoe | `sources/world-literature/robinson-crusoe/en/Robinson Crusoe.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 3 | `oliver-twist` | Oliver Twist | `sources/world-literature/oliver-twist/en/Oliver Twist.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 4 | `pride-and-prejudice` | Pride and Prejudice | `sources/world-literature/pride-and-prejudice/en/Pride and Prejudice.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 5 | `great-gatsby` | The Great Gatsby | `sources/world-literature/great-gatsby/en/The Great Gatsby.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 6 | `the-stranger` | The Stranger | `sources/world-literature/the-stranger/en/The Stranger.pdf` | 0 |
| `imported-world-classics-trilingual-queue.json` | 7 | `old-man-and-the-sea` | The Old Man and the Sea | `sources/world-literature/old-man-and-the-sea/en/The Old Man and the Sea.pdf` | 0 |
| `imported-world-classics-trilingual-queue.json` | 8 | `steppenwolf` | Steppenwolf | `sources/world-literature/steppenwolf/en/Steppenwolf.pdf` | 0 |
| `imported-world-classics-trilingual-queue.json` | 9 | `swanns-way` | Swann's Way | `sources/world-literature/swanns-way/en/Swann's Way.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 10 | `gullivers-travels` | Gulliver's Travels | `sources/world-literature/gullivers-travels/en/Gulliver's Travels.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 11 | `david-copperfield` | David Copperfield | `sources/world-literature/david-copperfield/en/David Copperfield.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 12 | `tale-of-two-cities` | A Tale of Two Cities | `sources/world-literature/tale-of-two-cities/en/A Tale of Two Cities.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 13 | `resurrection` | Resurrection | `sources/world-literature/resurrection/en/Resurrection.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 14 | `brothers-karamazov` | The Brothers Karamazov | `sources/world-literature/brothers-karamazov/en/The Brothers Karamazov.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 15 | `crime-and-punishment` | Crime and Punishment | `sources/world-literature/crime-and-punishment/en/Crime and Punishment.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 16 | `red-and-black` | The Red and the Black | `sources/world-literature/red-and-black/en/The Red and the Black.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 17 | `madame-bovary` | Madame Bovary | `sources/world-literature/madame-bovary/en/Madame Bovary.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 18 | `moon-and-sixpence` | The Moon and Sixpence | `sources/world-literature/moon-and-sixpence/en/The Moon and Sixpence.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 19 | `anna-karenina` | Anna Karenina | `sources/world-literature/anna-karenina/en/Anna Karenina.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 20 | `three-musketeers` | The Three Musketeers | `sources/world-literature/three-musketeers/en/The Three Musketeers.epub` | 1 |
| `imported-world-classics-trilingual-queue.json` | 21 | `war-and-peace` | War and Peace | `sources/world-literature/war-and-peace/en/War and Peace.epub` | 1 |

## Copied Source Files

| Status | Destination | Size | SHA-256 |
| --- | --- | ---: | --- |
| `existing_same` | `sources/world-history/ancient-egypt/en/The Rise and Fall of Ancient Egypt - Toby Wilkinson.pdf` | 35326334 | `441cb39ebdd3125b` |
| `existing_same` | `sources/world-history/central-asia/en/Lost Enlightenment - S Frederick Starr.pdf` | 32709527 | `72578798fc487a47` |
| `existing_same` | `sources/leadership/7-habits/en/The 7 Habits of Highly Effective People - Stephen R Covey and Sean Covey.epub` | 11941907 | `565ef670fa0b4f45` |
| `existing_same` | `sources/leadership/7-habits/en/The 7 Habits of Highly Effective People - Stephen R Covey and Sean Covey.pdf` | 16261902 | `72de30794b871237` |
| `existing_same` | `sources/leadership/multipliers/en/Multipliers - Liz Wiseman.pdf` | 8038540 | `a28c4c446a3b5400` |
| `existing_same` | `sources/leadership/five-dysfunctions-team/en/The Five Dysfunctions of a Team - Patrick Lencioni.pdf` | 5850237 | `48dccb61cde8a9ee` |
| `existing_same` | `sources/leadership/five-dysfunctions-team/en/The Five Dysfunctions of a Team - Patrick Lencioni - large reference.pdf` | 48782227 | `5d55a447e5e7cb33` |
| `existing_same` | `sources/leadership/21-irrefutable-laws/en/The 21 Irrefutable Laws of Leadership - John C Maxwell.pdf` | 1627264 | `b9e794ff599c989e` |
| `existing_same` | `sources/leadership/good-to-great/en/Good to Great - Jim Collins.pdf` | 9098531 | `9f43faddc85b9c2c` |
| `existing_same` | `sources/leadership/radical-candor/en/Radical Candor - Kim Scott.pdf` | 8552806 | `a8e9d7b0c5bc9a1f` |
| `existing_same` | `sources/leadership/leadership-and-self-deception/en/Leadership and Self-Deception - The Arbinger Institute.pdf` | 8419588 | `7b2a24c4ecd92f0b` |
| `existing_same` | `sources/leadership/leadership-challenge/en/The Leadership Challenge - Kouzes and Posner.epub` | 1567423 | `d3cb16cc7b90fced` |
| `existing_same` | `sources/leadership/leadership-challenge/en/The Leadership Challenge - Kouzes and Posner.pdf` | 3522233 | `6d1499d2b352db5e` |
| `existing_same` | `sources/leadership/leaders-eat-last/en/Leaders Eat Last - Simon Sinek.epub` | 1804464 | `aaa01b5c2499a60c` |
| `existing_same` | `sources/leadership/turn-the-ship-around/en/Turn the Ship Around - L David Marquet.epub` | 482008 | `ea927cd8a7cc7366` |
| `existing_same` | `sources/leadership/on-becoming-a-leader/en/On Becoming a Leader - Warren Bennis.pdf` | 957167 | `0ab8af780402444e` |
| `existing_same` | `sources/leadership/effective-executive/en/The Effective Executive - Peter F Drucker.pdf` | 4353507 | `4b7ed2cd4d6f3562` |
| `existing_same` | `sources/world-literature/don-quixote/en/Don Quixote.epub` | 46083520 | `1f2e274bd13e54c9` |
| `existing_same` | `sources/world-literature/don-quixote/en/reference/Miguel de Cervantes - Don Quixote.pdf` | 37144127 | `12bb8bfd3eab146b` |
| `existing_same` | `sources/world-literature/robinson-crusoe/en/Robinson Crusoe.epub` | 339846 | `13dc9a555bac3141` |
| `existing_same` | `sources/world-literature/robinson-crusoe/en/reference/Daniel Defoe - Robinson Crusoe - Signet Classics 2008.epub` | 534583 | `1140a5b49df64f64` |
| `existing_same` | `sources/world-literature/oliver-twist/en/Oliver Twist.epub` | 507698 | `befb2494f499ea95` |
| `existing_same` | `sources/world-literature/oliver-twist/en/reference/Charles Dickens - Oliver Twist - Oakshot Press.epub` | 4300725 | `6474691655e072e1` |
| `existing_same` | `sources/world-literature/pride-and-prejudice/en/Pride and Prejudice.epub` | 24835597 | `9cb123f154e60a23` |
| `existing_same` | `sources/world-literature/pride-and-prejudice/en/reference/Jane Austen - Pride and Prejudice - Cambridge Edition 2006.pdf` | 1623108 | `9c4d742c4d7ecf72` |
| `existing_same` | `sources/world-literature/great-gatsby/en/The Great Gatsby.epub` | 353400 | `d650f5166517eac7` |
| `existing_same` | `sources/world-literature/great-gatsby/en/reference/F Scott Fitzgerald - The Great Gatsby - 2021.pdf` | 6880777 | `be540867b846f611` |
| `existing_same` | `sources/world-literature/the-stranger/en/The Stranger.pdf` | 756950 | `c686a488a22e59e3` |
| `existing_same` | `sources/world-literature/old-man-and-the-sea/en/The Old Man and the Sea.pdf` | 49272224 | `7ec2f7048a73ccf8` |
| `existing_same` | `sources/world-literature/steppenwolf/en/Steppenwolf.pdf` | 705958 | `bb02d0caa4cd3349` |
| `copied` | `sources/world-literature/swanns-way/en/Swann's Way.epub` | 522382 | `86077c7c949f8ca6` |
| `copied` | `sources/world-literature/swanns-way/en/reference/Marcel Proust - Swanns Way - Modern Library 1992.pdf` | 1815220 | `a7cb005d2cdd3d00` |
| `copied` | `sources/world-literature/gullivers-travels/en/Gulliver's Travels.epub` | 740007 | `35c8495c668681f3` |
| `copied` | `sources/world-literature/gullivers-travels/en/reference/Jonathan Swift - Gullivers Travels - Oxford Worlds Classics 2005.pdf` | 1915060 | `12876ce80e8b3240` |
| `copied` | `sources/world-literature/david-copperfield/en/David Copperfield.epub` | 9412907 | `60efd9a70e79894c` |
| `copied` | `sources/world-literature/david-copperfield/en/reference/Charles Dickens - David Copperfield - 1997.pdf` | 4213517 | `e30cd2c725dbdfb0` |
| `copied` | `sources/world-literature/tale-of-two-cities/en/A Tale of Two Cities.epub` | 7922073 | `a99bbdf4495411b4` |
| `copied` | `sources/world-literature/tale-of-two-cities/en/reference/Charles Dickens - A Tale of Two Cities - Bunny Books 2010.pdf` | 1034267 | `5da8e5f8089d45e4` |
| `copied` | `sources/world-literature/resurrection/en/Resurrection.epub` | 473286 | `660e2eb5e2ebc41e` |
| `copied` | `sources/world-literature/resurrection/en/reference/Leo Tolstoy - Resurrection - Floating Press 2011.pdf` | 1386055 | `24b1afc2aa1c25c2` |
| `copied` | `sources/world-literature/brothers-karamazov/en/The Brothers Karamazov.epub` | 959595 | `c556f03d6b7195c6` |
| `copied` | `sources/world-literature/brothers-karamazov/en/reference/Fyodor Dostoevsky - The Brothers Karamazov - Planet PDF 2004.pdf` | 3217626 | `bb72f36f52609f09` |
| `copied` | `sources/world-literature/crime-and-punishment/en/Crime and Punishment.epub` | 783876 | `a057f27e961a2343` |
| `copied` | `sources/world-literature/crime-and-punishment/en/reference/Fyodor Dostoevsky - Crime and Punishment - Barnes and Noble 1994.pdf` | 1398750 | `9f5e2d2e4468e1fd` |
| `copied` | `sources/world-literature/red-and-black/en/The Red and the Black.epub` | 692969 | `7f99664b96399191` |
| `copied` | `sources/world-literature/red-and-black/en/reference/Stendhal - The Red and the Black - Modern Library 2004.pdf` | 1937042 | `156895421ed85795` |
| `copied` | `sources/world-literature/madame-bovary/en/Madame Bovary.epub` | 448630 | `0582875c9d1b045f` |
| `copied` | `sources/world-literature/madame-bovary/en/reference/Gustave Flaubert - Madame Bovary - 2005.pdf` | 1473521 | `55d7c9837e550a92` |
| `copied` | `sources/world-literature/moon-and-sixpence/en/The Moon and Sixpence.epub` | 468437 | `f38e9b9e7eae3038` |
| `copied` | `sources/world-literature/moon-and-sixpence/en/reference/W Somerset Maugham - The Moon and Sixpence - Penn State 2001.pdf` | 512545 | `bd6f586b8ff8fe3a` |
| `copied` | `sources/world-literature/anna-karenina/en/Anna Karenina.epub` | 1029639 | `ace54fbcc0e26fe3` |
| `copied` | `sources/world-literature/anna-karenina/en/reference/Leo Tolstoy - Anna Karenina - Yale 2014.pdf` | 3199464 | `dc3d0c30ab98206a` |
| `copied` | `sources/world-literature/three-musketeers/en/The Three Musketeers.epub` | 675541 | `a6f13c436356574a` |
| `copied` | `sources/world-literature/three-musketeers/en/reference/Alexandre Dumas - The Three Musketeers - Viking 2006.pdf` | 1940108 | `f8db3facd726348b` |
| `copied` | `sources/world-literature/war-and-peace/en/War and Peace.epub` | 1835872 | `e50c6e888077e996` |
| `copied` | `sources/world-literature/war-and-peace/en/reference/Leo Tolstoy - War and Peace - 1968.pdf` | 452907 | `d60aab88fcab4c77` |
