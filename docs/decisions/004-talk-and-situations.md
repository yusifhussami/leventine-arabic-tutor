# Talk and Situations

## Decision

Default Talk is a Levantine friend on a call. Situations are a separate row (Coffee, Restaurant, Shop, Taxi). Choosing a scene does not replace the friend prompt forever; it adds a scene block for that conversation.

## Why

I tried folding “order a coffee” into Talk itself. That made every Speak start at a counter, which was wrong for normal practice. Reverting Talk and adding Situations under the orb kept both uses.

## How

- Speak / orb with no scene: friend prompt only.
- Coffee (and the others): `scene` is sent on `/api/talk`. `talk()` appends the matching block from `_SCENES` (counter lines, spellings like `ahwe`, `bala sukkar`, `8addeesh`).
- An empty situation starts with a short “speak first” user turn so Sawt opens the scene.
- Corrections still use `correction` and `better`, so a bad order line gets a kinder rewrite in my Arabizi.
