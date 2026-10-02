"""Generate the rewrite's figures and data tables from the frozen v4 result files.

Reads only results/ (no writes there). Writes LaTeX into manuscript/fse2027/figures/ and manuscript/fse2027/tables/.
Every number in these files comes from a result JSON; nothing is typed by hand.
Run: .venv\\Scripts\\python.exe -B manuscript\\tools\\make_v4_figures.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "results"
FIG = ROOT / "manuscript/fse2027/figures"
TAB = ROOT / "manuscript/fse2027/tables"

NAMES = {
    "mra": "Pooled order (MRA)",
    "best_config_top1": "Best configuration, top-1",
    "first_global": "First global position",
    "borda": "Borda count",
    "rrf": "Reciprocal-rank fusion",
    "mean_norm_position": "Mean normalised position",
    "occurrence": "Occurrence count",
    "mra_then_occurrence": "MRA, then occurrence",
    "testability": "Testability product",
    "one_stage": "One-stage logistic",
    "source_agnostic": "Source-agnostic refit",
    "token_similarity": "Token similarity",
    "codet5_similarity": "CodeT5+ similarity",
    "naturalness": "Naturalness",
    "entropy_delta": "Entropy delta",
    "uniform": "Uniform random",
}
STEPS = ["E0 archived", "E1 +census", "+F2 census top-up", "+F3 generated tests", "+F4 human review",
         "Final (+R fix re-run)"]
SHORT = ["E0", "E1", "E2", "E3", "E4", "E5"]
RLKEY = ["E0", "E1", "F2", "F3", "F4", "R"]  # step names inside refutation_limit.json


def load(p):
    return json.loads((R / p).read_text(encoding="utf-8"))


def iv(lo, hi):
    return f"$[{lo:+.2f},\\,{hi:+.2f}]$"


def decided(lo, hi):
    return lo > 0 or hi < 0


# ------------------------------------------------------------------ Table: Defects4J decidability
def table_d4j(dec, basis):
    rows = {r["b"]: r for r in dec["defects4j"]["comparisons"]}
    bas = {r["b"]: r for r in basis["comparisons"]}
    out = [r"\begin{tabular}{@{}l" + "c" * 6 + r"rrrr@{}}", r"\toprule",
           r" & \multicolumn{6}{c}{Decided after evidence layer} & \multicolumn{4}{c}{Final evidence} \\",
           r"\cmidrule(lr){2-7}\cmidrule(l){8-11}",
           r"Baseline & " + " & ".join(SHORT) +
           r" & Interval (pp) & Flips & Human & Break-even \\", r"\midrule"]
    order = ["mra", "first_global", "borda", "rrf", "mean_norm_position", "occurrence", "mra_then_occurrence",
             "token_similarity", "codet5_similarity", "naturalness", "entropy_delta", "uniform",
             "source_agnostic", "one_stage", "testability", "best_config_top1"]
    for b in order:
        r, s = rows[b], bas[b]
        marks = []
        for st in STEPS:
            lo, hi = r[st]["pp"]
            marks.append(r"$\bullet$" if decided(lo, hi) else r"$\circ$")
        lo, hi = s["interval_pp"]
        flips = r["robustness"]["label_flips_to_reopen_any"]
        hum = s["human_archived"] + s["human_F4"]
        out.append(f"{NAMES[b]} & " + " & ".join(marks) + f" & {iv(lo, hi)} & {flips} & {hum} & "
                   f"{100 * s['eps_star']:.1f}\\% \\\\")
        if b == "uniform":
            out.append(r"\midrule")
    d = dec["defects4j"]["decided_by_step"]
    out.append(r"\midrule")
    out.append(r"Decided & " + " & ".join(str(d[st]) for st in STEPS) + r" & 16 of 16 & & & \\")
    out += [r"\bottomrule", r"\end{tabular}"]
    (TAB / "decidability_d4j.tex").write_text("\n".join(out) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ Figure: interval trajectories
def figure_trajectories(rl, dec, he):
    res = rl["defects4j"]["results"]
    g1 = rl["g1"]["results"]["challenger_frozen vs occurrence"]
    her = rl["humaneval"]["results"]["native_position"]

    def panel(groups, xmin, xmax, xtick):
        """groups: list of (title, [(steplabel, lo, hi, a0), ...]). One pgfplots axis body."""
        lines, ticks, labels, heads, y = [], [], [], [], 0.0
        for title, rows in groups:
            heads.append((title, y + 0.75))
            for label, lo, hi, a0 in rows:
                style = "dec" if decided(lo, hi) else "opn"
                lines.append(f"\\addplot[{style}] coordinates {{({lo:.4f},{y:.2f}) ({hi:.4f},{y:.2f})}};")
                lines.append(f"\\addplot[a0mark] coordinates {{({a0:.4f},{y:.2f})}};")
                ticks.append(f"{y:.2f}")
                labels.append(label)
                y -= 1
            y -= 1.3
        ymin, ymax = y + 0.6, 1.4
        opts = (f"xmin={xmin},xmax={xmax},ymin={ymin:.2f},ymax={ymax:.2f},xtick={{{xtick}}},"
                f"ytick={{{','.join(ticks)}}},yticklabels={{{','.join(labels)}}}")
        body = [f"\\draw[densely dashed,gray!70] (axis cs:0,{ymin:.2f}) -- (axis cs:0,{ymax:.2f});"] + lines
        for title, yy in heads:
            body.append(f"\\node[grouphead] at (axis cs:{xmin},{yy:.2f}) {{{title}}};")
        return opts, body

    d4j = lambda b: (NAMES[b], [(lab, res[b][k]["L"], res[b][k]["H"], res[b][k]["A0"]) for lab, k in zip(SHORT, RLKEY)])
    pa = panel([d4j("mra"), d4j("occurrence"), d4j("source_agnostic")], -2, 12, "-2,0,2,...,12")
    pb = panel([d4j("best_config_top1"), d4j("one_stage"), d4j("testability")], -1.5, 2.5, "-1,0,1,2")
    pc = panel([("HumanEval-Java, vs pooled order",
                 [("Archived", her["archived"]["L"], her["archived"]["H"], her["archived"]["A0"]),
                  ("Final", her["HE-E1"]["L"], her["HE-E1"]["H"], her["HE-E1"]["A0"])]),
                ("Fresh campaign, vs occurrence",
                 [("G-E0", g1["G-E0"]["L"], g1["G-E0"]["H"], g1["G-E0"]["A0"]),
                  ("G-E1", g1["G-E1"]["L"], g1["G-E1"]["H"], g1["G-E1"]["A0"])])], -20, 32, "-20,-10,0,10,20,30")
    out = [r"\begin{tikzpicture}",
           r"\tikzset{grouphead/.style={anchor=south west,font=\scriptsize\itshape,inner sep=1pt}}",
           r"\pgfplotsset{dec/.style={line width=2.4pt,color=decblue},opn/.style={line width=2.4pt,color=opengray},",
           r"  a0mark/.style={only marks,mark=diamond*,mark size=2.2pt,color=black,mark options={fill=white}}}",
           r"\begin{groupplot}[group style={group size=3 by 1,horizontal sep=0.95cm},",
           r"  width=0.33\linewidth,height=5.9cm,axis x line*=bottom,axis y line*=left,",
           r"  xlabel={$\Delta$ (pp)},xlabel style={font=\footnotesize},",
           r"  tick label style={font=\scriptsize},y tick label style={font=\tiny},clip=false]"]
    for key, (opts, body) in zip("abc", (pa, pb, pc)):
        out.append(f"\\nextgroupplot[{opts},title={{({key})}},title style={{font=\\footnotesize}}]")
        out += body
    out += [r"\end{groupplot}", r"\end{tikzpicture}"]
    (FIG / "trajectories.tex").write_text("\n".join(out) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ Figure: positive controls by configuration
CFG_NAMES = {  # display names as in analysis_tools/v4/positive_controls.py (SHORT)
    "gpt4_gpt-zero-shot": "GPT-4", "gpt35_gpt-zero-shot": "GPT-3.5",
    "repairllama_ir4_or2": r"RepairLLaMA IR4$\times$OR2",
    "repairllama_ir1_or1": r"LoRA IR1$\times$OR1", "repairllama_ir1_or3": r"LoRA IR1$\times$OR3",
    "repairllama_ir1_or4": r"LoRA IR1$\times$OR4", "repairllama_ir2_or2": r"LoRA IR2$\times$OR2",
    "repairllama_ir3_or2": r"LoRA IR3$\times$OR2", "deepseek_base": "DeepSeek base",
    "deepseek_fft": "DeepSeek full FT", "deepseek_lora": "DeepSeek LoRA",
    "zero-shot-cloze_codellama": "CodeLlama zero-shot IR3", "zero-shot-cloze_codellama-ir4": "CodeLlama zero-shot IR4",
    "zero-shot-cloze_repairllama-fft": "CodeLlama full FT",
}


def cfg_label(k):
    return CFG_NAMES[k]


def figure_positive_controls(pc):
    d4 = pc["artifacts"]["repairllama_defects4j"]["levels"]["L1_text"]["per_config"]
    he = pc["artifacts"]["repairllama_humanevaljava"]["levels"]["L1_text"]["per_config"]
    keys = sorted(set(d4) | set(he), key=lambda k: -(d4.get(k, {}).get("occurrences", {}).get("rate", 0)))
    rows = []
    for k in keys:
        a = d4.get(k, {}).get("occurrences", {})
        b = he.get(k, {}).get("occurrences", {})
        rows.append((k, a.get("k"), a.get("n"), a.get("rate"), b.get("k"), b.get("n"), b.get("rate")))
    (TAB / "positive_controls_raw.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    sym = ",".join("{" + cfg_label(k) + f" ({r[1]}/{r[4]})" + "}" for k, *r in reversed(rows))
    coords_d4 = " ".join(f"({100 * (r[3] or 0):.1f},{i})" for i, r in enumerate(reversed(rows)))
    coords_he = " ".join(f"({100 * (r[6] or 0):.1f},{i})" for i, r in enumerate(reversed(rows)))
    out = [r"\begin{tikzpicture}",
           r"\begin{axis}[xbar=0pt,bar width=3.3pt,width=0.62\linewidth,height=5.5cm,",
           r"  xmin=0,xmax=80,xlabel={Fix copies archived as failing (\%)},xlabel style={font=\footnotesize},",
           f"  ytick={{0,...,{len(rows) - 1}}},yticklabels={{{sym}}},",
           r"  y tick label style={font=\scriptsize},x tick label style={font=\scriptsize},",
           r"  enlarge y limits=0.04,area legend,legend style={font=\scriptsize,at={(0.98,0.03)},anchor=south east,draw=none},",
           r"  axis x line*=bottom,axis y line*=left]",
           f"\\addplot[fill=decblue,draw=none] coordinates {{{coords_d4}}};",
           f"\\addplot[fill=opengray,draw=none] coordinates {{{coords_he}}};",
           r"\legend{Defects4J,HumanEval-Java}",
           r"\end{axis}", r"\end{tikzpicture}"]
    (FIG / "positive_controls.tex").write_text("\n".join(out) + "\n", encoding="utf-8")
    return rows


# ------------------------------------------------------------------ Table: pre-flight check
def table_preflight(rl):
    camps = dict(rl["defects4j"]["campaigns"])
    camps.update(rl["g1"]["campaigns"])
    rows = []
    for name, c in camps.items():
        if "G-E2a" in name:  # the optional stage was not completed; its numbers are not reported
            continue
        open_ = c.get("comparisons_open_at_start") or {}
        reach = []
        for b, v in open_.items():
            st = v.get("status", "")
            if st.startswith("reachable"):
                reach.append(f"{b}: {v['k_min']}/{v['helpful_classes']}")
        rows.append({"campaign": name, "hours": c.get("hours"), "open": len(open_),
                     "reachable": reach, "newly": c.get("newly_decided"), "semantics": c.get("semantics")})
    (TAB / "preflight_raw.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    dec = load("v4/decidability/decidability.json")
    basis = load("v4/decision_basis/decision_basis.json")
    rl = load("v4/refutation_limit/refutation_limit.json")
    pc = load("v4/positive_controls/positive_controls.json")
    he = load("v4/humaneval/e3_results.json")
    table_d4j(dec, basis)
    figure_trajectories(rl, dec, he)
    rows = figure_positive_controls(pc)
    table_preflight(rl)
    table_settings_decided(dec, rl)
    table_preflight_tex(rl)
    print("positive-control rows:", len(rows))


# ------------------------------------------------------------------ Tables added for the rewrite (settings, pre-flight)
def table_settings_decided(dec, rl):
    D = dec["defects4j"]
    mra = next(r for r in D["comparisons"] if r["b"] == "mra")
    H = dec["humaneval"]
    nat = next(r for r in H["comparisons"] if r["b"] == "native_position")
    G = dec["g1"]["comparisons"][0]
    O = dec["others"]
    rb = next(p for p in O["repairbench"] if p["a"] == "challenger_frozen" and p["b"] == "occurrence")
    d4c = next(p for p in O["d4c_trigger_passage"] if p["a"] == "challenger_frozen" and p["b"] == "occurrence")
    d2 = next(p for p in O["d2_plausible_pools"] if p["a"] == "challenger" and p["b"] == "prevarank")
    e2 = json.loads((R / "v4/prevarank/e2_analysis.json").read_text(encoding="utf-8"))
    sh = e2["views"]["E1"]["per_run"]["stable_hash_v1"]["vs_canonical_pp"]
    pod = json.loads((R / "v4/pod/pod_analysis.json").read_text(encoding="utf-8"))
    pp = next(p for p in pod["pairs"] if {p["a"], p["b"]} == {"llm4patchcorrect", "tian_dl4patchcorrectness"})
    lo, hi = pp["bounds_pp"] if "bounds_pp" in pp else pp["exact_bounds_pp"]
    if pp["a"] != "llm4patchcorrect":
        lo, hi = -hi, -lo
    n_rb = sum(p["identified"] for p in O["repairbench"])
    n_d4c = sum(r["result"] != "open" for r in O["d4c_trigger_passage"])
    n_d2 = sum(r["identified"] for r in O["d2_plausible_pools"])
    p1 = json.loads((R / "v4/p1_prospective/outcomes.json").read_text(encoding="utf-8"))
    p1c = next(c for c in p1["comparisons"] if c["comparison"] == "challenger vs prevarank")
    pr = O["prevarank_input_order"]
    po = O["pod_pairs"]
    arrow = r" $\rightarrow$ "
    g1d = [sum(r[v]["result"] != "open" for r in dec["g1"]["comparisons"]) for v in ("G-E0", "G-E1")]
    rows = [
        ("Defects4J", D["n"], f"{D['decided_by_step']['E0 archived']}{arrow}{D['decided_by_step']['Final (+R fix re-run)']}",
         "vs pooled order", iv(*mra["E0 archived"]["pp"]), iv(*mra["Final (+R fix re-run)"]["pp"])),
        ("HumanEval-Java", len(H["comparisons"]), f"{H['decided_A0']}{arrow}{H['decided_HE-E1']}",
         "vs pooled order", iv(*nat["A0"]["equal_bug_pp"]), iv(*nat["HE-E1"]["equal_bug_pp"])),
        ("Fresh campaign", len(dec["g1"]["comparisons"]), f"{g1d[0]}{arrow}{g1d[1]}",
         "vs occurrence", iv(*G["G-E0"]["pp"]), iv(*G["G-E1"]["pp"])),
        ("RepairBench", len(O["repairbench"]), str(n_rb), "vs occurrence", iv(*rb["pp"]), "--"),
        ("D4C", len(O["d4c_trigger_passage"]), str(n_d4c), "vs occurrence", iv(*d4c["pp"]), "--"),
        ("Second decision point", len(O["d2_plausible_pools"]), f"{n_d2}{arrow}{p1['decided_at_end']}", "vs PrevaRank",
         iv(*d2["pp"]), iv(*p1c["end_interval_pp"])),
        ("PrevaRank input order", pr["permutations_vs_canonical"], str(pr["decided"]), "hash vs supplied order", iv(*sh), "--"),
        ("Overfitting detectors", po["pairs"], str(po["identified"]), "LLM4PC vs DL4PC", iv(lo, hi), "--"),
    ]
    out = [r"\begin{tabular}{@{}lrllrr@{}}", r"\toprule",
           r"Setting & Pairs & Decided & Example & First view & Last view \\", r"\midrule"]
    for row in rows:
        out.append(" & ".join(str(x) for x in row) + r" \\")
    out += [r"\bottomrule", r"\end{tabular}"]
    (TAB / "settings_decided.tex").write_text("\n".join(out) + "\n", encoding="utf-8")


PRETTY = {"best_config_top1": "best configuration", "testability": "testability", "one_stage": "one-stage",
          "source_agnostic": "source-agnostic"}


def table_preflight_tex(rl):
    """Table 6: target-aware pre-flight check (results/v4/target_aware_preflight_v1, review finding V8-01).
    One row per Defects4J comparison open in the archive, one column per campaign; the fresh campaign is one row."""
    ta = load("v4/target_aware_preflight_v1/target_aware_preflight.json")
    rr = rl["defects4j"]["campaigns"]["R (F4 -> R)"]
    C = ta["defects4j"]["campaigns"]
    camps = [("Census", "Census"), ("Top-up", "Top-up"), ("Generated tests", "Generated tests")]
    comps = list(C["Census"]["comparisons"])  # the four comparisons open in the archive
    dash = "--"

    def cell(a):
        t = a["targeted"]
        if a["outcome"] == "decided":
            return (f"decided: {t['k_min']:,} needed, {t['helpful_targeted_refuted']:,} of "
                    f"{t['helpful_classes_targeted']:,} refuted")
        if a["outcome"] == "type cannot decide":
            return r"type: $\Delta_0=0$" if a["A0"] == 0 else "type: conflict-locked"
        if a["outcome"] == "type could, targets not":
            return f"targets: 0 of {t['helpful_classes_under_rule']:,} helpful"
        return "too few failed"

    head = " & ".join([r"Comparison"] + [f"{n} ({C[k]['hours']:.1f} h)" for n, k in camps]
                      + [f"Fix re-run ({rr['hours']:.1f} h)"])
    out = [r"\begin{tabularx}{\linewidth}{@{}>{\raggedright\arraybackslash}p{2.5cm}YYYY@{}}", r"\toprule",
           head + r" \\", r"\midrule"]
    for b in comps:
        row = [NAMES.get(b, b)]
        for _, k in camps:
            a = C[k]["comparisons"].get(b)
            row.append(cell(a) if a else dash)
        row.append("decided (not refuting)" if b in rr["newly_decided"] else dash)
        out.append(" & ".join(row) + r" \\")
    G = ta["g1"]
    assert all(a["outcome"] == "targets could, too few failed" for a in G["comparisons"].values())
    p1 = G["comparisons"][G["primary"]]["targeted"]
    sec = [a["targeted"] for k, a in G["comparisons"].items() if k != G["primary"]]
    g_hours = G["tier_P"]["hours"] + G["tier_S"]["hours"]
    span = r"\multicolumn{4}{>{\raggedright\arraybackslash}p{\dimexpr\linewidth-2.5cm-3\tabcolsep\relax}}"
    out += [r"\midrule",
            f"Fresh campaign, G-E1 ({g_hours:.1f} h) & {span}{{too few failed in all five: "
            f"primary {p1['k_min']:,} needed, {p1['helpful_targeted_refuted']:,} refuted; "
            f"secondaries each $\\geq${min(t['k_min'] for t in sec):,} needed, "
            f"$\\leq${max(t['helpful_targeted_refuted'] for t in sec):,} refuted}} \\\\",
            r"\bottomrule", r"\end{tabularx}"]
    (TAB / "preflight.tex").write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
