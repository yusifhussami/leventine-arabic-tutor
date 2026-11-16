/* Learning notebook. All learner text is rendered as text, never HTML. */
(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const state = {
    workspace: null,
    identity: "",
    seq: 0,
    task: null,
    recap: null,
    family: null,
    words: [],
    view: "list",
    session: null,
    dirty: false,
    saving: false,
    timer: null,
  };
  const today = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  const identity = () => `${learningLanguage}:${clerk?.user?.id || "local"}`;
  const uid = () =>
    crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const el = (tag, cls, value) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (value != null) n.textContent = value;
    return n;
  };
  const notice = el("p", "learning-global-status learning-muted");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  $(".panes").before(notice);
  const say = (message, error = false) => {
    notice.textContent = message;
    notice.hidden = !message;
    notice.style.color = error ? "var(--red, #b33)" : "";
  };
  const fail = (error) =>
    say(error.message || "Could not save. Your work is still here.", true);
  async function api(url) {
    const r = await apiFetch(url);
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Could not load. Try again.");
    return data;
  }
  const write = (body) => post("/api/lessons", { ...body, request_id: uid() });
  function btn(label, handler, kind = "secondary") {
    const b = el("button", kind, label);
    b.type = "button";
    b.onclick = async () => {
      if (b.disabled) return;
      b.disabled = true;
      try {
        await handler(b);
      } catch (error) {
        fail(error);
      } finally {
        b.disabled = false;
      }
    };
    return b;
  }
  function field(name, label, value = "", options = {}) {
    const wrapper = el("div", `field ${options.full ? "learning-full" : ""}`);
    const l = el("label", "", label);
    const n = document.createElement(
      options.area ? "textarea" : options.choices ? "select" : "input",
    );
    n.name = name;
    n.id = `learning-${name}-${uid()}`;
    l.htmlFor = n.id;
    if (options.choices)
      for (const [v, caption] of options.choices) {
        const o = el("option", "", caption);
        o.value = v;
        n.append(o);
      }
    else if (!options.area) n.type = options.type || "text";
    n.value = value;
    if (options.required) n.required = true;
    if (options.placeholder) n.placeholder = options.placeholder;
    if (options.rtl) {
      n.dir = "rtl";
      n.lang = "ar";
    } else if (options.area) n.dir = "auto";
    if (options.type === "number") {
      n.min = 1;
      n.max = 30;
    }
    wrapper.append(l, n);
    return wrapper;
  }
  const val = (root, name) =>
    root.querySelector(`[name="${name}"]`)?.value || "";
  function heading(title, subtitle, action) {
    const h = el("div", "learning-heading");
    const copy = el("div");
    copy.append(
      el("p", "learning-eyebrow", "Your learning notebook"),
      el("h2", "", title),
    );
    if (subtitle) copy.append(el("p", "learning-muted", subtitle));
    h.append(copy);
    if (action) h.append(action);
    return h;
  }
  function empty(root, title, note, action) {
    const box = el("div", "learning-empty");
    box.append(el("h3", "", title), el("p", "learning-muted", note));
    if (action) box.append(action);
    root.append(box);
  }
  const section = (title) => {
    const s = el("section", "learning-section");
    if (title) s.append(el("h3", "", title));
    return s;
  };
  const line = (title, note, action) => {
    const row = el("div", "learning-row");
    const copy = el("div");
    copy.append(el("h3", "", title));
    if (note) copy.append(el("p", "learning-muted", note));
    row.append(copy);
    if (action) row.append(action);
    return row;
  };
  function reset() {
    state.workspace = null;
    state.words = [];
    state.task = null;
    state.recap = null;
    state.family = null;
    state.view = "list";
    state.session = null;
    state.dirty = false;
    clearTimeout(state.timer);
    $("#word-family-panel").hidden = true;
  }
  async function refresh() {
    const key = identity();
    if (state.identity !== key) {
      reset();
      state.identity = key;
    }
    const seq = ++state.seq;
    if (!state.workspace) {
      $("#learning-home").replaceChildren(
        el("p", "learning-muted", "Loading your lessons…"),
      );
    }
    try {
      const data = await api("/api/lessons?action=workspace");
      if (seq !== state.seq || key !== identity()) return;
      state.workspace = data;
      renderHome();
      if (state.view === "list") renderLessons();
      if (!state.recap) renderKnowledge();
    } catch (error) {
      if (key !== identity()) return;
      $("#learning-home").replaceChildren(
        line(
          "Your notebook could not load",
          error.message,
          btn("Try again", refresh),
        ),
      );
      throw error;
    }
  }
  async function ensureWords() {
    state.words = await api("/api/items");
    return state.words;
  }
  function renderHome() {
    const root = $("#learning-home"),
      w = state.workspace;
    if (!w) return;
    root.replaceChildren(
      heading(
        "From the lesson to your own sentences",
        "Keep the words, the grammar, and what your teacher corrected together.",
        btn("Capture a lesson", () => openCapture(), "primary"),
      ),
    );
    const stats = el("div", "learning-statline");
    for (const [n, label] of [
      [w.counts.sessions, "lessons captured"],
      [w.counts.open_homework, "homework to do"],
      [w.due_rules.length, "rules to recap"],
    ]) {
      const span = el("span");
      span.append(el("strong", "", n), document.createTextNode(label));
      stats.append(span);
    }
    root.append(stats);
    const grid = el("div", "learning-home-grid"),
      focus = el("section", "learning-focus"),
      task = w.tasks.find((t) => t.status === "open");
    focus.append(
      el(
        "p",
        "learning-eyebrow",
        task ? "Continue your homework" : "After your next lesson",
      ),
    );
    if (task) {
      const session = w.sessions.find((s) => s.id === task.session_id);
      focus.append(
        el("h3", "", session?.title || "Write with what you learned"),
        el("p", "learning-prose", task.prompt),
        el(
          "p",
          "learning-muted",
          `${task.sentence_count} sentences · ${task.words.length} words · ${task.rules.length} rules${task.due_on ? " · due " + formatDay(task.due_on) : ""}`,
        ),
        btn("Open sentence workshop", () => openTask(task.id), "primary"),
      );
    } else
      focus.append(
        el("h3", "", "A lesson is more than a word list."),
        el(
          "p",
          "learning-muted",
          "Capture the new words and the rule that connects them. Sawt turns the lesson into a brief for your own sentences, then keeps your attempts and corrections.",
        ),
        btn("Start a lesson", () => openCapture(), "primary"),
      );
    const rail = el("aside", "learning-rail");
    rail.append(el("h3", "", "Recall, then reveal"));
    if (w.due_rules.length)
      for (const rule of w.due_rules.slice(0, 3))
        rail.append(
          line(
            rule.title,
            "Explain it or write a fresh example before looking at your notes.",
            btn("Recap", () => openRecap(rule.id), "text"),
          ),
        );
    else
      rail.append(
        el(
          "p",
          "learning-muted",
          w.rules.length
            ? "Your saved rules will return here when they are due. You can recap any rule in Knowledge."
            : "Save your first grammar rule with a lesson. It will become a recall prompt here.",
        ),
      );
    rail.append(btn("Open Knowledge", () => showTab("knowledge"), "text"));
    grid.append(focus, rail);
    root.append(grid);
  }
  function renderLessons() {
    if (!state.workspace) return;
    const root = $("#learning-lessons"),
      w = state.workspace;
    root.replaceChildren(
      heading(
        "Lessons",
        "Words → grammar → your sentences → teacher feedback.",
        btn("Capture a lesson", () => openCapture(), "primary"),
      ),
    );
    if (!w.sessions.length) {
      empty(
        root,
        "Start with your new teacher",
        "Use a lesson title, add the words and rules you covered, then set the writing brief. Grammar-only lessons and familiar words are welcome.",
        btn("Capture your first lesson", () => openCapture(), "primary"),
      );
      return;
    }
    for (const session of w.sessions) {
      const task = w.tasks.find((t) => t.session_id === session.id);
      root.append(
        line(
          session.title,
          `${formatDay(session.learned_on)}${session.teacher ? " · " + session.teacher : ""} · ${session.words.length} words${session.goal ? "\n" + session.goal : ""}`,
          btn(task?.status === "done" ? "Review lesson" : "Open lesson", () =>
            openSession(session.id),
          ),
        ),
      );
    }
  }
  function ruleEditor(parent, spec = {}) {
    const row = el("div", "learning-rule-editor");
    row.dataset.ruleEditor = "";
    row.append(
      field("rule_title", "Rule or pattern", spec.title || "", {
        placeholder: "e.g. 3am + bare imperfect",
      }),
      field("rule_explanation", "How it works", spec.explanation || "", {
        area: true,
        placeholder: "Write the explanation in your own words.",
      }),
      field(
        "rule_example",
        "Teacher example or your own example",
        spec.example || "",
        { area: true },
      ),
      field(
        "rule_source",
        "Source / book page",
        spec.source || "Teacher lesson",
      ),
      btn("Remove rule", () => row.remove(), "text"),
    );
    parent.append(row);
  }
  async function openCapture(seed) {
    if (state.dirty) await saveDraft();
    showTab("lessons");
    state.view = "capture";
    state.task = null;
    state.session = null;
    const root = $("#learning-lessons");
    root.replaceChildren(
      heading(
        "Capture the lesson",
        "Keep vocabulary, grammar, and the writing brief separate. They will stay linked.",
      ),
    );
    root.append(
      btn(
        "Back to lessons",
        () => {
          state.view = "list";
          renderLessons();
        },
        "text",
      ),
    );
    const form = el("form", "learning-capture"),
      basics = el("div", "learning-form-grid");
    basics.append(
      field("title", "Lesson title", "", {
        required: true,
        placeholder: "What did you work on?",
        full: true,
      }),
      field("learned_on", "Lesson date", today(), {
        type: "date",
        required: true,
      }),
      field("teacher", "Teacher", state.workspace?.teacher || "", {
        placeholder: "Your new teacher’s name",
      }),
      field("goal", "What do you want to be able to say?", "", {
        area: true,
        full: true,
        placeholder: "A situation, topic, or skill you want to practise.",
      }),
    );
    form.append(basics);
    const vocab = section("1. Words from this lesson");
    vocab.append(
      field("words_text", "New words", "", {
        area: true,
        placeholder: "katab = write\nshoghol = work",
      }),
    );
    const reused = el("details");
    reused.append(el("summary", "", "Reuse words already in my notebook"));
    const choices = el("div", "learning-checkwords learning-chip-list");
    reused.append(choices);
    reused.ontoggle = async () => {
      if (reused.open && !choices.children.length) {
        try {
          await ensureWords();
          for (const word of state.words) {
            const l = el("label", "learning-chip");
            const i = el("input");
            i.type = "checkbox";
            i.value = word.id;
            l.append(
              i,
              document.createTextNode(`${word.spelling} · ${word.gloss}`),
            );
            choices.append(l);
          }
        } catch (error) {
          fail(error);
        }
      }
    };
    vocab.append(reused);
    form.append(vocab);
    const rules = section("2. Grammar and sentence patterns"),
      editors = el("div");
    rules.append(
      el(
        "p",
        "learning-muted",
        "Capture the rule you will use. Add another if the lesson covered several.",
      ),
      editors,
    );
    ruleEditor(editors, seed);
    rules.append(btn("Add another rule", () => ruleEditor(editors), "text"));
    form.append(rules);
    form.append(field("notes", "Other lesson notes", "", { area: true }));
    const hw = section("3. Homework · use the lesson in your own sentences");
    hw.append(
      field("prompt", "Teacher’s homework / writing brief", "", {
        area: true,
        placeholder:
          "Leave empty and Sawt will build a brief from the selected words, rules, and your goal.",
      }),
    );
    const dates = el("div", "learning-form-grid");
    dates.append(
      field("sentence_count", "Number of sentences", "3", { type: "number" }),
      field("due_on", "Due date (optional)", "", { type: "date" }),
    );
    hw.append(dates);
    form.append(hw);
    const error = el("p", "error");
    error.setAttribute("role", "alert");
    const submit = el("button", "primary", "Save lesson and open workshop");
    submit.type = "submit";
    form.append(error, submit);
    root.append(form);
    form.onsubmit = async (e) => {
      e.preventDefault();
      if (submit.disabled) return;
      submit.disabled = true;
      error.textContent = "";
      try {
        const specs = [...editors.children]
          .map((row) => ({
            title: val(row, "rule_title"),
            explanation: val(row, "rule_explanation"),
            example: val(row, "rule_example"),
            source: val(row, "rule_source"),
          }))
          .filter((r) => r.title || r.explanation);
        const data = await write({
          action: "capture",
          title: val(form, "title"),
          learned_on: val(form, "learned_on"),
          teacher: val(form, "teacher"),
          goal: val(form, "goal"),
          notes: val(form, "notes"),
          words_text: val(form, "words_text"),
          word_ids: [...choices.querySelectorAll("input:checked")].map((i) =>
            Number(i.value),
          ),
          rules: specs,
          prompt: val(form, "prompt"),
          sentence_count: Number(val(form, "sentence_count")),
          due_on: val(form, "due_on"),
        });
        state.view = "workshop";
        await refresh();
        await loadLibrary();
        await loadRecent();
        await openTask(data.task_id);
        if (data.word_ids.length) requestArabicFill(data.word_ids);
        say(
          "Lesson saved. Your vocabulary and rules are ready for your own sentences.",
        );
      } catch (err) {
        error.textContent = err.message;
      } finally {
        submit.disabled = false;
      }
    };
  }
  function openSession(id) {
    state.session = id;
    state.view = "session";
    showTab("lessons");
    const s = state.workspace.sessions.find((x) => x.id === id);
    if (!s) return;
    const root = $("#learning-lessons");
    root.replaceChildren(
      btn(
        "Back to lessons",
        () => {
          state.view = "list";
          renderLessons();
        },
        "text",
      ),
      heading(
        s.title,
        `${formatDay(s.learned_on)}${s.teacher ? " · " + s.teacher : ""}`,
      ),
    );
    if (s.goal) root.append(el("p", "learning-prose", s.goal));
    if (s.notes) root.append(el("p", "learning-muted learning-prose", s.notes));
    const words = section("Words used in this lesson"),
      chips = el("div", "learning-chip-list");
    for (const word of s.words)
      chips.append(
        el("span", "learning-chip", `${word.spelling} · ${word.gloss}`),
      );
    words.append(chips);
    root.append(words);
    const rules = section("Grammar to use");
    for (const rule of state.workspace.rules.filter(
      (r) => r.session_id === id,
    )) {
      const box = el("div", "learning-rule-note");
      box.append(
        el("h4", "", rule.title),
        el("p", "learning-prose", rule.explanation),
        el("p", "learning-small", rule.source),
        btn("Recap this rule", () => openRecap(rule.id), "text"),
      );
      rules.append(box);
    }
    root.append(rules);
    const tasks = section("Sentence homework");
    for (const task of state.workspace.tasks.filter((t) => t.session_id === id))
      tasks.append(
        line(
          task.prompt,
          `${task.status === "done" ? "Ready / completed" : "In progress"} · ${task.sentence_count} sentences`,
          btn("Open workshop", () => openTask(task.id)),
        ),
      );
    tasks.append(
      btn(
        "New writing brief from this lesson",
        async () => {
          const r = await write({
            action: "task",
            session_id: id,
            word_ids: s.words.map((w) => w.id),
            rule_ids: state.workspace.rules
              .filter((r) => r.session_id === id)
              .map((r) => r.id),
            sentence_count: 3,
            prompt: "",
          });
          await refresh();
          await openTask(r.task_id);
        },
        "text",
      ),
    );
    root.append(tasks);
  }
  async function openTask(id) {
    if (state.dirty) await saveDraft();
    clearTimeout(state.timer);
    state.view = "workshop";
    showTab("lessons");
    const root = $("#learning-lessons");
    root.replaceChildren(el("p", "learning-muted", "Loading your writing…"));
    const task = await api(`/api/lessons?action=task&id=${id}`);
    state.task = task;
    state.dirty = false;
    renderTask();
  }
  function renderTask() {
    const task = state.task,
      root = $("#learning-lessons");
    if (!task) return;
    const session = state.workspace?.sessions.find(
      (s) => s.id === task.session_id,
    );
    root.replaceChildren(
      btn(
        "Back to lesson",
        async () => {
          if (state.dirty) await saveDraft();
          state.task = null;
          if (session) openSession(session.id);
          else {
            state.view = "list";
            renderLessons();
          }
        },
        "text",
      ),
      heading("Sentence workshop", session?.title || "Use what you learned"),
    );
    root.append(el("p", "learning-prose", task.prompt));
    const grid = el("div", "learning-work-grid"),
      main = el("div"),
      rail = el("aside", "learning-rail");
    const input = field("writing", "Your own sentences", task.draft, {
      area: true,
      placeholder:
        "Write in Arabic or Arabizi. Try the rule before looking at your teacher’s example.",
    });
    $("textarea", input).classList.add("learning-editor");
    $("textarea", input).id = "learning-writing";
    main.append(input);
    const status = el(
      "p",
      "learning-save-status",
      task.draft ? "Draft loaded" : "Your draft will save as you write.",
    );
    status.id = "learning-draft-status";
    main.append(status);
    $("textarea", input).oninput = () => {
      state.dirty = true;
      status.textContent = "Unsaved changes";
      clearTimeout(state.timer);
      state.timer = setTimeout(() => saveDraft(true).catch(fail), 1400);
    };
    const actions = el("div", "learning-actions");
    actions.append(
      btn("Save draft", () => saveDraft()),
      btn(
        "Save attempt",
        async () => {
          clearTimeout(state.timer);
          if (state.saving) {
            say("Please wait for the draft to finish saving.");
            return;
          }
          const answer = $("#learning-writing").value;
          const result = await write({
            action: "attempt",
            task_id: task.id,
            text: answer,
            revision: task.revision,
          });
          task.revision = result.revision;
          state.dirty = false;
          await openTask(task.id);
          say(
            "Attempt saved. Keep revising here, or add your teacher’s corrections below.",
          );
        },
        "primary",
      ),
      btn(
        task.status === "done" ? "Reopen homework" : "Mark homework ready",
        async () => {
          if (state.dirty) await saveDraft();
          await write({
            action: "task-status",
            task_id: task.id,
            status: task.status === "done" ? "open" : "done",
          });
          await refresh();
          await openTask(task.id);
        },
        "text",
      ),
    );
    main.append(actions);
    rail.append(
      el("h3", "", "Your requirements"),
      el(
        "p",
        "learning-muted",
        `${task.sentence_count} original sentences${task.due_on ? " · due " + formatDay(task.due_on) : ""}`,
      ),
      el(
        "p",
        "learning-small",
        "Tick the words you used as your own check. These ticks are not an automatic grammar grade.",
      ),
    );
    const chips = el("div", "learning-chip-list");
    for (const word of task.words) {
      const label = el("label", "learning-chip"),
        checkbox = el("input");
      checkbox.type = "checkbox";
      label.append(
        checkbox,
        document.createTextNode(`${word.spelling} · ${word.gloss}`),
      );
      chips.append(label);
    }
    rail.append(chips);
    for (const rule of task.rules) {
      const details = el("details", "learning-rule-note");
      details.append(el("summary", "", rule.title));
      const saved =
        state.workspace?.rules.find((r) => r.id === rule.id) || rule;
      details.append(
        el("p", "learning-prose", rule.explanation),
        el("p", "learning-prose", rule.example || ""),
        el("p", "learning-small", rule.source || saved.source),
      );
      rail.append(details);
    }
    if (!task.rules.length)
      rail.append(
        el(
          "p",
          "learning-muted",
          "No grammar rule is attached to this brief. Add the rule to a new lesson or use one from Knowledge.",
        ),
      );
    rail.append(btn("Look up a word", () => openDictionary(""), "text"));
    grid.append(main, rail);
    root.append(grid);
    const history = section("Attempts and corrections");
    if (!task.attempts.length)
      history.append(
        el(
          "p",
          "learning-muted",
          "Saved attempts will appear here. Your original sentences are kept when you add a correction.",
        ),
      );
    for (const attempt of task.attempts) {
      const box = el("article", "learning-evidence");
      box.append(
        el("h4", "", new Date(attempt.created_at).toLocaleString()),
        el("p", "learning-prose", attempt.text),
      );
      for (const correction of attempt.corrections) {
        const c = el("div", "learning-correction");
        c.append(
          el("p", "learning-small", correction.author),
          el("p", "learning-prose", correction.text),
          el("p", "learning-muted learning-prose", correction.note),
        );
        box.append(c);
      }
      const details = el("details");
      details.append(el("summary", "", "Add a correction or teacher note"));
      const f = el("div");
      f.append(
        field("corrected", "Corrected sentences", "", { area: true }),
        field("reason", "What changed and why?", "", { area: true }),
        field("author", "Source", "Teacher notes entered by me", {
          choices: [
            ["Teacher notes entered by me", "Teacher notes entered by me"],
            ["My own revision", "My own revision"],
          ],
        }),
        btn("Save correction", async () => {
          await write({
            action: "correction",
            attempt_id: attempt.id,
            text: val(f, "corrected"),
            note: val(f, "reason"),
            author: val(f, "author"),
          });
          await openTask(task.id);
          say("Correction saved alongside your original attempt.");
        }),
      );
      details.append(f);
      box.append(details);
      history.append(box);
    }
    root.append(history);
  }
  async function saveDraft(quiet = false) {
    if (!state.task || !$("#learning-writing") || !state.dirty) return;
    if (state.saving)
      throw new Error(
        "A draft save is in progress. Wait a moment before switching.",
      );
    state.saving = true;
    const task = state.task,
      answer = $("#learning-writing").value;
    const s = $("#learning-draft-status");
    if (s) s.textContent = "Saving draft…";
    try {
      const r = await write({
        action: "draft",
        task_id: task.id,
        text: answer,
        revision: task.revision,
      });
      task.revision = r.revision;
      task.draft = answer;
      if ($("#learning-writing")?.value === answer) state.dirty = false;
      if (s)
        s.textContent = state.dirty ? "More changes to save…" : "Draft saved";
      if (!quiet) say("Draft saved.");
    } catch (error) {
      if (s) s.textContent = "Not saved. Your text is still here.";
      throw error;
    } finally {
      state.saving = false;
      if (state.dirty && $("#learning-writing")?.value !== answer)
        state.timer = setTimeout(() => saveDraft(true).catch(fail), 1400);
    }
  }
  function renderKnowledge() {
    const w = state.workspace;
    if (!w) return;
    const root = $("#learning-knowledge");
    root.replaceChildren(
      heading(
        "Knowledge",
        "Remember the rule, use it in a sentence, then revisit what changed.",
        btn("Add a rule", () => openRuleForm(), "primary"),
      ),
    );
    const saved = section("Your grammar and patterns");
    if (!w.rules.length)
      empty(
        saved,
        "Build a record of how the language works",
        "Save rules from lessons or adapt a pattern below. They will appear in your recall queue.",
      );
    for (const rule of w.rules)
      saved.append(
        line(
          rule.title,
          `${rule.source || "Your notes"} · ${rule.due_on <= today() ? "Due for recap" : "Next recap " + formatDay(rule.due_on)}`,
          btn("Recall it", () => openRecap(rule.id)),
        ),
      );
    root.append(saved);
    if (w.guide.length) {
      const guide = section("A guide for the green verbs book");
      guide.append(
        el(
          "p",
          "learning-muted",
          "Original study prompts organised around the verb distinctions in Matthew Aldrich’s Levantine Arabic Verbs. Page references use the printed page numbers. Add only what you cover with your teacher.",
        ),
      );
      const rows = el("div", "learning-guide");
      for (const pattern of w.guide) {
        const box = el("div", "learning-row");
        const copy = el("div");
        copy.append(
          el("h3", "", pattern.title),
          el("p", "learning-muted", pattern.explanation),
          el("p", "learning-small", pattern.source),
          btn("Use this in a lesson", () => openCapture(pattern), "text"),
        );
        box.append(copy);
        rows.append(box);
      }
      guide.append(rows);
      root.append(guide);
    }
  }
  function openRuleForm() {
    const root = $("#learning-knowledge");
    root.replaceChildren(
      heading(
        "Save a rule",
        "Use your own explanation and an example you understand.",
      ),
    );
    const form = el("form", "learning-capture");
    form.append(
      field("title", "Rule or pattern", "", { required: true }),
      field("explanation", "Explanation", "", { area: true, required: true }),
      field("example", "Example", "", { area: true }),
      field("source", "Teacher / source / page", "Teacher lesson"),
    );
    const b = el("button", "primary", "Save rule");
    b.type = "submit";
    form.append(b, btn("Cancel", renderKnowledge, "text"));
    form.onsubmit = async (e) => {
      e.preventDefault();
      if (b.disabled) return;
      b.disabled = true;
      try {
        await write({
          action: "rule",
          title: val(form, "title"),
          explanation: val(form, "explanation"),
          example: val(form, "example"),
          source: val(form, "source"),
        });
        await refresh();
        renderKnowledge();
      } catch (error) {
        fail(error);
      } finally {
        b.disabled = false;
      }
    };
    root.append(form);
  }
  async function openRecap(id) {
    if (state.dirty) await saveDraft();
    showTab("knowledge");
    state.recap = await api(`/api/lessons?action=rule&id=${id}`);
    const rule = state.recap,
      root = $("#learning-knowledge");
    root.replaceChildren(
      btn(
        "Back to knowledge",
        () => {
          state.recap = null;
          renderKnowledge();
        },
        "text",
      ),
      heading(
        rule.title,
        "Explain the pattern or write a fresh example before revealing your notes.",
      ),
    );
    const fieldNode = field("recall", "What can you remember?", "", {
      area: true,
    });
    $("textarea", fieldNode).classList.add("learning-editor");
    root.append(fieldNode);
    const reveal = btn(
      "Reveal my notes",
      () => {
        reveal.hidden = true;
        const answer = el("section", "learning-recap-answer");
        answer.append(el("p", "learning-prose", rule.explanation));
        if (rule.example)
          answer.append(el("p", "learning-prose", rule.example));
        answer.append(el("p", "learning-small", rule.source));
        root.append(answer);
        const ratings = el("div", "learning-actions");
        for (const [rating, label] of [
          ["again", "Need another look · tomorrow"],
          ["partly", "Partly recalled · 3 days"],
          ["recalled", "Recalled · 7 days"],
        ])
          ratings.append(
            btn(
              label,
              async () => {
                const r = await write({
                  action: "recall",
                  rule_id: id,
                  response: val(fieldNode, "recall"),
                  rating,
                });
                state.recap = null;
                await refresh();
                say(
                  `Recall saved. This rule returns on ${formatDay(r.due_on)}.`,
                );
              },
              rating === "recalled" ? "primary" : "secondary",
            ),
          );
        root.append(ratings);
        if (rule.history.length) {
          const h = section("Earlier recall");
          for (const entry of rule.history.slice(0, 8))
            h.append(
              line(
                new Date(entry.created_at).toLocaleDateString(),
                entry.response + " · " + entry.rating,
              ),
            );
          root.append(h);
        }
      },
      "primary",
    );
    root.append(reveal);
  }
  let dictionarySeq = 0;
  function renderDictionary(query = "") {
    const root = $("#dictionary-panel");
    root.replaceChildren(
      heading(
        "Look up a word",
        "Search English, Arabic, or available Arabizi spellings without leaving Sawt.",
      ),
    );
    if (state.task)
      root.append(
        btn("Back to my sentences", () => openTask(state.task.id), "text"),
      );
    const form = el("form", "learning-search"),
      input = el("input");
    input.type = "search";
    input.placeholder = "e.g. write, coffee, كتب";
    input.setAttribute("aria-label", "Search the dictionary");
    input.value = query;
    const submit = el("button", "primary", "Search");
    submit.type = "submit";
    form.append(input, submit);
    root.append(
      form,
      el(
        "p",
        "dictionary-attribution",
        "Definitions from the cached Arwords index. Extra forms load on request when available. The dictionary is separate from your saved words.",
      ),
    );
    const results = el("div"),
      status = el("p", "learning-muted");
    status.setAttribute("role", "status");
    root.append(status, results);
    async function search() {
      const seq = ++dictionarySeq;
      results.replaceChildren();
      status.textContent = "Searching the dictionary…";
      submit.disabled = true;
      try {
        const data = await api(
          "/api/items?action=dictionary&q=" + encodeURIComponent(input.value),
        );
        if (seq !== dictionarySeq) return;
        status.textContent = data.total
          ? `${data.total} matching entries${data.total > data.entries.length ? "; showing the first " + data.entries.length : ""}. Select the meaning you need.`
          : input.value.trim()
            ? "No match in the cached index. Try a shorter spelling or the English meaning."
            : "Type a word or a meaning to search.";
        for (const entry of data.entries)
          results.append(dictionaryResult(entry));
      } catch (error) {
        status.textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    }
    form.onsubmit = (e) => {
      e.preventDefault();
      search();
    };
    if (query) search();
    else
      status.textContent =
        "Try a meaning, an Arabic spelling, or an Arabizi form.";
  }
  function dictionaryResult(entry) {
    const card = el("article", "dictionary-result"),
      title = el("h3", "arabic-script", entry.arabic);
    title.dir = "rtl";
    title.lang = "ar";
    card.append(title, el("p", "learning-prose", entry.meaning));
    const details = el("div");
    const actions = el("div", "learning-actions");
    actions.append(
      btn("View available forms", async (b) => {
        b.textContent = "Loading forms…";
        const data = await api(
          "/api/items?action=dictionary-entry&id=" + entry.id,
        );
        details.replaceChildren();
        if (data.notice) details.append(el("p", "learning-muted", data.notice));
        if (!data.forms.length)
          details.append(
            el(
              "p",
              "learning-muted",
              "No additional forms were available. You can still save this headword and add teacher-confirmed forms.",
            ),
          );
        for (const [index, form] of data.forms.entries()) {
          const box = el("div", "dictionary-form"),
            word = el("p", "arabic-script", form.arabic);
          word.dir = "rtl";
          box.append(
            word,
            el("p", "", form.translit || ""),
            el(
              "p",
              "learning-small",
              [form.conjugation, form.dialect].filter(Boolean).join(" · "),
            ),
            btn(
              "Save this form",
              () => saveDictionary(entry.id, index),
              "text",
            ),
          );
          details.append(box);
        }
        details.className = "dictionary-forms";
        b.textContent = "Forms loaded";
      }),
      btn(
        "Save headword to Words",
        () => saveDictionary(entry.id, null),
        "text",
      ),
    );
    const source = el("a", "dictionary-attribution", "Source: Arwords");
    source.href = entry.url;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    card.append(actions, details, source);
    return card;
  }
  async function saveDictionary(id, formIndex) {
    const saved = await post("/api/items", {
      action: "save-dictionary",
      entry_id: id,
      form_index: formIndex,
      learned_on: today(),
    });
    await loadLibrary();
    await loadRecent();
    say(
      saved.already_saved
        ? "This word is already in your notebook."
        : "Saved to Words. It will also be available to your word flashcards.",
    );
  }
  function openDictionary(query = "") {
    showTab("words");
    wordsWriting = "dictionary";
    syncWordsWriting();
    renderDictionary(query);
  }
  const kindLabels = {
    noun: "Noun",
    verbal_noun: "Verbal noun / masdar",
    adjective: "Adjective",
    past: "Past / perfect",
    imperfect: "Bare imperfect",
    present: "Habitual present / b-form",
    imperative: "Imperative / command",
    continuous: "Continuous / 3am construction",
    active_participle: "Active participle",
    passive_participle: "Passive participle",
    other: "Other / dictionary label",
  };
  const sourceLabels = {
    teacher: "Teacher confirmed",
    dictionary: "Dictionary form",
    learner: "My own note",
    suggestion: "AI suggestion — check with teacher",
  };
  async function openFamily(id) {
    showTab("words");
    if (wordsWriting === "dictionary") wordsWriting = "all";
    syncWordsWriting();
    const root = $("#word-family-panel");
    root.hidden = false;
    root.replaceChildren(el("p", "learning-muted", "Loading related forms…"));
    const data = await api("/api/items?action=family&id=" + id);
    state.family = data;
    renderFamily();
    root.scrollIntoView({ block: "start", behavior: "smooth" });
  }
  function familyRow(list, form = {}) {
    const row = el("div", "family-form");
    row.dataset.familyForm = "";
    row.dataset.sourceUrl = form.source_url || "";
    const grid = el("div", "family-form-grid");
    grid.append(
      field("kind", "Form", form.kind || "past", {
        choices: Object.entries(kindLabels),
      }),
      field("subject", "Person / gender / number", form.subject || "", {
        placeholder: "e.g. I, he, you (f), plural",
      }),
      field("arabic", "Arabic", form.arabic || "", { rtl: true }),
      field("arabizi", "Arabizi", form.arabizi || ""),
      field("meaning", "Meaning of this form", form.meaning || ""),
      field("source", "Source", form.source || "teacher", {
        choices: Object.entries(sourceLabels),
      }),
      field("example", "Example or usage note", form.example || "", {
        area: true,
        full: true,
      }),
    );
    row.append(grid);
    if (form.source_url) {
      const a = el("a", "learning-small", "Dictionary source");
      a.href = form.source_url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      row.append(a);
    }
    row.append(btn("Remove this form", () => row.remove(), "text"));
    list.append(row);
  }
  function readFamily(list) {
    return [...list.children].map((row) => ({
      kind: val(row, "kind"),
      subject: val(row, "subject"),
      arabic: val(row, "arabic"),
      arabizi: val(row, "arabizi"),
      meaning: val(row, "meaning"),
      source: val(row, "source"),
      example: val(row, "example"),
      source_url: row.dataset.sourceUrl || "",
    }));
  }
  function renderFamily() {
    const data = state.family,
      root = $("#word-family-panel");
    root.hidden = false;
    root.replaceChildren();
    const header = el("div", "family-header"),
      copy = el("div");
    copy.append(
      el("p", "learning-eyebrow", "Word family"),
      el("h2", "", `${data.item.spelling} · ${data.item.gloss}`),
      el(
        "p",
        "learning-muted",
        "Keep each form, its meaning, and the person it belongs to. Nouns and adjectives are related words; they are not automatic tense changes. Continuous forms are constructions.",
      ),
    );
    header.append(
      copy,
      btn(
        "Close",
        () => {
          root.hidden = true;
          state.family = null;
        },
        "text",
      ),
    );
    root.append(header);
    const list = el("div");
    for (const form of data.forms) familyRow(list, form);
    if (!data.forms.length)
      root.append(
        el(
          "p",
          "learning-muted",
          "No forms saved yet. Add what your teacher gives you, load dictionary forms, or request suggestions to review.",
        ),
      );
    const controls = el("div", "learning-actions"),
      status = el("p", "learning-muted");
    status.setAttribute("role", "status");
    const candidates = el("div");
    const append = (forms) => {
      const known = new Set(
        readFamily(list).map((f) =>
          [f.kind, f.subject, f.arabic, f.arabizi].join("|"),
        ),
      );
      for (const form of forms) {
        const key = [form.kind, form.subject, form.arabic, form.arabizi].join(
          "|",
        );
        if (!known.has(key)) {
          familyRow(list, form);
          known.add(key);
        }
      }
    };
    const loadForms = async (entryId) => {
      status.textContent = "Loading dictionary forms…";
      const found = await post("/api/items", {
        action: "dictionary-forms",
        item_id: data.item.id,
        ...(entryId ? { entry_id: entryId } : {}),
      });
      if (found.forms.length) {
        append(found.forms);
        candidates.replaceChildren();
        status.textContent =
          "Dictionary forms added to the editor. Check the labels, then save.";
      } else {
        status.textContent =
          found.notice ||
          "No forms were available. Add confirmed forms manually.";
        candidates.replaceChildren();
        for (const entry of found.entries || [])
          candidates.append(
            line(
              `${entry.arabic} · ${entry.meaning}`,
              "Choose the matching meaning before using its forms.",
              btn("Choose entry", () => loadForms(entry.id), "text"),
            ),
          );
      }
    };
    controls.append(
      btn("Add a form", () => familyRow(list)),
      btn("Load dictionary forms", () => loadForms()),
      btn("Suggest related forms", async () => {
        status.textContent = "Preparing unverified suggestions…";
        try {
          const result = await post("/api/items", {
            action: "suggest-family",
            item_id: data.item.id,
          });
          append(result.forms);
          status.textContent = result.notice;
        } catch (error) {
          status.textContent =
            error.message + " You can add teacher-confirmed forms manually.";
        }
      }),
    );
    root.append(controls, status, candidates, list);
    const actions = el("div", "learning-actions");
    actions.append(
      btn(
        "Save word family",
        async () => {
          const result = await post("/api/items", {
            action: "save-family",
            item_id: data.item.id,
            revision: data.revision,
            forms: readFamily(list),
          });
          state.family = result;
          renderFamily();
          say(
            "Word family saved. Suggestions remain labelled until you confirm their source.",
          );
        },
        "primary",
      ),
    );
    root.append(actions);
  }
  $("#words-dictionary-tab").onclick = () => openDictionary("");
  window.addEventListener("beforeunload", (event) => {
    if (state.dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  window.SawtLearning = {
    refresh,
    openFamily,
    openDictionary,
    show(name) {
      if (state.identity && state.identity !== identity()) {
        reset();
        refresh().catch(fail);
        return;
      }
      if (!state.workspace) {
        refresh().catch(fail);
        return;
      }
      if (name === "today") renderHome();
      if (name === "lessons" && state.view === "list") renderLessons();
      if (name === "knowledge" && !state.recap) renderKnowledge();
    },
  };
  refresh().catch(() => {});
})();
