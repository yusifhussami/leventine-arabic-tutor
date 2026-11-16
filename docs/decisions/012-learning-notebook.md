# Learning notebook

Sawt now needs to support lessons with a teacher, grammar rules, sentence homework, and recall of knowledge. Existing `lessons` rows are vocabulary imports. Existing word IDs and card schedules must survive the rework.

## Usage

Capture a teaching session with its words, rules, goal, and homework. Capture creates a writing task that shows the required words and grammar. Save drafts, submit separate attempts, and attach corrections without replacing the original sentences. Recap asks for recall before revealing the saved explanation and records a self-rating.

Words keeps saved vocabulary, Arabic spellings, dictionary search, and word families. Dictionary searches are read-only. Saving a result is explicit. Related forms retain their source, person, meaning, and examples. Missing forms remain editable rather than being manufactured from a root.

## Shape

Use independent learning sessions, rules, tasks, attempts, corrections, recalls, and families. Sessions link vocabulary through snapshots of existing IDs and labels. Legacy imports remain vocabulary imports. A shared additive schema supports SQLite and Postgres. Existing API files dispatch learning and dictionary actions, preserving legacy requests and the twelve-function deployment shape.

New mutations validate ownership and language. Capture is one transaction, including grammar-only sessions and reused words. Drafts use revision checks. Submitted attempts and corrections append history. Retried lesson, writing, and recall commands carry a request key. Word-family edits use revision checks, and dictionary saves reuse an existing word. Rule recall records the explanation shown and uses a simple next-review date. Existing FSRS cards retain their scheduler.

## Synthesis decision

The two independent sketches agreed on preserving vocabulary and card identities. Candidate B provides the smaller storage boundary: knowledge records remain independent of import containers. Candidate A contributes atomic capture, a lesson-centred writing flow, immutable corrections, and snapshots of requirements. The independent cross-judge preferred this combination. A generic knowledge graph and a wholesale card migration were rejected because they add configuration and migration risk without helping the lesson-to-sentence loop.

## Book and dictionary

The scanned reference is Matthew Aldrich's *Levantine Arabic Verbs*. Printed pages 107–114 distinguish perfect, bare imperfect, bi-imperfect, imperative, and participles. The app provides original learning prompts and page references. The private PDF and its page images are not public app assets.

No documented public Arwords API was found. Search uses the existing cached public index and available forms with attribution. Missing forms and incomplete transliteration coverage remain visible. Dictionary forms are evidence; continuous constructions and derivations are not assumed to be universal inflections.

## Implementation reconciliation

The first release uses bounded snapshots for session vocabulary and grammar requirements rather than a generic relationship graph. This keeps historical writing readable after later edits. Read-time duplicate deletion is removed so new links and existing card identities remain stable. Existing import dedup still prevents new duplicate word pairs.
