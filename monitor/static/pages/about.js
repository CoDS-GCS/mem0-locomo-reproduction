/* About: every linking rule in plain words */
PAGES.about = {
  async render(el) {
    const m = META;
    el.append(h('div', { class: 'about card', html: `
<h1>About Memory Journey</h1>
<p>A <b>read-only</b> view of one experiment folder (<code>${esc(m.folder)}</code>, mode <b>${esc(m.mode)}</b>, detected from ${esc(m.mode_source)}). It never writes, stops or edits anything in the folder, Qdrant or Neo4j, and never opens a Kuzu file. It reads new log bytes every ~15 s, the big result files only when they changed (at most every 30 s), and the live stores at most once per 25 s per view.</p>

<h2>Where each piece of information comes from</h2>
<ul>
<li><b>Dataset</b>: <code>dataset/locomo10.json</code>. A turn has a clock badge ⏱ when its text contains a relative time word (yesterday, last week/month/year/weekend/&lt;weekday&gt;, next …, tonight, N days/weeks/months/years ago, ago, recently, …).</li>
<li><b>Add stage</b>: <code>logs/events_&lt;user&gt;.jsonl</code> (one line per <code>add()</code> call: the 2 messages, memory events ADD / UPDATE (with previous text) / DELETE, graph relations added and deleted) and <code>logs/llm_conv&lt;N&gt;.jsonl</code> (every LLM call: prompt in, answer out). Files named <code>*.before_*</code> are abandoned passes and are ignored.</li>
<li><b>Search stage</b>: <code>results/mem0_results_top_30_filter_False_graph_True.json</code> (row <i>j</i> of conversation <i>c</i> is question <i>j</i> of the dataset, because search.py answers them in order) and <code>logs/llm_other.jsonl</code> (the entity call on the question).</li>
<li><b>Judge</b>: <code>results/mem0g_eval_run&lt;K&gt;.json</code>. These files hold only question, gold answer, response, category, F1, BLEU-1 and the 0/1 verdict, so a judged row is matched to its search row by <i>conversation + question text + gold answer</i> (the k-th repeat of identical text matches the k-th repeat).</li>
<li><b>Prompts</b>: templates are read as text from the source files (never imported, so no <code>__pycache__</code> appears in your folder). The answer and judge prompts are rebuilt exactly like <code>search.py</code> (jinja2, <code>json.dumps(..., indent=4)</code>) and <code>llm_judge.py</code> (<code>str.format</code>).</li>
</ul>

<h2>How LLM calls are linked to a batch</h2>
<ol>
<li>Mem0 1.0.11 creates a new thread pool for every <code>add()</code> and <code>search()</code>; its threads are called <code>ThreadPoolExecutor-&lt;N&gt;_&lt;i&gt;</code>, and N is unique per call within one process (one <code>llm_conv&lt;K&gt;.jsonl</code> = one process). All LLM calls with the same N are one <code>add()</code> call (a defensive split starts a new group if a second extraction appears under the same N).</li>
<li>Inside a group: the <i>memory</i> calls are extraction, then update (no update call if no fact was extracted); the <i>graph</i> calls are entities, relations, delete-decision.</li>
<li>A call is classified by its content: system prompt starting “Generate personal memories…” = extraction; a prompt with the update template (“smart memory manager”, “retrieved facts”) = update; the tool name gives the graph calls.</li>
<li>A group is matched to a batch by the message texts: the extraction input is “Input:” + the lines <code>role: Name: text</code> of the batch, which is unique per store because the roles are flipped between the two speakers. The user id in the graph prompt (“use X as the source entity”) confirms the store. The dataset is cut into batches exactly like <code>add.py</code> (2 turns per call, session by session).</li>
<li>Consecutive attempts of the same batch (retries after an error) form a run; the n-th run of a text goes to the n-th batch with that text. The same rule matches <code>events</code> lines to batches. Time order is only used for these runs.</li>
<li>Search stage: each <code>search()</code> is one group with one entity call whose user text is the question; it is matched by <i>(user id, question text)</i>.</li>
</ol>

<h2>Memory versions</h2>
<p>Mem0 returns the memory id for ADD, UPDATE (with <code>previous_memory</code>) and DELETE, so a memory's version chain is built by id from the events log, in batch order. <b>NONE</b> decisions are not returned by <code>add()</code> in 1.0.11; they are read from the update call's answer (each existing memory the model left unchanged). Temporary ids (“0”, “1”) in an update prompt are mapped to real ids by matching the memory text with the store state just before that batch.</p>

<h2>“Where information is lost” (Journey page)</h2>
<p>For every evidence turn and each of the two stores the page follows the information through six steps and marks the <b>first</b> broken link, in this order:</p>
<ol>
<li><b>no fact extracted</b>: none of the facts of the batch shares enough content words with the evidence turn (≥ ${30}% of the turn's content words; the same word-overlap rule is used for every “resembles” test below).</li>
<li><b>no memory created (decision NONE)</b>: facts exist, but the update call added or updated no memory that resembles the turn.</li>
<li><b>date dropped / date invented</b> (only for temporal questions: category 2, or questions starting with “When”, “What year/month/date/day”, “how long”, and only for evidence turns that contain a relative time word). The session date of the turn gives the expected date (“yesterday” on 8 May 2023 = 7 May 2023; “last year” = 2022; “two weeks ago” = a range around 24 April…). A date written in the memory that does not overlap the expected range = <i>invented</i>; no date and no relative word kept = <i>dropped</i>; the word kept (“yesterday”) is <i>not</i> a loss because the answer prompt prints the session date next to every memory. <b>Important:</b> the session date is stored as metadata only; it is not in the extraction prompt, so the model has no way to know the date and often invents one (check the prompt on the batch page).</li>
<li><b>overwritten by a later UPDATE</b>: the latest text of the memory no longer resembles the turn (or lost its date). The red edge sits on the first version that did it. <b>deleted</b>: the chain ends with a DELETE.</li>
<li><b>not retrieved (not in top 30)</b>: the latest text of the memory is not among the speaker's 30 retrieved memories (exact text match). If the two stores differ, the store that got furthest counts.</li>
<li><b>retrieved but answered wrong</b> or <b>correct</b>: the majority of the finished judge runs.</li>
</ol>
<p>If a question is judged correct although a loss was found, both facts are shown (the answer was found elsewhere). With several evidence turns, the turn that gets least far decides.</p>
<p>The <b>Overview funnel</b> counts a question at step k only if it passed steps 1…k for all its evidence turns. The <b>temporal lens</b> counts, per distinct evidence turn with a relative time word and per store, what the memory created in that batch did with it: kept the word / dropped the date / correct date / invented date / date present but not verifiable / no memory created.</p>

<h2>What cannot be known from the logs</h2>
<ul>
<li>Which Neo4j nodes were matched to the question's entities (similarity search inside Neo4j is not logged). The Search page shows an exact-name check instead and says so.</li>
<li>The Qdrant similarity search for each fact during add (which 5 old memories were found) is visible only through what the update prompt lists.</li>
<li>Word-overlap and date rules are <b>heuristics</b>, not proof; the clicked nodes show the evidence they used (overlap per fact, dates found, expected dates).</li>
<li>Questions without a search row, a judge run or an add log show grey “pending” nodes, never guesses.</li>
<li>In a run without add-stage logs (the Kuzu experiment) only the Dataset, Search, Judge, Overview and the retrieval part of the Journey are available; the Journey then uses text resemblance between the evidence turn and the 30 retrieved memories and says that it cannot tell “never created” from “not retrieved”. This text match (≥ 50% of the turn's content words) is a <b>weak</b> signal: on the finished Kuzu run it found an evidence-like memory for 53% of correctly answered and 41% of wrongly answered questions, so treat the retrieval step of that run as an estimate. No date verdicts are made in that mode.</li>
</ul>

<h2>Sources of the templates</h2>
<table class="t"><tr><th>template</th><th>file</th><th>name</th><th>read OK</th></tr>
${Object.entries(m.templates).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v.file)}</td><td>${esc(v.name)}</td><td>${v.found ? 'yes' : 'no'}</td></tr>`).join('')}</table>
<p class="note">Watchlist and the funnel category are kept in this browser's local storage only.</p>
` }));
  },
};
