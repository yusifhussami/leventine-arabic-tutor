# Levantine Arabic tutor

This is the notebook I use between lessons. After class I paste the new words in Arabizi, each one with its English meaning. Before the next class I pick a word and try to write a sentence with it.

The page is a small Mac window that runs on this computer. Nothing about the lessons is sent anywhere except the sentence check, which goes to OpenRouter.

## Use it

```bash
python3 -m lexicon.serve
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765).

- **Today** is where a lesson gets pasted. One line is `baza5 = fancy`. A line can also chain several pairs. Preview shows the split before you save.
- **Words** lists everything saved, grouped by the lesson date. Edit changes the Arabizi or the English on that word. A spelling with a space is stored as a phrase.
- **Practice** opens when you click a word. Similar meanings are listed, then you type a sentence and check it.

The next Preply or Arabic lesson shows in the side column after you paste the private Google Calendar iCal link. That link stays in the local database. It is not printed on the page and it is not included in errors.

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
