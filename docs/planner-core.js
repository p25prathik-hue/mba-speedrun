/* MBA Speedrun — solver core in JavaScript (runs in the browser and in Node).
 *
 * A line-by-line port of src/speedrun/{graph,costs,baselines,heuristics,days,crunch}.py
 * so that GitHub Pages (static hosting) can run the heuristics live for any student's
 * own selection. Exact branch and bound is NOT run in the browser; preset results also
 * carry the Python value so the two can be compared (tests/test_js_parity.py).
 *
 * Class links: precedence-feasible nearest neighbour and cheapest insertion (S1 sl.26-39),
 * or-opt and 2-opt (S3 sl.31-41), random restart (S10 sl.36-38), day split as a
 * shortest path (S7) with the bin-packing lower bound (S8 sl.16), profit-maximising
 * tour heuristic for crunch mode (S9 sl.17-21).
 */
(function (root) {
  "use strict";
  const INF = Infinity;

  // ---------------------------------------------------------------- utilities
  function cmpTuple(a, b) {
    for (let i = 0; i < Math.max(a.length, b.length); i++) {
      const x = a[i], y = b[i];
      if (x === y) continue;
      if (x === undefined) return -1;
      if (y === undefined) return 1;
      return x < y ? -1 : 1;
    }
    return 0;
  }
  function mulberry32(a) {
    return function () {
      let t = (a += 0x6d2b79f5);
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function pyCmpStr(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

  // ---------------------------------------------------------------- web
  function indexWeb(web) {
    const T = {};
    web.topics.forEach((t) => (T[t.id] = t));
    const overlaps = {};
    (web.overlaps || []).forEach((o) => {
      overlaps[o.a + "|" + o.b] = o.sim;
      overlaps[o.b + "|" + o.a] = o.sim;
    });
    return { T, links: web.links.filter((l) => T[l.src] && T[l.dst]), overlaps, params: web.params };
  }

  // ---------------------------------------------------------------- closure (graph.build_instance)
  function buildInstance(W, profile, params) {
    profile = profile || {};
    params = Object.assign({}, W.params, params || {});
    const T = W.T;
    const all = Object.keys(T);
    const known = new Set([...(profile.known || []), ...all.filter((t) => (profile.known_domains || []).includes(T[t].domain))]);
    const skip = new Set([...(profile.skip || []), ...all.filter((t) => (profile.skip_domains || []).includes(T[t].domain))]);
    let scope;
    if ((profile.targets && profile.targets.length) || (profile.target_domains && profile.target_domains.length)) {
      scope = new Set([...(profile.targets || []), ...all.filter((t) => (profile.target_domains || []).includes(T[t].domain))]);
    } else scope = new Set(all);
    known.forEach((t) => scope.delete(t));
    skip.forEach((t) => scope.delete(t));
    const warnings = [], added = [];
    const andPred = {}, orGrp = {};
    W.links.forEach((l) => {
      if (l.type === "AND") (andPred[l.dst] = andPred[l.dst] || []).push(l.src);
      else if (l.type === "OR") {
        const g = l.group || "OR_" + l.dst;
        orGrp[l.dst] = orGrp[l.dst] || {};
        (orGrp[l.dst][g] = orGrp[l.dst][g] || []).push(l.src);
      }
    });
    const mult = (t) => {
      const m = profile.multipliers && t in profile.multipliers ? profile.multipliers[t]
        : profile.domain_multipliers && T[t].domain in profile.domain_multipliers ? profile.domain_multipliers[T[t].domain] : 1.0;
      return +m;
    };
    function closureCost(k, cur, depth) {
      depth = depth || 0;
      if (cur.has(k) || known.has(k) || depth > 60) return [0, new Set()];
      let need = new Set([k]);
      let cost = T[k].hours * mult(k);
      for (const a of andPred[k] || []) {
        const [c, s] = closureCost(a, new Set([...cur, ...need]), depth + 1);
        cost += c; s.forEach((x) => need.add(x));
      }
      const groups = orGrp[k] || {};
      for (const g of Object.keys(groups)) {
        const mem = groups[g];
        if (mem.some((m) => cur.has(m) || known.has(m) || need.has(m))) continue;
        let best = null;
        for (const m of mem) {
          const r = closureCost(m, new Set([...cur, ...need]), depth + 1);
          if (best === null || r[0] < best[0]) best = r;
        }
        cost += best[0]; best[1].forEach((x) => need.add(x));
      }
      return [cost, need];
    }
    let changed = true;
    while (changed) {
      changed = false;
      const order = [...scope].sort(pyCmpStr);
      outer: for (const j of order) {
        for (const k of andPred[j] || []) {
          if (scope.has(k) || known.has(k)) continue;
          if (profile.allow_drop) {
            scope.delete(j); warnings.push(`dropped ${j} because required prerequisite ${k} is excluded`);
          } else {
            const [, s] = closureCost(k, scope);
            const nw = [...s].filter((x) => !scope.has(x)).sort(pyCmpStr);
            nw.forEach((x) => scope.add(x)); added.push(...nw);
            const why = skip.has(k) ? "skipped" : "outside the chosen scope";
            warnings.push(`auto-included ${nw.join(", ")} (required for ${j}; ${k} was ${why})`);
          }
          changed = true; break outer;
        }
        const groups = orGrp[j] || {};
        for (const g of Object.keys(groups)) {
          const mem = groups[g];
          if (mem.some((m) => scope.has(m) || known.has(m))) continue;
          if (profile.allow_drop) {
            scope.delete(j); warnings.push(`dropped ${j}: no member of OR-group ${g} available`);
          } else {
            let best = null;
            for (const m of mem) {
              const r = closureCost(m, scope);
              if (best === null || r[0] < best[0]) best = [r[0], r[1], m];
            }
            const nw = [...best[1]].filter((x) => !scope.has(x)).sort(pyCmpStr);
            nw.forEach((x) => scope.add(x)); added.push(...nw);
            warnings.push(`OR-group ${g} for ${j}: added cheapest route via ${best[2]} (${best[0].toFixed(1)} h: ${nw.join(", ")})`);
          }
          changed = true; break outer;
        }
      }
    }
    const ids = [...scope].sort((a, b) => cmpTuple([T[a].term, T[a].course, T[a].order, a], [T[b].term, T[b].course, T[b].order, b]));
    const p = {};
    ids.forEach((t) => (p[t] = T[t].hours * mult(t)));
    return { W, ids, p, known, params, warnings, added: [...new Set(added)].sort(pyCmpStr) };
  }

  // ---------------------------------------------------------------- evaluator (costs.Evaluator)
  function Evaluator(inst) {
    const W = inst.W, P = inst.params, T = W.T;
    const ids = inst.ids, n = ids.length, idx = {};
    ids.forEach((t, k) => (idx[t] = k));
    const p = ids.map((t) => inst.p[t]);
    const dom = ids.map((t) => T[t].domain);
    const linked = {};
    W.links.forEach((l) => {
      if (l.src in idx && l.dst in idx) {
        linked[l.src + "|" + l.dst] = 1.0;
        const r = l.dst + "|" + l.src;
        linked[r] = Math.max(linked[r] || 0, 0.5);
      }
    });
    const sim = (i, j) => {
      let best = 0;
      const key = i + "|" + j;
      if (key in W.overlaps) best = Math.max(best, W.overlaps[key]);
      const ti = T[i], tj = T[j];
      if (ti.course && ti.course === tj.course) best = Math.max(best, Math.abs(ti.order - tj.order) <= 1 ? 0.5 : 0.25);
      return Math.max(linked[key] || 0, best);
    };
    const C = Array.from({ length: n }, () => new Float64Array(n));
    for (let a = 0; a < n; a++)
      for (let b = 0; b < n; b++)
        if (a !== b) C[a][b] = P.w_switch * (dom[a] !== dom[b] ? 1 : 0) - P.s_synergy * sim(ids[a], ids[b]) * p[b];
    const ak = [], aj = [], sk = [], sj = [];
    const orr = {}, orKnown = new Set();
    W.links.forEach((l) => {
      if (!(l.dst in idx)) return;
      if (l.type === "AND" && l.src in idx) { ak.push(idx[l.src]); aj.push(idx[l.dst]); }
      else if (l.type === "SOFT" && l.src in idx) { sk.push(idx[l.src]); sj.push(idx[l.dst]); }
      else if (l.type === "OR") {
        const key = l.dst + "|" + (l.group || "OR_" + l.dst);
        if (inst.known.has(l.src)) orKnown.add(key);
        if (l.src in idx) (orr[key] = orr[key] || { j: idx[l.dst], m: [] }).m.push(idx[l.src]);
      }
    });
    const orgroups = Object.keys(orr).filter((k) => !orKnown.has(k)).map((k) => orr[k]);
    const andPred = Array.from({ length: n }, () => []), andSucc = Array.from({ length: n }, () => []);
    ak.forEach((k, e) => { andPred[aj[e]].push(k); andSucc[k].push(aj[e]); });
    const orOf = Array.from({ length: n }, () => []);
    orgroups.forEach((g) => orOf[g.j].push(g.m));
    const sumP = p.reduce((a, b) => a + b, 0);
    const kappa = P.revision_cap_share === undefined ? 0.5 : P.revision_cap_share;
    const ev = { inst, ids, idx, n, p, C, c0: P.start_warmup, rho: P.rho_revision, L: P.L_revision_free, kappa,
      piSoft: P.soft_penalty, ak, aj, sk, sj, orgroups, andPred, andSucc, orOf, sumP, params: P };
    // revision for one link: min(rho * (gap - L)^+, kappa * p_k)   (same as costs.Evaluator.rev_link)
    ev.revLink = (gap, k) => Math.min(ev.rho * Math.max(0, gap - ev.L), kappa * p[k]);
    ev.positions = (seq) => { const pos = new Int32Array(n); seq.forEach((v, k) => (pos[v] = k)); return pos; };
    ev.feasible = (seq, pos) => {
      pos = pos || ev.positions(seq);
      for (let e = 0; e < ak.length; e++) if (pos[ak[e]] >= pos[aj[e]]) return false;
      for (const g of orgroups) if (!g.m.some((k) => pos[k] < pos[g.j])) return false;
      return true;
    };
    ev.breakdown = (seq) => {
      const pos = ev.positions(seq);
      if (seq.length !== n || !ev.feasible(seq, pos)) return { total: INF, feasible: false };
      const end = new Float64Array(n);
      let clock = 0;
      for (const v of seq) { clock += p[v]; end[v] = clock; }
      const start = (v) => end[v] - p[v];
      let trans = n ? ev.c0 : 0, sw = 0;
      for (let k = 0; k + 1 < seq.length; k++) { const c = C[seq[k]][seq[k + 1]]; trans += c; if (c > 0) sw++; }
      let rev = 0, soft = 0;
      for (let e = 0; e < ak.length; e++) rev += ev.revLink(start(aj[e]) - end[ak[e]], ak[e]);
      for (let e = 0; e < sk.length; e++) {
        if (pos[sk[e]] > pos[sj[e]]) soft += ev.piSoft;
        else rev += ev.revLink(start(sj[e]) - end[sk[e]], sk[e]);
      }
      for (const g of orgroups) {
        let m = INF;
        for (const k of g.m) if (pos[k] < pos[g.j]) m = Math.min(m, ev.revLink(start(g.j) - end[k], k));
        rev += m;
      }
      return { total: sumP + trans + rev + soft, study: sumP, transitions: trans, revision: rev, soft_penalty: soft, domain_switches: sw, feasible: true };
    };
    // fast total (no allocation), same summation order as costs._total in Python
    const _pos = new Int32Array(n), _end = new Float64Array(n);
    const orJ = orgroups.map((g) => g.j), orM = orgroups.map((g) => g.m);
    ev.cost = (seq) => {
      const L = seq.length;
      if (L !== n) return INF;
      for (let k = 0; k < L; k++) _pos[seq[k]] = k;
      for (let e = 0; e < ak.length; e++) if (_pos[ak[e]] >= _pos[aj[e]]) return INF;
      for (let g = 0; g < orJ.length; g++) {
        let ok = false; const m = orM[g], pj = _pos[orJ[g]];
        for (let q = 0; q < m.length; q++) if (_pos[m[q]] < pj) { ok = true; break; }
        if (!ok) return INF;
      }
      let clock = 0, tot = 0;
      for (let k = 0; k < L; k++) { const v = seq[k]; clock += p[v]; _end[v] = clock; tot += p[v]; }
      if (L > 0) tot += ev.c0;
      for (let k = 0; k + 1 < L; k++) tot += C[seq[k]][seq[k + 1]];
      const rho = ev.rho, Lr = ev.L;
      for (let e = 0; e < ak.length; e++) {
        const g = _end[aj[e]] - p[aj[e]] - _end[ak[e]] - Lr;
        if (g > 0) tot += Math.min(rho * g, kappa * p[ak[e]]);
      }
      for (let e = 0; e < sk.length; e++) {
        if (_pos[sk[e]] > _pos[sj[e]]) tot += ev.piSoft;
        else { const g = _end[sj[e]] - p[sj[e]] - _end[sk[e]] - Lr; if (g > 0) tot += Math.min(rho * g, kappa * p[sk[e]]); }
      }
      for (let g = 0; g < orJ.length; g++) {
        let best = INF; const j = orJ[g], m = orM[g];
        for (let q = 0; q < m.length; q++) {
          const k = m[q];
          if (_pos[k] < _pos[j]) { const gap = _end[j] - p[j] - _end[k] - Lr; const r = gap > 0 ? Math.min(rho * gap, kappa * p[k]) : 0; if (r < best) best = r; }
        }
        tot += best;
      }
      return tot;
    };
    ev.toIds = (seq) => seq.map((k) => ids[k]);
    ev.fromIds = (arr) => arr.map((t) => idx[t]);
    return ev;
  }

  // ---------------------------------------------------------------- baselines
  function kahn(ev, keyOf) {
    const n = ev.n, indeg = new Int32Array(n), succ = Array.from({ length: n }, () => []);
    const W = ev.inst.W;
    W.links.forEach((l) => {
      if ((l.type === "AND" || l.type === "OR") && l.src in ev.idx && l.dst in ev.idx) {
        succ[ev.idx[l.src]].push(ev.idx[l.dst]); indeg[ev.idx[l.dst]]++;
      }
    });
    const ready = [];
    for (let v = 0; v < n; v++) if (indeg[v] === 0) ready.push(v);
    const out = [];
    while (ready.length) {
      let bi = 0;
      for (let i = 1; i < ready.length; i++) if (cmpTuple(keyOf(ready[i]), keyOf(ready[bi])) < 0) bi = i;
      const u = ready.splice(bi, 1)[0];
      out.push(u);
      for (const v of succ[u]) if (--indeg[v] === 0) ready.push(v);
    }
    return out.length === n ? out : null;
  }
  function curriculumOrder(ev) {
    const T = ev.inst.W.T, groups = {};
    ev.ids.forEach((t) => { const k = T[t].term + "|" + T[t].course; (groups[k] = groups[k] || []).push(t); });
    const rank = {};
    Object.values(groups).forEach((lst) => {
      lst.sort((a, b) => cmpTuple([T[a].order, a], [T[b].order, b]));
      lst.forEach((t, r) => (rank[t] = [T[t].term, (r + 0.5) / lst.length, T[t].course, t]));
    });
    return kahn(ev, (v) => rank[ev.ids[v]]);
  }
  function subjectBySubject(ev) {
    const T = ev.inst.W.T;
    return kahn(ev, (v) => { const t = ev.ids[v]; return [T[t].term, T[t].course, T[t].order, t]; });
  }

  // ---------------------------------------------------------------- availability
  function Avail(ev) {
    const n = ev.n;
    const a = { needAnd: ev.andPred.map((x) => x.length), needOr: ev.orOf.map((x) => x.length),
      orDone: ev.orOf.map((x) => x.map(() => false)), memberOf: {}, done: new Array(n).fill(false) };
    for (let j = 0; j < n; j++) ev.orOf[j].forEach((m, gi) => m.forEach((k) => (a.memberOf[k] = a.memberOf[k] || []).push([j, gi])));
    a.available = (j) => !a.done[j] && a.needAnd[j] === 0 && a.needOr[j] === 0;
    a.mark = (k) => {
      a.done[k] = true;
      for (const j of ev.andSucc[k]) a.needAnd[j]--;
      for (const [j, gi] of a.memberOf[k] || []) if (!a.orDone[j][gi]) { a.orDone[j][gi] = true; a.needOr[j]--; }
    };
    return a;
  }

  // ---------------------------------------------------------------- construction
  function nearestNeighbour(ev) {
    const av = Avail(ev), T = ev.inst.W.T, n = ev.n;
    const seq = [], end = new Float64Array(n), placed = new Array(n).fill(false);
    const softSucc = Array.from({ length: n }, () => []), softPred = Array.from({ length: n }, () => []);
    ev.sk.forEach((k, e) => { softSucc[k].push(ev.sj[e]); softPred[ev.sj[e]].push(k); });
    const curKey = (j) => [T[ev.ids[j]].term, T[ev.ids[j]].order];
    let clock = 0;
    while (seq.length < n) {
      const cand = [];
      for (let j = 0; j < n; j++) if (av.available(j)) cand.push(j);
      let bj = null;
      if (!seq.length) {
        bj = cand[0];
        for (const j of cand) if (cmpTuple(curKey(j), curKey(bj)) < 0) bj = j;
      } else {
        let best = INF;
        const last = seq[seq.length - 1];
        for (const j of cand) {
          let inc = ev.C[last][j];
          for (const k of ev.andPred[j]) inc += ev.revLink(clock - end[k], k);
          for (const k of softPred[j]) if (placed[k]) inc += ev.revLink(clock - end[k], k);
          for (const k of softSucc[j]) if (placed[k]) inc += ev.piSoft;
          if (inc < best - 1e-12 || (Math.abs(inc - best) <= 1e-12 && cmpTuple(curKey(j), curKey(bj)) < 0)) { best = inc; bj = j; }
        }
      }
      seq.push(bj); av.mark(bj); placed[bj] = true; clock += ev.p[bj]; end[bj] = clock;
    }
    return seq;
  }
  function cheapestInsertion(ev) {
    const n = ev.n, S = n, E = n + 1;
    const cx = (a, b) => (a === S ? (b < n ? ev.c0 : 0) : b === E ? 0 : ev.C[a][b]);
    let tour = [S, E];
    const av = Avail(ev);
    let pos = { [S]: 0, [E]: 1 };
    while (tour.length < n + 2) {
      let best = null;
      for (let k = 0; k < n; k++) {
        if (!av.available(k)) continue;
        let lo = 0;
        for (const a of ev.andPred[k]) lo = Math.max(lo, pos[a]);
        for (const m of ev.orOf[k]) {
          const pl = m.filter((x) => x in pos).map((x) => pos[x]);
          if (pl.length) lo = Math.max(lo, Math.min(...pl));
        }
        let bd = INF, br = 0;
        for (let r = lo; r < tour.length - 1; r++) {
          const d = cx(tour[r], k) + cx(k, tour[r + 1]) - cx(tour[r], tour[r + 1]);
          if (d < bd) { bd = d; br = r; }
        }
        if (best === null || bd < best[0]) best = [bd, k, br];
      }
      tour.splice(best[2] + 1, 0, best[1]);
      pos = {}; tour.forEach((v, i) => (pos[v] = i));
      av.mark(best[1]);
    }
    return tour.slice(1, -1);
  }
  function randomTopological(ev, rng) {
    const av = Avail(ev), seq = [];
    while (seq.length < ev.n) {
      const cand = [];
      for (let j = 0; j < ev.n; j++) if (av.available(j)) cand.push(j);
      const j = cand[Math.floor(rng() * cand.length)];
      seq.push(j); av.mark(j);
    }
    return seq;
  }

  // ---------------------------------------------------------------- improvement
  function windowOf(ev, seq, s, e) {
    const seg = new Set(seq.slice(s, e)), pos = ev.positions(seq);
    let lo = 0, hi = seq.length;
    seg.forEach((v) => {
      for (const a of ev.andPred[v]) if (!seg.has(a)) lo = Math.max(lo, pos[a] + 1);
      for (const b of ev.andSucc[v]) if (!seg.has(b)) hi = Math.min(hi, pos[b]);
    });
    return [lo, hi];
  }
  function orOpt(ev, seq, cur) {
    if (cur === undefined) cur = ev.cost(seq);
    let improved = false;
    const n = seq.length, buf = new Int32Array(n);
    for (const p of [3, 2, 1]) {
      let s = 0;
      while (s + p <= n) {
        const [lo, hi] = windowOf(ev, seq, s, s + p);
        const seg = seq.slice(s, s + p), rest = seq.slice(0, s).concat(seq.slice(s + p));
        const loR = lo <= s ? lo : lo - p, hiR = hi <= s ? hi : hi - p;
        let best = cur, bins = -1;
        for (let ins = Math.max(0, loR); ins <= Math.min(rest.length, hiR); ins++) {
          if (ins === s) continue;
          let q = 0;
          for (let k = 0; k < ins; k++) buf[q++] = rest[k];
          for (let k = 0; k < p; k++) buf[q++] = seg[k];
          for (let k = ins; k < rest.length; k++) buf[q++] = rest[k];
          const c = ev.cost(buf);
          if (c < best - 1e-9) { best = c; bins = ins; }
        }
        if (bins >= 0) { seq = rest.slice(0, bins).concat(seg, rest.slice(bins)); cur = best; improved = true; }
        s++;
      }
    }
    return [seq, cur, improved];
  }
  function twoOpt(ev, seq, cur) {
    if (cur === undefined) cur = ev.cost(seq);
    let improved = false;
    const n = seq.length, buf = new Int32Array(n);
    for (let i = 0; i < n - 1; i++) {
      let inside = new Set([seq[i]]);
      for (let j = i + 1; j < n; j++) {
        const v = seq[j];
        if (ev.andPred[v].some((a) => inside.has(a))) break;
        inside.add(v);
        for (let k = 0; k < n; k++) buf[k] = seq[k];
        for (let k = i, m = j; k <= j; k++, m--) buf[k] = seq[m];
        const c = ev.cost(buf);
        if (c < cur - 1e-9) { seq = Array.from(buf); cur = c; improved = true; inside = new Set(seq.slice(i, j + 1)); }
      }
    }
    return [seq, cur, improved];
  }
  function localSearch(ev, seq, maxRounds) {
    let cur = ev.cost(seq);
    for (let r = 0; r < (maxRounds || 50); r++) {
      let a, b;
      [seq, cur, a] = orOpt(ev, seq, cur);
      [seq, cur, b] = twoOpt(ev, seq, cur);
      if (!a && !b) break;
    }
    return [seq, cur];
  }
  function solve(ev, opts) {
    opts = opts || {};
    const t0 = Date.now(), limit = opts.timeLimitMs || 1500, rng = mulberry32(opts.seed || 1);
    // large scopes (e.g. the 266-topic web): only the two strongest constructions, no random restarts,
    // so the browser answers in a few seconds. Python (src/speedrun) runs every start for the report.
    const big = ev.n > 120;
    const starts = big ? { CI: cheapestInsertion(ev), NN: nearestNeighbour(ev) }
      : { NN: nearestNeighbour(ev), CI: cheapestInsertion(ev), B0: curriculumOrder(ev), B1: subjectBySubject(ev) };
    if (big && opts.restarts === undefined) opts.restarts = 0;
    let best = INF, bseq = null;
    const log = [];
    for (const [name, s] of Object.entries(starts)) {
      const c0 = ev.cost(s), [s2, c2] = localSearch(ev, s.slice());
      log.push({ start: name, construct: c0, improved: c2 });
      if (c2 < best) { best = c2; bseq = s2; }
    }
    let r = 0;
    while (Date.now() - t0 < limit && r < (opts.restarts === undefined ? 20 : opts.restarts)) {
      const s = randomTopological(ev, rng), [s2, c2] = localSearch(ev, s);
      log.push({ start: "rand" + r, construct: ev.cost(s), improved: c2 });
      if (c2 < best) { best = c2; bseq = s2; }
      r++;
    }
    return { seq: bseq, cost: best, log, ms: Date.now() - t0 };
  }

  // ---------------------------------------------------------------- days (shortest path split)
  function dayHours(ev, seq, a, b) {
    let h = ev.params.day_warmup;
    for (let k = a; k < b; k++) h += ev.p[seq[k]];
    for (let k = a; k < b - 1; k++) h += ev.C[seq[k]][seq[k + 1]];
    return h;
  }
  function splitDays(ev, seq, H) {
    H = H || ev.params.day_hours;
    const n = seq.length, BIG = 1e6, u = new Array(n + 1).fill(INF), pred = new Array(n + 1).fill(-1);
    u[0] = 0;
    for (let a = 0; a < n; a++) {
      if (u[a] === INF) continue;
      for (let b = a + 1; b <= n; b++) {
        const h = dayHours(ev, seq, a, b);
        if (!(h <= H + 1e-9 || b === a + 1)) break;
        const days = Math.max(1, Math.ceil(h / H - 1e-9));
        const c = u[a] + BIG * days + h;
        if (c < u[b] - 1e-9) { u[b] = c; pred[b] = a; }
      }
    }
    const cuts = [];
    for (let b = n; b > 0; b = pred[b]) cuts.unshift([pred[b], b]);
    const days = cuts.map(([a, b]) => ({ topics: seq.slice(a, b).map((k) => ev.ids[k]), hours: dayHours(ev, seq, a, b) }));
    const nDays = days.reduce((s, d) => s + Math.max(1, Math.ceil(d.hours / H - 1e-9)), 0);
    return { days, nDays, lbDays: Math.ceil(ev.sumP / H - 1e-9), totalHours: days.reduce((s, d) => s + d.hours, 0), H };
  }

  // ---------------------------------------------------------------- crunch (profit-maximising tour)
  function partialCost(ev, seq) {
    if (!seq.length) return 0;
    const pos = {}; seq.forEach((v, k) => (pos[v] = k));
    let h = ev.c0;
    for (const v of seq) h += ev.p[v];
    for (let k = 0; k + 1 < seq.length; k++) h += ev.C[seq[k]][seq[k + 1]];
    const end = {}; let clock = 0;
    for (const v of seq) { clock += ev.p[v]; end[v] = clock; }
    ev.ak.forEach((k, e) => { const j = ev.aj[e]; if (k in pos && j in pos) h += ev.revLink(end[j] - ev.p[j] - end[k], k); });
    ev.sk.forEach((k, e) => {
      const j = ev.sj[e];
      if (k in pos && j in pos) h += pos[k] > pos[j] ? ev.piSoft : ev.revLink(end[j] - ev.p[j] - end[k], k);
    });
    return h;
  }
  function closureHours(ev, k, have) {
    let tot = 0; const stack = [k], seen = new Set(have);
    while (stack.length) { const v = stack.pop(); if (seen.has(v)) continue; seen.add(v); tot += ev.p[v]; stack.push(...ev.andPred[v]); }
    return tot;
  }
  function closureOf(ev, i, have) {
    const out = [], seen = new Set(have);
    (function add(v, depth) {
      if (seen.has(v) || depth > 60) return;
      for (const a of ev.andPred[v]) add(a, depth + 1);
      for (const m of ev.orOf[v]) {
        if (m.some((k) => seen.has(k))) continue;
        let best = m[0];
        for (const k of m) if (closureHours(ev, k, seen) < closureHours(ev, best, seen)) best = k;
        add(best, depth + 1);
      }
      seen.add(v); out.push(v);
    })(i, 0);
    return out;
  }
  function insertCheapest(ev, tour, v) {
    // Delta_ijk = c_iv + c_vj - c_ij (S1 sl.33; delta_i of S9 sl.18), after v's prerequisites
    const pos = {}; tour.forEach((t, k) => (pos[t] = k));
    let lo = 0;
    for (const a of ev.andPred[v]) if (a in pos) lo = Math.max(lo, pos[a] + 1);
    for (const m of ev.orOf[v]) { const pl = m.filter((k) => k in pos).map((k) => pos[k]); if (pl.length) lo = Math.max(lo, Math.min(...pl) + 1); }
    const cx = (a, b) => (a === null ? (b !== null ? ev.c0 : 0) : b === null ? 0 : ev.C[a][b]);
    let best = INF, bins = lo;
    for (let ins = lo; ins <= tour.length; ins++) {
      const a = ins > 0 ? tour[ins - 1] : null, b = ins < tour.length ? tour[ins] : null;
      const d = cx(a, v) + cx(v, b) - cx(a, b);
      if (d < best - 1e-12) { best = d; bins = ins; }
    }
    return tour.slice(0, bins).concat([v], tour.slice(bins));
  }
  function profitMaxTour(ev, budget, nStarts) {
    const T = ev.inst.W.T, vals = ev.ids.map((t) => T[t].value);
    const roots = [];
    for (let i = 0; i < ev.n; i++) if (!ev.andPred[i].length && !ev.orOf[i].length) roots.push(i);
    roots.sort((a, b) => -vals[a] / ev.p[a] + vals[b] / ev.p[b]);
    let bestRes = null;
    for (const k of [null].concat(roots.slice(0, Math.max(0, (nStarts || 5) - 1)))) {
      let tour = [];
      if (k !== null && ev.p[k] + ev.c0 <= budget) tour = [k];
      for (;;) {
        const have = new Set(tour), cur = partialCost(ev, tour);
        let best = null;
        for (let i = 0; i < ev.n; i++) {
          if (have.has(i)) continue;
          const K = closureOf(ev, i, have);
          let t2 = tour.slice();
          for (const v of K) t2 = insertCheapest(ev, t2, v);
          const h2 = partialCost(ev, t2);
          if (h2 > budget + 1e-9) continue;
          const ratio = K.reduce((s, v) => s + vals[v], 0) / Math.max(1e-6, h2 - cur);
          if (best === null || ratio > best[0]) best = [ratio, t2];
        }
        if (best === null) break;
        tour = best[1];
      }
      const val = tour.reduce((s, v) => s + vals[v], 0), hrs = partialCost(ev, tour);
      if (bestRes === null || val > bestRes.value || (val === bestRes.value && hrs < bestRes.hours)) bestRes = { seq: tour, value: val, hours: hrs };
    }
    const inSet = new Set(bestRes.seq);
    bestRes.ids = bestRes.seq.map((k) => ev.ids[k]);
    bestRes.leftOut = ev.ids.filter((_, k) => !inSet.has(k));
    bestRes.totalValue = vals.reduce((a, b) => a + b, 0);
    return bestRes;
  }

  const api = { indexWeb, buildInstance, Evaluator, curriculumOrder, subjectBySubject, nearestNeighbour,
    cheapestInsertion, randomTopological, orOpt, twoOpt, localSearch, solve, splitDays, profitMaxTour, partialCost };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SpeedrunCore = api;
})(typeof self !== "undefined" ? self : this);
