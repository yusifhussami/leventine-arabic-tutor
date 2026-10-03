# Sawt

Sawt is the notebook I use between Levantine lessons. After class I paste the new words in Arabizi, each one with its English meaning. Before the next class I talk with those words, or write a sentence with one of them.

The page runs on this computer. Words and the calendar link stay in a local database. Sentence checks, Talk replies, and spoken Arabic go to OpenRouter.

## Use it

```bash
python3 -m lexicon.serve
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

- **Today** is where a lesson gets pasted. `baza5 = fancy` is one pair. `practice - tadreeb` is English, then a dash, then Arabizi. A line can mix both. Preview shows the split before you save. The same spelling with the same meaning is not stored twice.
- **Words** lists everything saved, grouped by the lesson date. Edit changes the Arabizi or the English. A spelling with a space is stored as a phrase.
- **Practice** is the voice page. Tap the circle to talk. Coffee, Restaurant, Shop, and Taxi put Sawt in that place. You can also type a line, or open a saved word and check one sentence. Dark mode is the switch in the toolbar.

Arabizi digits in this notebook: 2 ء/أ, 3 ع, 3' غ, 5 خ, 6 ط, 7 ح, 8 ق, 9 ص, 9' ض. Long ee and oo stay as ee and oo. كيفك is keefak.

The next Preply or Arabic lesson shows in the side column after you paste the private Google Calendar iCal link. That link stays in the local database. It is not printed on the page and it is not included in errors.

## On a phone

`127.0.0.1` only works on the computer running the notebook. On the same Wi‑Fi:

```bash
python3 -m lexicon.serve --host 0.0.0.0
```

Then open `http://` followed by this computer's local IP and `:8765`. Anyone on that address can use your words and your API key, so keep it off public networks. Speech uses Gemini Flash Lite TTS, about a cent a minute.

## Keep the key local

Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. `GEMINI_API_KEY` is accepted as the same key.

| Call | Model |
| --- | --- |
| Sentence check and Talk | `google/gemini-3.5-flash-lite` |
| Spoken Arabic | `google/gemini-3.8-flash-lite-tts` |

These files stay on the machine and are ignored by git:

| File | What it holds |
| --- | --- |
| `.env` | The API key |
| `lexicon.db` | Saved words, judgments, and the calendar link |

`data/vocabulary.csv` is the older sheet export. It has Arabizi and English only, no account details.

Python 3.9 is enough. There are no extra packages to install.

## Decisions

Why each model, and how the voice loop is wired: [docs/decisions](docs/decisions).

## Tests

```bash
python3 -m unittest discover -s tests
```

## Older terminal commands

The notebook replaced the day-to-day way of practicing, but the earlier commands still load the sheet and run a drill in the terminal:

```bash
python3 -m lexicon.load data/vocabulary.csv lexicon.db
python3 -m lexicon.drill data/vocabulary.csv lexicon.db
```
