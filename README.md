# Sawt

Sawt is the notebook I use between Levantine lessons. After class I paste the new words in Arabizi, each one with its English meaning. Before the next class I pick a word and try to write a sentence with it.

The page is a small window that runs on this computer. Words and the calendar link stay here. A sentence check, a Talk reply, and the spoken Arabic go to OpenRouter.

## Use it

```bash
python3 -m lexicon.serve
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

- **Today** is where a lesson gets pasted. One line is `baza5 = fancy`. A line can also chain several pairs. Preview shows the split before you save.
- **Words** lists everything saved, grouped by the lesson date. Edit changes the Arabizi or the English on that word. A spelling with a space is stored as a phrase.
- **Practice** opens when you click a word. Similar meanings are listed, then you type a sentence and check it. Talk speaks the reply as an mp3, so a phone hears it too.

The next Preply or Arabic lesson shows in the side column after you paste the private Google Calendar iCal link. That link stays in the local database. It is not printed on the page and it is not included in errors.

## On a phone

`127.0.0.1` only works on the computer running the notebook. On the same Wi‑Fi, start it on the local network and open that address on the phone:

```bash
python3 -m lexicon.serve --host 0.0.0.0
```

Then visit `http://` followed by this computer's local IP and `:8765`. Anyone who opens that address can use your words and your API key, so don't use it on a public network. The voice is Gemini Flash Lite TTS, about a cent a minute.

## Keep the key local

Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. `GEMINI_API_KEY` is accepted as the same key. Sentence checks use OpenRouter and the model `google/gemini-3.5-flash-lite`.

These files stay on the machine and are ignored by git:

| File | What it holds |
| --- | --- |
| `.env` | The API key |
| `lexicon.db` | Saved words, judgments, and the calendar link |

`data/vocabulary.csv` is the older sheet export. It has Arabizi and English only, no account details.

Python 3.9 is enough. There are no extra packages to install.

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
