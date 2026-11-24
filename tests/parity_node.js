// node tests/parity_node.js docs/data/web.json  -> prints JSON of JS results per preset
const core = require("../docs/planner-core.js");
const web = require(require("path").resolve(process.argv[2]));
const W = core.indexWeb(web);
const out = {};
for (const pr of web.presets) {
  const inst = core.buildInstance(W, pr, pr.params || {});
  const ev = core.Evaluator(inst);
  const b0 = core.curriculumOrder(ev), b1 = core.subjectBySubject(ev);
  const nn = core.nearestNeighbour(ev), ci = core.cheapestInsertion(ev);
  const [nnLs, nnLsC] = core.localSearch(ev, nn.slice());
  const r = { ids: inst.ids, added: inst.added, B0: ev.cost(b0), B1: ev.cost(b1), NN: ev.cost(nn), CI: ev.cost(ci),
    NN_LS: nnLsC, B0_ids: ev.toIds(b0), NN_ids: ev.toIds(nn), CI_ids: ev.toIds(ci), NN_LS_ids: ev.toIds(nnLs) };
  const sp = core.splitDays(ev, nnLs); r.days = sp.nDays; r.dayHours = sp.totalHours;
  if (pr.budget) { const c = core.profitMaxTour(ev, pr.budget); r.crunch = { value: c.value, hours: c.hours, ids: c.ids }; }
  out[pr.name] = r;
}
console.log(JSON.stringify(out));
