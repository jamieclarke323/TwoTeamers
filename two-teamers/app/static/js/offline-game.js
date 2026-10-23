(() => {
  const transliterations = {
    "ð": "d", "Ð": "d", "þ": "th", "Þ": "th", "æ": "ae", "Æ": "ae",
    "ø": "o", "Ø": "o", "ł": "l", "Ł": "l",
  };
  const normalise = (value, combiningMarks) => String(value)
    .replace(/[ðÐþÞæÆøØłŁ]/g, (letter) => transliterations[letter])
    .normalize("NFKD").replace(/\p{M}/gu, (mark) => combiningMarks.includes(mark) ? "" : mark).toLowerCase()
    .replace(/['`’]/g, "").replace(/[^a-z0-9]+/g, " ").trim();

  // RapidFuzz ratio is normalized Indel similarity: twice the LCS length.
  const ratio = (left, right) => {
    const row = new Array(right.length + 1).fill(0);
    for (let i = 0; i < left.length; i += 1) {
      let diagonal = 0;
      for (let j = 0; j < right.length; j += 1) {
        const previous = row[j + 1];
        row[j + 1] = left[i] === right[j] ? diagonal + 1 : Math.max(row[j], previous);
        diagonal = previous;
      }
    }
    const length = left.length + right.length;
    const value = length ? (1 - (length - 2 * row[right.length]) / length) * 100 : 100;
    const floor = Math.floor(value);
    return value - floor === 0.5 ? floor + floor % 2 : Math.round(value);
  };
  const match = (guess, players, solved, combiningMarks) => {
    const value = normalise(guess, combiningMarks);
    if (value.replace(/ /g, "").length < 3) return {result: "wrong", index: null, score: 0};
    let best = {index: null, score: 0};
    for (let index = 0; index < players.length; index += 1) {
      if (solved.includes(index)) continue;
      const answers = players[index].answers.map((answer) => normalise(answer, combiningMarks));
      if (answers.includes(value)) return {result: "exact", index, score: 100};
      const score = Math.max(0, ...answers.map((answer) => ratio(value, answer)));
      if (score > best.score) best = {index, score};
    }
    return {
      result: best.index !== null && best.score >= 90 ? "correct"
        : best.index !== null && best.score >= 70 ? "near" : "wrong",
      index: best.score >= 70 ? best.index : null, score: best.score,
    };
  };
  const share = (pack, state) => [
    `TWO TEAMERS ${state.solved.length}/${pack.players.length}`,
    `${pack.home} vs ${pack.away}`,
    pack.players.map((_, index) => {
      if (!state.solved.includes(index)) return "❌";
      const count = (state.answer_data.clues[String(index)] || []).length;
      return count === 0 ? "🟢" : count === 1 ? "🟡" : "🟠";
    }).join(" "),
    "twoteamers.com",
  ].join("\n");
  const completed = (pack, state) => new Set([...state.solved, ...(state.answer_data.revealed || [])]).size === pack.players.length;
  const apply = (pack, state, action, body) => {
    const start = () => {
      if (!state.score_started) {
        state.score_started = true;
        state.score_total = pack.players.length;
      }
    };
    if (action === "guess" || action === "exact") {
      const outcome = match(body.guess || "", pack.players, [...state.solved, ...(state.answer_data.revealed || [])], pack.combiningMarks);
      if (action === "exact" && outcome.result !== "exact") return {status: "not_exact"};
      start();
      if (outcome.result === "exact" || outcome.result === "correct") {
        const index = outcome.index;
        state.solved.push(index);
        state.solved.sort((a, b) => a - b);
        state.answer_data.solve_order.push({
          index, clue_count: (state.answer_data.clues[String(index)] || []).length,
        });
        if (!state.score_frozen) {
          state.score_correct += 1;
          if (state.score_correct >= state.score_total) state.score_frozen = true;
        }
        const finished = completed(pack, state);
        if (finished) state.score_frozen = true;
        return {
          status: "correct", message: "Correct!", player: pack.players[index],
          solved_count: state.solved.length, total: pack.players.length, completed: finished,
          ...(finished ? {share_text: share(pack, state)} : {}),
        };
      }
      return outcome.result === "near"
        ? {status: "near", message: "Close but not quite.", score: outcome.score}
        : {status: "wrong", message: "Not a match. Keep trying."};
    }
    if (action === "clue") {
      if (pack.adsEnabled) return {status: "ad_required", message: "Connect and return to online play to unlock ad-gated clues."};
      const types = (body.types || []).filter((kind) => ["years", "initials", "nationality"].includes(kind));
      if (!types.length) return {status: "error", message: "Choose at least one clue."};
      if (body.index != null && body.index !== "all" && !/^[+-]?\d+$/.test(String(body.index).trim())) {
        return {status: "error", message: "Choose a valid player."};
      }
      const indices = pack.players.map((_, index) => index).filter((index) =>
        !state.solved.includes(index) && !(state.answer_data.revealed || []).includes(index)
        && (body.index == null || body.index === "all" || index === Number(body.index)));
      if (types.includes("nationality") && !indices.some((index) => pack.players[index].clues.nationality)) {
        types.splice(types.indexOf("nationality"), 1);
      }
      if (!types.length) return {status: "error", message: "That clue is not available."};
      start();
      state.score_frozen = true;
      return {status: "ok", clues: indices.map((index) => {
        const saved = state.answer_data.clues[String(index)] ||= [];
        for (const kind of types) {
          if (pack.players[index].clues[kind] && !saved.includes(kind)) saved.push(kind);
        }
        return {index, ...Object.fromEntries(saved.map((kind) => [kind, pack.players[index].clues[kind]]))};
      })};
    }
    if (action === "giveup-answer") {
      const index = body.index;
      if (body.confirm !== true) return {status: "error", message: "Confirm before revealing this answer."};
      if (!Number.isInteger(index) || index < 0 || index >= pack.players.length) {
        return {status: "error", message: "Choose a valid player."};
      }
      if (state.solved.includes(index) || state.given_up) return {status: "error", message: "This answer is already resolved."};
      start();
      const revealed = state.answer_data.revealed ||= [];
      if (!revealed.includes(index)) revealed.push(index);
      revealed.sort((a, b) => a - b);
      const finished = completed(pack, state);
      if (finished) state.score_frozen = true;
      return {
        status: "answer_revealed", player: pack.players[index],
        solved_count: state.solved.length, total: pack.players.length, completed: finished,
        ...(finished ? {share_text: share(pack, state)} : {}),
      };
    }
    if (action === "giveup") {
      if (!body.confirm) return {status: "error"};
      start();
      state.score_frozen = true;
      state.given_up = true;
      return {
        status: "given_up", players: pack.players, total: pack.players.length,
        solved_count: state.solved.length, share_text: share(pack, state),
      };
    }
    if (action === "reset") {
      if (state.score_started) state.score_frozen = true;
      state.solved = [];
      state.given_up = false;
      state.answer_data = {clues: {}, solve_order: []};
      return {status: "reset"};
    }
    return {status: "error", message: "This action requires online play."};
  };
  globalThis.OfflineGame = {normalise, ratio, match, apply, share, completed};
})();
