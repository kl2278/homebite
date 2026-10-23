"""Build submission/report.html: one self-contained HTML report (inline CSS, base64 images, inline SVG).

Run: python submission/build_report.py          (from the repo root; needs only the standard library and Pillow)

Numbers are read from the repo's own files (logs/*.md, logs/token_report.csv, safety.py, usage.py, README.md, data/*.csv).
The pytest count is measured by running pytest (no tokens are spent). Anything that is not in a file is written in this
script as a MY INPUTS item and is labelled as such in the appendix.
"""

import base64
import csv
import html
import io
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SUB = ROOT / "submission"
SHOTS = SUB / "screenshots"
OUT = SUB / "report.html"
MAX_WIDTH = 1400


# ================================================================ reading facts from files

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def md_table(text: str, header_start: str) -> list[list[str]]:
    """Rows (list of cells) of the first markdown table whose header line starts with header_start."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(header_start):
            rows = []
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                rows.append([c.strip() for c in row.strip().strip("|").split("|")])
            return rows
    raise KeyError(header_start)


def num(text: str) -> float:
    return float(re.sub(r"[^0-9.\-]", "", text))


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.strip()


summary = read("logs/token_summary.md")
experiment = read("logs/cost_experiment.md")
safety_demo = read("logs/safety_demo_output.txt")
allergen_fix = read("logs/allergen_fix_check.md")
safety_src = read("safety.py")
usage_src = read("usage.py")
csv_rows = list(csv.DictReader((ROOT / "logs" / "token_report.csv").open(encoding="utf-8")))
dishes = {d["id"]: d for d in json.loads(read("data/measurement_dishes.json"))}


def const(name: str, source: str = safety_src) -> float:
    return float(re.search(rf"^{name} = ([0-9_.]+)", source, re.M).group(1).replace("_", ""))


PRICE = {k: const(k, usage_src) for k in ("INPUT_PRICE_PER_M", "CACHED_INPUT_PRICE_PER_M", "CACHE_WRITE_PRICE_PER_M", "OUTPUT_PRICE_PER_M")}


def run_cost(r: dict) -> float:
    stages = ("guard", "intake", "analyst", "substitution", "writer")
    total = 0.0
    for s in stages:
        i, c, w, o = (float(r[f"{s}_{k}"]) for k in ("input", "cached", "cache_write", "output"))
        total += ((i - c - w) * PRICE["INPUT_PRICE_PER_M"] + c * PRICE["CACHED_INPUT_PRICE_PER_M"]
                  + w * PRICE["CACHE_WRITE_PRICE_PER_M"] + o * PRICE["OUTPUT_PRICE_PER_M"]) / 1e6
    return total


F: dict = {}
per_run = {row[0]: row[1:] for row in md_table(summary, "| Metric | Average | p90 |")}
for key, label in (("in", "Input tokens"), ("cached", "Cached input tokens"), ("out", "Output tokens"), ("cost", "Cost"), ("lat", "Latency (s)")):
    F[f"avg_{key}"], F[f"p90_{key}"] = per_run[label]
F["cache_ratio"] = re.search(r"Cache hit ratio.*?\*\*([0-9.]+%)\*\*", summary).group(1)
F["stages"] = {row[0]: row[1:] for row in md_table(summary, "| Stage | Input |")}
F["proj"] = {row[0]: row for row in md_table(summary, "| Users | Runs per month |")}
F["daily_obs"] = re.search(r"about \*\*(\$[0-9.]+) per day\*\*", summary).group(1)
F["daily_worst"] = re.search(r"Worst case.*?: (\$[0-9.]+) per day", summary).group(1)
F["daily_cap"] = f"{int(const('DAILY_TOKEN_CAP')):,}"
F["cw_baseline_total"] = re.search(r"reported (\d+) cache-write", summary).group(1)
exp_rows = {row[0]: row[1:] for row in md_table(experiment, "| Metric | Baseline | Cost-saver | Change |") if len(row) == 4}
exp_split = md_table(experiment, "| Config | Fresh input |")
sd_pass = len(re.findall(r"^\[PASS\]", safety_demo, re.M))
sd_fail = len(re.findall(r"^\[FAIL\]", safety_demo, re.M))
F["safety_demo"] = re.search(r"(\d+/\d+) cases passed", safety_demo).group(1)
guard_line = re.search(r"tokens per call \[(\d+), (\d+)\], average (\d+)", safety_demo)

diet_md = read("logs/diet_fix_check.md")
_m = re.search(r"wall time ([\d.]+) s.*?\n- Tokens: ([\d,]+) input \(([\d,]+) cached, ([\d,]+) cache-write\), ([\d,]+) output, (\d+) requests; cost \$([\d.]+)", diet_md, re.S)
DIET = {"sec": _m.group(1), "inp": _m.group(2), "cached": _m.group(3), "cw": _m.group(4), "out": _m.group(5), "req": _m.group(6), "cost": f"${float(_m.group(7)):.4f}"}
_u = re.search(r"(\d+) of (\d+) saved measurement results are unaffected", diet_md)
DIET["unaffected"], DIET["unaffected_of"] = _u.group(1), _u.group(2)
DIET["d08_clear"] = len(re.findall(r"\| d08 (?:baseline|cost_saver) \|.*?\| none \| none \|", diet_md))
NOSUB_NOTE = ('In the substitutions table, a row with status no_substitute shows (left out) in the Use instead column, followed by the model\'s closest idea; '
              'that idea is NOT a verified product at that store. Only rows with status substituted name a catalog product, with a price.')

base = [r for r in csv_rows if r["config"] == "baseline"]
saver = [r for r in csv_rows if r["config"] == "cost_saver"]
lat_all = [float(r["latency_s"]) for r in csv_rows]
F["lat_min"], F["lat_max"] = min(lat_all), max(lat_all)
F["runs"] = len(csv_rows)
F["cache_flagged"] = [r for r in csv_rows if r["possible_gateway_cache"] in ("True", "true", "1")]
all_tokens_in = sum(int(r["total_input"]) for r in csv_rows)
all_tokens_out = sum(int(r["total_output"]) for r in csv_rows)
F["experiment_tokens"] = all_tokens_in + all_tokens_out
F["experiment_cost"] = sum(run_cost(r) for r in csv_rows)
F["cw_all"] = sum(int(r["total_cache_write"]) for r in csv_rows)
F["tool_calls_base"] = statistics.mean(int(r["total_tool_calls"]) for r in base)
F["tool_calls_saver"] = statistics.mean(int(r["total_tool_calls"]) for r in saver)


def quality(rows: list[dict]) -> dict:
    proposed = sum(int(r["proposed_substitutes"] or 0) for r in rows)
    valid = sum(round(float(r["catalog_valid_rate"]) * int(r["proposed_substitutes"])) for r in rows if r["catalog_valid_rate"])
    return {"proposed": proposed, "valid": valid,
            "substituted": sum(int(r["substituted"] or 0) for r in rows), "none": sum(int(r["no_substitute"] or 0) for r in rows),
            "residual": sum(1 for r in rows if r["residual_conflict"] == "True"),
            "with_allergy": sum(1 for r in rows if r["residual_conflict"] in ("True", "False")),
            "expected_dishes": sum(1 for r in rows if r["expected_conflicts"]),
            "detected": sum(1 for r in rows if r["conflict_detected"] == "True"),
            "regenerated": sum(1 for r in rows if r["writer_path"] == "regenerated"),
            "fallback": sum(1 for r in rows if r["writer_path"] == "fallback")}


QB, QS = quality(base), quality(saver)
git_remote = run(["git", "remote", "get-url", "origin"])
pytest_out = run([sys.executable, "-m", "pytest", "-q"])
m_tests = re.search(r"(\d+) passed", pytest_out)
F["tests"] = m_tests.group(1) if m_tests else "not measured"
F["nutrition_rows"] = sum(1 for _ in csv.DictReader((ROOT / "data" / "nutrition.csv").open(encoding="utf-8")))
F["catalog_rows"] = sum(1 for _ in csv.DictReader((ROOT / "data" / "grocery_catalog.csv").open(encoding="utf-8")))
F["catalog_verified"] = sum(1 for r in csv.DictReader((ROOT / "data" / "grocery_catalog.csv").open(encoding="utf-8")) if r["verified"] == "true")

# ---- cross-check list from the earlier reports: the files win, and any difference is printed
CHECKS = [
    ("baseline avg cost", F["avg_cost"], "$0.002414"), ("avg input", F["avg_in"], "11,709"), ("avg cached", F["avg_cached"], "3,265"),
    ("avg output", F["avg_out"], "2,829"), ("avg latency", F["avg_lat"], "33.2"), ("analyst share", F["stages"]["analyst"][4], "59.0%"),
    ("substitution share", F["stages"]["substitution"][4], "21.4%"), ("writer share", F["stages"]["writer"][4], "14.3%"),
    ("intake share", F["stages"]["intake"][4], "3.1%"), ("guard share", F["stages"]["guard"][4], "2.2%"),
    ("cost-saver change", exp_rows["Cost per run"][2], "-16.9%"), ("nutrition match", exp_rows["Nutrition match rate (avg)"][0] + ">" + exp_rows["Nutrition match rate (avg)"][1], "91.7%>82.0%"),
    ("safety demo", F["safety_demo"], "19/19"), ("tests", F["tests"], "268"),
]
DISAGREE = [(n, got, want) for n, got, want in CHECKS if got != want]

# ================================================================ images

CROPS = {  # crop boxes remove browser chrome, bookmarks, the menu bar, the Dock and side panels
    "landing_page.png": (0, 86, 1917, 963),
    "blocked_injection.png": (300, 372, 1920, 945),
    "override_attempt_blocked.png": (300, 372, 1920, 945),
    "medical_advice_decline.png": (300, 372, 1920, 945),
    "extreme_restriction_decline.png": (300, 372, 1920, 965),
    "terminal_showing_safety_demo_at_1919.png": (222, 100, 1655, 905),
    "safety_checks.png": (0, 0, 1600, 410),
    "homebite_test_2.png": (240, 0, None, None), "homebite_test_3.png": (240, 0, None, None),
    "homebite_after_diet_2.png": (240, 0, None, None), "homebite_after_diet_3.png": (240, 0, None, None),
}
IMG_INFO: dict[str, tuple[int, int, int]] = {}
FIGS: list[str] = []


def img_uri(name: str) -> str:
    im = Image.open(SHOTS / name).convert("RGB")
    if name in CROPS:
        left, top, right, bottom = CROPS[name]
        im = im.crop((left, top, right or im.width, bottom or im.height))
    if im.width > MAX_WIDTH:
        im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    data = buf.getvalue()
    if len(data) > 450_000:  # large screenshots: JPEG keeps the file small and the text readable
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=86, optimize=True)
        data, mime = buf.getvalue(), "image/jpeg"
    else:
        mime = "image/png"
    IMG_INFO[name] = (im.width, im.height, len(data))
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def fig(key: str, caption: str, files: list[str] | str | None = None, svg: str | None = None, cls: str = "", sub: list[str] | None = None) -> str:
    """A numbered figure. files: one or more screenshots (a row), or svg: an inline SVG string."""
    FIGS.append(key)
    body = svg or ""
    if files:
        names = [files] if isinstance(files, str) else files
        imgs = "".join(f'<img src="{img_uri(n)}" alt="{esc(n)}">' for n in names)
        body = imgs if len(names) == 1 else f'<div class="row">{imgs}</div>'
    return f'<figure id="fig-{key}" class="{cls}">{body}<figcaption><b>Figure §{key}§.</b> {caption}</figcaption></figure>'


# ================================================================ SVG diagrams

def box(x, y, w, h, title, sub="", fill="#FFFFFF", stroke="#D6336C", dash=False, tcolor="#3A2330"):
    d = ' stroke-dasharray="5,3"' if dash else ""
    t = f'<text x="{x + w / 2}" y="{y + (h / 2 - 3 if sub else h / 2 + 4)}" text-anchor="middle" font-size="11.5" font-weight="700" fill="{tcolor}">{esc(title)}</text>'
    s = f'<text x="{x + w / 2}" y="{y + h / 2 + 11}" text-anchor="middle" font-size="9.5" fill="#6B4A5A">{esc(sub)}</text>' if sub else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{d}/>{t}{s}'


def arrow(x1, y1, x2, y2, color="#D6336C", dash=False, label="", lx=0, ly=0):
    d = ' stroke-dasharray="5,3"' if dash else ""
    lab = f'<text x="{lx}" y="{ly}" font-size="9.5" fill="{color}" font-style="italic">{esc(label)}</text>' if label else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.6"{d} marker-end="url(#ah)"/>{lab}'


def diagram() -> str:
    P, G, W = "#FFF0F5", "#EAF2FF", "#FFFFFF"
    parts = [
        '<svg viewBox="0 0 980 470" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" role="img" '
        'aria-label="Pipeline diagram">',
        '<defs><marker id="ah" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#D6336C"/></marker></defs>',
        # trusted settings
        box(20, 10, 300, 44, "Sidebar settings (trusted)", "store, allergies, diet, servings, goal", fill=G, stroke="#3B6FB6"),
        '<text x="335" y="29" font-size="9.5" fill="#3B6FB6" font-style="italic">settings go to the agents as trusted</text>',
        '<text x="335" y="42" font-size="9.5" fill="#3B6FB6" font-style="italic">configuration, never as part of the student text</text>',
        # row 1
        box(20, 90, 118, 52, "Student text", "untrusted, in delimiters", fill=W, stroke="#9A7B8A"),
        box(158, 90, 118, 52, "Input rules", "free code, no tokens"),
        box(296, 90, 118, 52, "Guard", "1 cheap classifier call", fill=P),
        box(434, 90, 118, 52, "Intake", "AI: Request or 1 question", fill=P),
        box(572, 90, 118, 52, "Analyst", "AI: ingredients + USDA ids", fill=P),
        box(740, 90, 220, 52, "Blocked or stopped", "friendly message, 0 further tokens", fill="#F3F3F3", stroke="#9A7B8A", dash=True),
        arrow(138, 116, 156, 116), arrow(276, 116, 294, 116), arrow(414, 116, 432, 116), arrow(552, 116, 570, 116),
        '<path d="M217,90 V76 H850 V88" fill="none" stroke="#9A7B8A" stroke-width="1.6" stroke-dasharray="5,3" marker-end="url(#ah)"/>',
        '<text x="430" y="72" font-size="9.5" fill="#6B4A5A" font-style="italic">a rule or the classifier blocks the request</text>',
        # row 2
        box(20, 230, 118, 52, "Substitution", "AI: picks from catalog", fill=P),
        box(158, 230, 118, 52, "Verifier", "pure code, no AI", fill="#E8F7EE", stroke="#2B8A57"),
        box(296, 230, 118, 52, "Writer", "AI: text only", fill=P),
        box(434, 230, 118, 52, "Output check", "code: numbers, products"),
        box(572, 230, 118, 52, "Results page", "tables and charts by code", fill=W),
        arrow(631, 142, 631, 190), arrow(631, 190, 79, 190), arrow(79, 190, 79, 228),
        arrow(138, 256, 156, 256), arrow(276, 256, 294, 256), arrow(414, 256, 432, 256), arrow(552, 256, 570, 256),
        # re-run loop
        '<path d="M217,230 C217,175 120,175 100,228" fill="none" stroke="#C92A2A" stroke-width="1.6" stroke-dasharray="5,3" marker-end="url(#ah)"/>',
        '<text x="126" y="171" font-size="9.5" fill="#C92A2A" font-style="italic">allergen or diet conflict: re-run once</text>',
        # fallback
        box(434, 330, 118, 44, "Template", "built from Verifier data", fill="#F3F3F3", stroke="#9A7B8A", dash=True),
        arrow(493, 282, 493, 328, color="#9A7B8A", dash=True),
        '<text x="500" y="312" font-size="9.5" fill="#6B4A5A" font-style="italic">fails twice</text>',
        # data
        box(590, 330, 170, 52, "nutrition.csv (USDA)", f"{F['nutrition_rows']:,} foods; Analyst, Verifier", fill=G, stroke="#3B6FB6"),
        box(780, 330, 180, 52, "grocery_catalog.csv", f"{F['catalog_rows']} items, 5 stores; Substitution, Verifier", fill=G, stroke="#3B6FB6"),
        # caps band
        '<rect x="20" y="410" width="940" height="44" rx="7" fill="#FFF0F5" stroke="#D6336C" stroke-width="1"/>',
        '<text x="490" y="429" text-anchor="middle" font-size="10.5" font-weight="700" fill="#3A2330">Limits on every run</text>',
        '<text x="490" y="445" text-anchor="middle" font-size="9.5" fill="#6B4A5A">request and tool-call caps per agent; token caps per run, session and day; hourly rate limit; every stage is logged</text>',
        '</svg>',
    ]
    return "".join(parts)


def bar_chart(items: list[tuple[str, float, str]], width=640, unit="") -> str:
    """Horizontal bars: (label, value, text). Value is scaled to the largest."""
    top = max(v for _, v, _ in items)
    rows = []
    for i, (label, value, text) in enumerate(items):
        y = 6 + i * 25
        w = max(2, (width - 230) * value / top)
        rows.append(f'<text x="0" y="{y + 14}" font-size="11" fill="#3A2330">{esc(label)}</text>'
                    f'<rect x="130" y="{y}" width="{w:.1f}" height="20" rx="3" fill="#D6336C" opacity="0.85"/>'
                    f'<text x="{136 + w:.1f}" y="{y + 15}" font-size="11" fill="#3A2330">{esc(text)}</text>')
    height = 6 + len(items) * 25
    return (f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
            f'role="img" aria-label="bar chart">{"".join(rows)}</svg>')


def grouped_chart(groups: list[tuple[str, float, float, str, str]], width=640, height=210) -> str:
    """Grouped vertical bars: (label, baseline, saver, baseline_text, saver_text)."""
    top = max(max(b, s) for _, b, s, _, _ in groups)
    gw = (width - 40) / len(groups)
    out = []
    for i, (label, b, s, bt, st) in enumerate(groups):
        x0 = 30 + i * gw
        hb, hs = 140 * b / top, 140 * s / top
        out.append(f'<rect x="{x0 + 10:.1f}" y="{160 - hb:.1f}" width="{gw / 2 - 14:.1f}" height="{hb:.1f}" fill="#D6336C"/>'
                   f'<rect x="{x0 + gw / 2 - 2:.1f}" y="{160 - hs:.1f}" width="{gw / 2 - 14:.1f}" height="{hs:.1f}" fill="#F3A6C0"/>'
                   f'<text x="{x0 + 10 + (gw / 2 - 14) / 2:.1f}" y="{154 - hb:.1f}" text-anchor="middle" font-size="10" fill="#3A2330">{esc(bt)}</text>'
                   f'<text x="{x0 + gw / 2 - 2 + (gw / 2 - 14) / 2:.1f}" y="{154 - hs:.1f}" text-anchor="middle" font-size="10" fill="#3A2330">{esc(st)}</text>'
                   f'<text x="{x0 + gw / 2:.1f}" y="180" text-anchor="middle" font-size="11" fill="#3A2330">{esc(label)}</text>')
    legend = ('<rect x="30" y="193" width="10" height="10" fill="#D6336C"/><text x="45" y="202" font-size="10" fill="#3A2330">Baseline</text>'
              '<rect x="110" y="193" width="10" height="10" fill="#F3A6C0"/><text x="125" y="202" font-size="10" fill="#3A2330">Cost-saver</text>')
    return (f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
            f'role="img" aria-label="grouped bar chart"><line x1="30" y1="160" x2="{width - 10}" y2="160" stroke="#C9B3BE"/>{"".join(out)}{legend}</svg>')


def trace_fig() -> str:
    FIGS.append("walk_trace")
    def im(n):
        return f'<img src="{img_uri(n)}" alt="{esc(n)}">'
    return ('<figure id="fig-walk_trace" class="trace w80"><div class="tcols">'
            f'<div>{im("trace_analyst.png")}</div>'
            f'<div>{im("trace_intake.png")}<div class="tsub"><div>{im("trace_substitution.png")}</div><div>{im("trace_verifier.png")}{im("trace_writer.png")}</div></div></div>'
            '</div><figcaption><b>Figure §walk_trace§.</b> Trace panels for the same run. Left: the Analyst and its nutrition searches. Right: Intake, then Substitution, '
            'the Verifier (code only) and the Writer. Each shows its input, its tool calls and its tokens.</figcaption></figure>')


# ================================================================ small HTML helpers

def table(header: list[str], rows: list[list[str]], cls: str = "", widths: list[str] | None = None) -> str:
    cols = "".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    head = "".join(f"<th>{h}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><colgroup>{cols}</colgroup><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def callout(inner: str, cls: str = "") -> str:
    return f'<div class="callout {cls}">{inner}</div>'


def usd(x: float, places: int = 4) -> str:
    return f"${x:.{places}f}"


def pct_change(row: str) -> str:
    return exp_rows[row][2]


# ================================================================ sections

SECTIONS: list[str] = []


def section(title: str, body: str) -> None:
    SECTIONS.append(f'<section><h2>{title}</h2>{body}</section>')


# ---- 1. Title ----------------------------------------------------------------------------------------------------
section("1. HomeBite", f"""
<p class="lead">Adapt a dish from home to the ingredients you can actually buy at your store, with nutrition computed in code from USDA data.</p>
<table class="meta"><tbody>
<tr><td><b>Author</b></td><td>Nicole Lin</td></tr>
<tr><td><b>Course</b></td><td>MGT 409, AI Foundations for Managers, Yale SOM, Fall 2026</td></tr>
<tr><td><b>Code</b></td><td><a href="{esc(git_remote)}">{esc(git_remote)}</a></td></tr>
<tr><td><b>App</b></td><td>Not hosted online. Runs locally from a fresh clone; setup measured at about 35 seconds in a fresh-clone test
(see README). The README itself estimates about 5 minutes for a first-time user, because that includes creating the <code>.env</code> file.</td></tr>
</tbody></table>
<p>HomeBite takes a dish that a student misses from home, for example Taiwanese beef noodle soup, together with the student's store and allergies.
It breaks the dish into ingredients, finds substitutes for the ones that are hard to buy, but only from a product catalog for that store, writes the
cooking steps, and compares the nutrition of the original and the adapted dish. Code, not the AI model, computes the nutrition numbers and checks allergens and vegetarian, vegan and pescatarian diets.
It is a prototype: the catalog is a starter set of {F['catalog_rows']} illustrative items, not real store data.</p>
<div class="split">
<div>{callout(f'''<b>At a glance</b>
<ul>
<li><b>Design:</b> five stages (Intake, Analyst, Substitution, Verifier, Writer) plus an input guard and output checks; the Verifier is pure code. Model: gpt-6-luna through Portkey.</li>
<li><b>Data:</b> {F['nutrition_rows']:,} USDA foods and {F['catalog_rows']} catalog items; {F['catalog_verified']} of the {F['catalog_rows']} catalog items have been verified against real store listings.</li>
<li><b>Cost and speed (20 live runs, 10 dishes x 2 configurations):</b> baseline average {F['avg_cost']} per run and {F['avg_lat']} seconds per run.</li>
<li><b>Checks:</b> {F['tests']} automated tests pass without spending tokens; the safety demo (which predates the diet check) passes {F['safety_demo']} cases.</li>
<li><b>Honest result:</b> a cheaper configuration cut cost by {pct_change('Cost per run').lstrip('-')} but lowered the nutrition match rate from {exp_rows['Nutrition match rate (avg)'][0]} to {exp_rows['Nutrition match rate (avg)'][1]}, so I did not adopt it.</li>
</ul>''')}</div>
<div>{fig('landing', 'The app on first load: settings in the sidebar, a text box, three example dishes and one button.', 'landing_page.png')}</div>
</div>
""")

# ---- 2. Motivation -----------------------------------------------------------------------------------------------
section("2. Motivation: who this is for", f"""
<h3>The problem</h3>
<p>U.S. institutions hosted 1,177,766 international students in 2024/25, about 6% of total U.S. higher-education enrollment (Open Doors 2025).
Many of them arrive in a food environment that is unfamiliar. A 2015 study with seven focus groups and 32 college-age international students at an
urban U.S. university found that students described many dietary challenges when adapting to American culture, shaped by the food environment,
the campus, religion and personal preferences. The authors also report dietary changes associated with undesirable health outcomes such as weight gain (Alakaam et al., 2015).</p>
<p>Where students shop matters. A master's thesis at East Carolina University (a survey of 142 international students in spring 2011, plus interviews) found that food choices were guided by whether native foods were available in local stores and by time in the U.S.; newcomers looked for familiar foods. Familiar food also carries meaning: in a small thesis study at one large public university (38 surveys, 11 interviews), 80% of the students who rated belonging differently for home-country foods versus overall reported more belonging with those foods. A small qualitative sample, so a hint, not a measurement.</p>
<p>Money matters too. A survey of 853 students aged 18 to 34 at one Midwest university (April 2022) found food insecurity among 26.8% of international students, against 19.9% of White students and 35.6% of U.S.-born multicultural students; international students also used nutrition assistance programs, including the campus food pantry, more. One university only, so this shows the problem exists, not how large it is.</p>
<h3>My own starting point</h3>
<p>I am an international student from Taiwan. I love cooking and I'm passionate about nutrition. I find it challenging to get used to the food here in the US, and I miss my mom's cooking
(or Taiwanese food in general) a lot. I designed this app because I think a lot of international students might share my experience and want to recreate some dishes from home.</p>
<h3>How students cope today, and what it costs</h3>
<p>The usual workarounds are a web search, asking a chatbot, asking family, or giving up on the dish. I timed one: searching Google for a vegetarian kimchi jjigae recipe took about
2 minutes (one dish, one attempt, self-timed). It produced a recipe only: I still had to look up the nutrition facts of alternative ingredients myself, and the time excludes shopping and cooking.
I did not measure what students spend in money or how often they give up, so I make no claim about either; the sources above support only that familiar food matters and that store availability shapes choices.</p>
{callout("<b>What HomeBite is not.</b> It is not medical advice. It does not fix food insecurity. It is not a substitute for real store data: its catalog is a "
         f"starter set of {F['catalog_rows']} illustrative items, and none of them has been checked against a real store listing.")}
""")

# ---- 3. What is new ----------------------------------------------------------------------------------------------
CAUTION = "as publicly described (2023 launch announcements; features may have changed by October 2026; not hands-on tested by me)"
section("3. What is new here, and what is not", f"""
<p>I compared HomeBite with three existing products as publicly described, and ran one hands-on test against a general chatbot. Product descriptions come from public announcements and web pages (listed under Sources), {CAUTION}.
The right-hand column says where the other tool is stronger.</p>
{table(['Tool', 'What it does well (as publicly described)', 'What HomeBite adds or does differently', 'Where it is stronger than HomeBite'], [
    ['<b>Samsung Food</b> (launched September 2023)', 'An AI-powered food and recipe platform. Personalize Recipe changes a saved recipe to fit dietary requirements; its Food AI can swap ingredients for what users have at home or for nutrition; recipes can become shopping lists; nutrition information is available.',
     'Starts from a specific dish from home and rebuilds it for one named store; every substitute must be a catalog product; a code check re-runs the substitution when an allergen or diet conflict appears.',
     'A full platform with saved recipes and shopping lists; HomeBite is a single-purpose prototype.'],
    ['<b>Ask Instacart</b> (2023)', 'An AI search tool built on OpenAI\'s ChatGPT plus Instacart\'s own models and catalog data (more than a billion shoppable items across more than 80,000 retail partner locations). It can suggest alternative ingredients (for example a fish similar to salmon) and generate ingredient lists for a meal.',
     'Focuses on verifying each suggestion: catalog-only products, USDA-based nutrition computed in code, and an allowed answer of leaving the ingredient out.',
     'Real catalogs at very large scale. HomeBite has 163 illustrative items.'],
    ['<b>Cronometer</b>', 'A nutrition tracker that draws on USDA and other national food composition databases (for example USDA SR28 and NCCDB).',
     'Uses one bundled USDA table (SR Legacy, 3,000 foods) inside a dish-adaptation flow, and compares the original and adapted versions.',
     'Broader databases and a full tracking product.'],
], widths=['15%', '33%', '30%', '22%'])}
<h3>Is this just another recipe or meal-planning app?</h3>
<p>It is adjacent to that crowded category, and the difference is narrow. First, it starts from one specific dish from home and rebuilds it for the student's own store; it does not plan meals.
Second, the model proposes and code disposes. Products can only come from the catalog. Nutrition is computed in code from USDA data, and ingredients without a USDA entry are listed as excluded.
Allergen conflicts, and conflicts with a vegetarian, vegan or pescatarian preference, are checked by code and trigger a re-run of the substitution step. "No substitute, leave it out" is an allowed answer, and it happens often (sections 7 and 8).
Third, safety and cost behavior is measured (20 live runs, and a safety demo that can be rerun). It is a prototype of a verification layer, not a finished product.</p>
<h3>A head-to-head test with a general chatbot</h3>
<p>This is one dish, one chatbot, one prompt and one run each. I gave ChatGPT (GPT-6) this request: “I'm an international student shopping at Walmart in the US. Adapt a vegetarian Korean kimchi jjigae using ingredients I can buy there, list the products to buy, and give calories and sodium per serving.”
The app displayed “Worked for 1m 15s”. I ran HomeBite on the same dish with Walmart, dietary preference vegetarian, goal lower sodium (the chatbot prompt did not mention a sodium goal), 2 servings and the text “Korean kimchi jjigae”.
I ran HomeBite twice more after fixing the problem this test exposed (below): once with the goal set to none, and once with the exact original settings (logged in logs/diet_fix_check.md).</p>
{table(['', 'ChatGPT (one run)', 'HomeBite at the time of the test', 'HomeBite after the diet fix'], [
    ['<b>Time and cost</b>', 'Displayed run time 1 m 15 s; cost not measured.',
     '33 s; estimated $0.0023 (9,342 input tokens, 2,159 cached, 2,988 output, 8 requests).',
     f'41 s, estimated $0.0032 (goal none). A second run with the original settings: {DIET["sec"]} s, {DIET["inp"]} input tokens ({DIET["cached"]} cached, {DIET["cw"]} cache-write), {DIET["out"]} output, {DIET["req"]} requests, about {DIET["cost"]}.'],
    ['<b>Vegetarian requirement</b>', 'Met: a vegetarian recipe (25 minutes, 2 servings, one pot) built around a vegan-labeled kimchi.',
     '<b>Not met.</b> The recipe included 120 g of pork belly and its first step browns it; the intro said the list included pork belly, so the version was not vegetarian.',
     'Pork belly no longer appears in the ingredient list or the steps. The diet check box is yellow: kimchi is kept, with a note that traditional kimchi often contains fish sauce or shrimp and the label should be checked.'],
    ['<b>Products</b>', 'Three named Walmart products with prices (a vegan kimchi $4.87, extra-firm tofu $2.92, a gochujang-style chili sauce $4.38) plus everyday groceries. It said the products were found on Walmart\'s website, that prices are approximate and that availability at my store is not confirmed. I did not verify them.',
     '0 substitutes found; 3 items left out (gochugaru, dried anchovy, kelp). Kimchi, tofu and the rest were kept as common items, not checked against the catalog.',
     '0 substitutes found; 5 items left out (pork belly, gochujang, Korean chili flakes, dried anchovy, kelp). The starter catalog has no vegan-labeled kimchi, so generic kimchi was kept with a check-the-label warning.'],
    ['<b>Nutrition and how it was derived</b>', 'A per-ingredient table summing to about 300 kcal and about 850 mg sodium per serving (about 430 kcal with 100 g of rice), described as approximate and based on published labels, with a reminder to check packages.',
     'USDA values computed in code. Per serving: original 520.53 kcal and 539.09 mg sodium; adapted 517.48 kcal and 534.68 mg. Totals exclude gochugaru (no USDA entry).',
     'USDA values computed in code. Per serving: original 530.42 kcal and 757.35 mg; adapted 131.2 kcal and 727.3 mg; fat falls from 48.1 g to 7.9 g and protein from 17.3 g to 9.4 g. Totals exclude gochujang.'],
    ['<b>Extras</b>', 'Photos of the dish; an interactive slider for kimchi and rice amounts; a remark that the kimchi is the largest sodium source.',
     'Allergen box, trace of every stage, usage panel. No photos, no slider.', 'The same, plus a Diet check box.'],
], widths=['12%', '29%', '29%', '30%'])}
<p>The two nutrition sets are not comparable, because the recipes differ (pork belly or none, and different kimchi products and amounts). I did not check ChatGPT's numbers or products.</p>
{fig('chatgpt', 'The ChatGPT answer: the request and the top of the answer (with the displayed 1 m 15 s), the Walmart shopping list, the cooking steps, the nutrition table (about 300 kcal and about 850 mg per serving) and the interactive slider.',
     ['chatgpt_test_1.png', 'chatgpt_test_2.png', 'chatgpt_test_3.png', 'chatgpt_test_4.png', 'chatgpt_test_5.png'], cls='')}
{fig('hb_pair', 'HomeBite on the same dish. Left column: at the time of the test (the pork belly, its first step and the intro note; the substitutions table; the nutrition chart and usage). Right column: after the diet fix (no pork belly in the list or steps; five items left out; the yellow Diet check box; nutrition after pork belly was removed). ' + NOSUB_NOTE,
     ['homebite_test_1.png', 'homebite_after_diet_1.png', 'homebite_test_2.png', 'homebite_after_diet_2.png', 'homebite_test_3.png', 'homebite_after_diet_3.png'], cls='g2 splittable')}
<p><b>What the test shows.</b> ChatGPT's answer met the vegetarian requirement, named real-looking Walmart products with prices, and included photos and an interactive estimate. Its displayed run time was 1 m 15 s against HomeBite's 33 s; the two did different work (the chatbot also made photos and looked up products), so I do not read the times as an advantage either way.
HomeBite's answer at the time of the test was not vegetarian. Two of Alex's three suggestions, pictures and conversation, are things ChatGPT did in this test. ChatGPT also named a specific vegan-labeled kimchi product, while HomeBite kept generic kimchi with a check-the-label warning because its catalog has no such product.</p>
<p><b>What HomeBite's checks add in principle, and where this test did and did not show them.</b> Catalog-only products: not shown as a benefit here. No product was named at all, because the 163-item starter catalog had nothing suitable, so in this test the restriction cost usefulness.
USDA values computed in code with excluded items listed: shown (the chart lists gochugaru, and later gochujang, as excluded), but because the recipes differ I cannot say whose numbers are closer to the truth.
Allergen and diet checks with a re-run: the allergen check was not exercised (no allergies selected). The diet check did not exist at the time of the test; after the fix it flagged pork belly on the first pass and removed it through the re-run (section 6).</p>
""")

# ---- 4. Agents ---------------------------------------------------------------------------------------------------
section("4. The agents", f"""
<p>HomeBite is a pipeline of small steps. Three are AI agents with a narrow job, one is plain code, and two more checks (an input guard and an output check) sit around them.
Each AI agent returns a structured result; the Writer's fields are free text, and they are checked before they are shown.</p>
{table(['Stage', 'Job', 'Tools', 'Hands to the next stage'], [
    ['<b>Input guard</b>', 'Free rules first (instruction overrides, requests for the prompt or keys, attempts to change store or allergies through the text), then one cheap classifier call. If the classifier cannot run, the request stops.', 'Rules in code; one AI call', 'Pass, or a friendly message with no further tokens'],
    ['<b>Intake</b>', 'Turns the text and sidebar settings into a request (dish, cuisine, servings, goals), or asks one clarifying question.', 'None', 'A structured request'],
    ['<b>Analyst</b>', 'Breaks the dish into ingredients with weights, flags those hard to find in a U.S. supermarket, and finds USDA entries.', 'USDA search', 'Ingredient list with USDA ids'],
    ['<b>Substitution</b>', 'For each hard-to-find ingredient, picks a product that really comes back from a search of the student\'s store, or says there is none.', 'Catalog search (store and allergies fixed by code), USDA search', 'A substitution plan'],
    ['<b>Verifier</b> (pure code)', 'Checks each substitute exists in the catalog, computes nutrition for both versions, runs the allergen check and, for a vegetarian, vegan or pescatarian preference, the diet check, and lists unmatched ingredients. Re-runs Substitution once if there is a definite allergen or diet conflict.', 'Catalog lookup, nutrition math, allergen check', 'Verified ingredients, nutrition comparison, allergen result'],
    ['<b>Writer</b>', 'Writes the intro, the cooking steps and a note on what will taste different. It never sees nutrition numbers.', 'None', 'Text'],
    ['<b>Output check</b> (code)', 'Rejects leaked prompts, key-like strings, invented numbers, nutrition claims and product names that were not confirmed. Retries once, then uses a plain template.', 'Rules in code', 'The text shown, or the template'],
], widths=['15%', '45%', '20%', '20%'])}
{fig('diagram', 'How a request moves through the system. Blue boxes are trusted inputs and data files; pink boxes are AI calls; the green box is pure code. Dashed arrows are exits and data lookups.', svg=diagram())}
<h3>Which model, and why</h3>
<p>All AI calls use gpt-6-luna through Portkey with the course key. I chose the low-cost tier: $0.10 per million input tokens, $0.01 per million cached input tokens and $0.50 per million output tokens (course pricing slide), with cache writes at $0.125.
The code calls the model through the Responses API, because the chat completions endpoint rejected function tools for this model (a comment in <code>llm.py</code> records this).</p>
<h3>Why five stages instead of one prompt</h3>
<p>Separation of duties. The model is good at reading a dish and proposing ingredients, and bad at being trusted with numbers, so numbers and checks are code. Each stage also gets its own small prompt and its own limits.
I did not build or test a single-prompt version, so I cannot report how it would compare in cost or quality.</p>
<h3>One real run, step by step</h3>
<p>This is a live run of Kung pao chicken with Walmart selected and a peanut allergy. Settings go in the sidebar; the text box holds only the dish name.</p>
{fig('walk_top', 'The result page for the run: a summary strip (substitutes found, items left out, allergen status, run time, estimated cost), the ingredient list with left-out items struck through, the steps and the taste note.', 'result_1_top.png', cls='w86')}
<p>Behind the page is a trace of every stage. The panels below are from the same run. The Intake panel shows the trusted settings and the student text in separate delimited blocks. The Analyst ran 21 nutrition searches (counted from the panel) in 3 requests.
The Substitution agent searched the catalog five times and found a product for two of them. The Verifier, which is code, confirmed both products exist in the Walmart catalog, computed nutrition twice (original and adapted)
and found one allergen conflict, which sent the run back to Substitution once.</p>
{trace_fig()}
<p>Cross-check against the usage panel. The panels for Intake (311 in, 79 out), Analyst (8,116 in of which 2,855 cached, 1,769 out), Substitution (1,905 in, 711 out) and Writer (853 in, 422 out) add up to
11,185 input and 2,981 output tokens. The usage panel reports 13,661 input, 2,855 cached and 3,879 output tokens over 10 requests, so 2,476 input and 898 output tokens are not in the panels shown.
That remainder is consistent with the guard call and the substitution re-run, whose panels are not in these screenshots. The cached tokens match exactly because only the Analyst had cache hits.</p>
{fig('walk_usage', 'The usage panel for the run: 13,661 input, 2,855 cached and 3,879 output tokens, 10 requests.', 'usage_panel.png', cls='w60')}
<h3>Design choices that are actually in the code</h3>
<ul>
<li><b>Trusted settings.</b> Store, allergies, diet, servings and goal come from the sidebar and travel as configuration. The student's text is wrapped in delimiters and treated as data.</li>
<li><b>The Analyst is not told the student's allergies.</b> It describes the traditional dish, so a conflicting ingredient reaches the code check instead of being silently dropped by the model.</li>
<li><b>Tool wrappers fix the store and allergies.</b> The catalog search takes the store and allergy list from the run settings, not from the model's arguments, so text like a request to search another store cannot change them (tested).</li>
</ul>
""")

# ---- 5. Tokenomics -----------------------------------------------------------------------------------------------
st = F["stages"]
stage_names = ["guard", "intake", "analyst", "substitution", "writer"]
section("5. Tokenomics", f"""
<p>All numbers in this section come from {F['runs']} live runs: 10 dishes, each run once with the baseline configuration and once with a cost-saver configuration (section below).
Costs are computed from token counts with the course prices; the guard stage is included in every total. Latency is wall-clock time.
{('No run was flagged as a possible gateway cache hit.' if not F['cache_flagged'] else 'Runs flagged as possible gateway cache hits: ' + ', '.join(r['dish_id'] + '/' + r['config'] for r in F['cache_flagged']) + '.')}</p>
<h3>Baseline cost per run</h3>
{table(['Per run (10 dishes)', 'Average', 'p90'], [
    ['Input tokens', F['avg_in'], F['p90_in']], ['Cached input tokens', F['avg_cached'], F['p90_cached']], ['Output tokens', F['avg_out'], F['p90_out']],
    ['Cost', F['avg_cost'], F['p90_cost']], ['Latency (seconds)', F['avg_lat'], F['p90_lat']],
], widths=['50%', '25%', '25%'])}
<p>Cached input is {F['cache_ratio']} of input. The slowest run took {F['lat_max']:.1f} seconds and the fastest {F['lat_min']:.1f} seconds across all {F['runs']} runs. The provider reported cache-write tokens
({int(F['cw_all']):,} across all {F['runs']} runs), and they are priced at the cache-write rate.</p>
<h3>Where the cost goes</h3>
{fig('cost_stage', 'Average cost per run by stage, baseline configuration. The Analyst, which looks up every ingredient, is more than half of the cost. Source: the stage table in logs/token_summary.md.',
     svg=bar_chart([(s.capitalize(), num(st[s][4]), f"{st[s][4]}  ({st[s][3]})") for s in stage_names]))}
{table(['Stage', 'Input', 'Cached', 'Output', 'Cost per run', 'Share', 'Requests', 'Tool calls'],
       [[s.capitalize()] + st[s][:3] + st[s][3:] for s in stage_names], widths=['16%', '11%', '11%', '11%', '15%', '10%', '13%', '13%'])}
<p>The guard stage costs {st['guard'][3]} per request on average ({st['guard'][0]} input and {st['guard'][2]} output tokens), {st['guard'][4]} of the total; two real classifier calls in the safety demo used {guard_line.group(1)} and {guard_line.group(2)} tokens.
Output is priced at five times normal input and is {exp_split[0][5]} of baseline cost.</p>
<h3>Cost per user and at scale</h3>
<p>The monthly figures use <b>12 runs per user per month, which is my assumption</b>, not something I measured. They include the guard cost.</p>
{table(['Users', 'Runs per month', 'Estimated monthly cost'], [[u, F['proj'][u][1], F['proj'][u][2]] for u in F['proj']], widths=['30%', '35%', '35%'])}
<p>They exclude hosting, storage and bandwidth, and they do not model provider rate limits at 100 or 10,000 users. They are estimates from tokens and the course price slide, not an invoice.
The per-day token cap of {F['daily_cap']} tokens (input plus output) implies at most about {F['daily_obs']} per day at the measured token mix, or {F['daily_worst']} per day in the worst case where every capped token is an output token.
The whole 20-run measurement used {F['experiment_tokens']:,} input plus output tokens, about {usd(F['experiment_cost'], 3)}.</p>
<h3>Can the cost be cut?</h3>
<p>I tested three levers, switchable by a settings object and off by default: put each agent's static instructions first and the dynamic text last (so provider prompt caching could apply),
trim the Analyst and Writer prompts while keeping every safety rule, and add a batched nutrition lookup so the Analyst searches all ingredients in one call. The cost-saver configuration turns on all three together.
Each dish was run once per configuration, alternating which went first.</p>
{table(['Metric', 'Baseline', 'Cost-saver', 'Change'], [[k] + exp_rows[k] for k in
    ['Input tokens', 'Cached input tokens', 'Output tokens', 'Cost per run', 'Tool calls', 'Latency (s)', 'Nutrition match rate (avg)', 'Writer fallback rate', 'Catalog valid rate (proposed substitutes found in catalog)',
     'Allergen detection rate (conflict_detected / expected, 5 dishes)', 'Residual allergen conflicts (count)']], widths=['46%', '18%', '18%', '18%'])}
<p>Cost split per run: baseline {exp_split[0][1]} fresh input, {exp_split[0][2]} cached input, {exp_split[0][3]} output; cost-saver {exp_split[1][1]}, {exp_split[1][2]} and {exp_split[1][3]}.
Tool calls fell by {pct_change('Tool calls').lstrip('-')} and cost fell by {pct_change('Cost per run').lstrip('-')}; the cost-saver was cheaper on 9 of 10 dishes.
The combined cost-saver did not raise caching: cached input fell by {pct_change('Cached input tokens').lstrip('-')}, so the savings came from fewer tokens, not from more cache hits. Because the three levers were tested together, I cannot say whether prompt order alone had any effect.</p>
{callout(f"<b>The cost-saver was not adopted.</b> It cut cost, but the nutrition match rate fell from {exp_rows['Nutrition match rate (avg)'][0]} to {exp_rows['Nutrition match rate (avg)'][1]}, "
         "and it was lower on 7 of 10 dishes (equal on 3, higher on none), so this is unlikely to be noise alone. A lower match rate means more ingredients are left out of the nutrition totals. "
         "I tested the three levers together, so I cannot say which one caused the drop. With one run per dish, the sample is small. The app still runs the baseline configuration.")}
""")

# ---- 6. Safety ---------------------------------------------------------------------------------------------------
section("6. Safety", f"""
<p>The table lists each risk, the defense I built, and the evidence. Evidence is either an automated test, the safety demo (a script that exercises each defense), or a screenshot in this report.</p>
{table(['Risk', 'Defense built', 'Evidence'], [
    ['Prompt injection, requests for the system prompt or keys', 'Free input rules run first; student text is wrapped in delimiters and treated as data; a canary marker in every prompt detects leaks.', 'Safety demo; Figure §safety_grid§ (blocked at 0 tokens); tests.'],
    ['Changing the store or allergies through the text box', 'Those settings come only from the sidebar. Rules catch attempts; the catalog search takes store and allergies from the run settings, not from the model.', 'Test that such text cannot change them; Figure §safety_grid§.'],
    ['Medical-advice and extreme-restriction requests', 'A classifier call screens the text. Medical requests are declined with a pointer to a doctor or dietitian. Extreme-restriction requests are declined gently with no numbers or tips and a pointer to a helpline organisation by name only.', 'Safety demo; Figure §safety_grid2§.'],
    ['Invented numbers or products', 'Verifier catalog check; output check rejects numbers not in the verified data, nutrition claims and unconfirmed product names; one retry, then a plain template built from verified data.', 'Safety demo (fake writer cases); tests.'],
    ['Loops and overspending', f'Per-agent request and tool-call caps (for example the Analyst: {int(const("ANALYST_REQUEST_LIMIT"))} requests, {int(const("ANALYST_TOOL_CALL_LIMIT"))} tool calls); token caps of {int(const("RUN_TOKEN_CAP")):,} per run, {int(const("SESSION_TOKEN_CAP")):,} per session and {int(const("DAILY_TOKEN_CAP")):,} per day (read from the usage log); {int(const("RATE_LIMIT_RUNS"))} runs per hour per session.', 'Safety demo (forced tool loop, session cap, rate limit); tests.'],
    ['A dietary preference that only reaches the AI as text', 'Vegetarian, vegan and pescatarian are checked by code with a keyword list; a definite conflict triggers one substitution re-run, and a conflict that remains is shown as not that diet. Other preferences (halal, kosher) are passed to the AI and not verified.', 'Found by the head-to-head test (Figure §hb_pair§), fixed, and re-checked live on one dish and offline on saved results (logs/diet_fix_check.md); tests.'],
    ['Allergen conflicts', 'Code checks the adapted ingredient list. A definite conflict triggers one re-run of Substitution; if a conflict remains, the recipe is shown only as not safe. Items marked uncertain always carry a check-the-label warning.', 'Live peanut run (Figure §peanut§); offline test of the not-safe screen; Figure §safetychecks§.'],
], widths=['22%', '50%', '28%'])}
<h3>Defenses working</h3>
{fig('safety_grid', 'Two requests stopped before any recipe was made, both at 0 tokens (see the usage tables). Left: an injection hidden in a dish description is blocked by the free input rules. Right: an attempt to ignore the peanut allergy is blocked by the same rules. (Screenshots cropped to the app window; their cost column still used placeholder prices, so I rely only on the token counts.)',
     ['blocked_injection.png', 'override_attempt_blocked.png'], cls='')}
{fig('safety_grid2', 'Two requests declined by the classifier. Left: a medical-advice request is declined and the student is pointed to a doctor or dietitian. Right: an extreme-restriction request is declined gently, with no numbers or tips and a pointer to a helpline organisation by name.',
     ['medical_advice_decline.png', 'extreme_restriction_decline.png'], cls='')}
<p>The classifier calls for the two declined requests used 342 input and 41 output tokens (medical) and 341 input and 67 output tokens (extreme restriction), one request each, as the usage tables show.
The safety demo ({F['safety_demo']} cases) covers the injection, key-leak, prompt-leak, store and allergy overrides, oversized input, forced tool loop, tool-call flood, session cap, rate limit, an invented number and product, and the kung pao peanut case. The demo predates the diet check, so it does not cover it.</p>

<h3>Two live allergen runs</h3>
<p><b>Peanut allergy, Kung pao chicken, Walmart.</b> The first check flagged peanuts as a definite conflict and the substitution step was re-run once. Peanuts were left out of the recipe and struck through on the page; three other ingredients with no store match (dried red chilies, Chinese black vinegar and Shaoxing wine) were left out too, so four items were left out in total.
The page shows a yellow warning, not a green box, because soy sauce, cornstarch and vegetable oil could not be confirmed peanut-free from the catalog or keyword list.</p>
<p><b>Fish allergy, Vietnamese chicken pho, Aldi</b> (a fresh-clone check; the figures come from my Prompt 9 report, not from the repo logs): 44 seconds, 16,373 input tokens (4,328 cached, 5,406 cache-write), 3,794 output tokens,
11 requests, about $0.0033. The first pass flagged fish sauce and the substitution re-run removed it.</p>
{fig('peanut', 'The live peanut run. Highlighted: left-out ingredients (peanuts struck through) and the yellow check-the-label warning. ' + NOSUB_NOTE, 'safety_peanuts_removed.png', cls='w52')}
<div class="two">
{fig('demo', 'The safety demo output file, ending with the pass count.', 'terminal_showing_safety_demo_at_1919.png')}
{fig('safetychecks', 'The safety checks list from the trace for the peanut run: the allergen conflict, the re-run and the output check.', 'safety_checks.png')}
</div>
<h3>A problem the measurement found, and the fix</h3>
<p>In the 20-run measurement, a gluten-allergy dish (Japanese chicken katsu curry) kept panko in the final recipe in both configurations, because the allergen keyword list had no entry for panko; it was only marked uncertain.
I extended the keyword list (whole-word matching, so nutmeg and eggplant are not flagged). A before-and-after check on all saved results (logs/allergen_fix_check.md) shows only that dish changed: 2 of 14 saved results with an allergy (the two katsu curry runs). A new live run of the dish flagged panko, flour and soy sauce, re-ran the substitution step, and removed all three, so panko is no longer in the final recipe.
A later check of noodle types (Prompt 8, with tests) found that rice vermicelli had been treated as safe for gluten rather than uncertain. That is fixed: rice, glass and sweet-potato noodles are now uncertain; wheat noodles, ramen, udon and soba stay definite conflicts.</p>
<h3>A second problem, found by the chatbot comparison</h3>
<p>In the head-to-head test (section 3), HomeBite's own answer with a vegetarian preference kept 120 g of pork belly and its first step browned it; only the intro admitted the version was not vegetarian.
The cause was that the dietary preference reached the AI only as text, and nothing in code checked it, while allergies were checked by code. I fixed it in the same style as the allergen path: vegetarian, vegan and pescatarian are now checked by code with a keyword list,
a definite conflict triggers one substitution re-run, and a conflict that remains is shown as not that diet. The cooking steps are also checked so they cannot use an ingredient that was left out.
Re-checked: a live run with the original settings flagged pork belly on the first pass and removed it through the re-run, and pork belly is absent from the ingredient list and the steps (logs/diet_fix_check.md); the page now shows a yellow Diet check box for kimchi.
Offline, the new check flagged nothing on the {DIET['d08_clear']} saved vegetarian ratatouille runs, and {DIET['unaffected']} of {DIET['unaffected_of']} saved results without a diet preference are unaffected.
It does not cover other preferences (halal and kosher are still only passed to the AI), and items such as kimchi stay uncertain: the page asks the student to check the label.</p>
<h3>What is not proven</h3>
<ul>
<li>The role-play jailbreak case in the demo was stopped by the AI provider's own content filter before my classifier answered, so it does not show my classifier working.</li>
<li>The red not-safe screens for a remaining allergen or diet conflict were tested offline with a fake model only. In the live runs, the re-run always removed the conflict.</li>
<li>The diet check was verified live on one dish and offline on the saved results; it is a keyword list, not a guarantee, and the safety demo predates it.</li>
<li>The allergen check uses catalog tags and a keyword list. It is not a guarantee. Ingredients such as Worcestershire sauce stay uncertain, and the page asks the student to check the label.</li>
<li>Allergen behavior was observed on 7 dishes in the measurement (14 runs) plus the demo and the live runs shown here, never with a real catalog.</li>
</ul>
""")

# ---- 7. Impact ---------------------------------------------------------------------------------------------------
section("7. Impact", f"""
<p>Measured results are marked as measured; everything else is potential.</p>
<h3>(a) One real user test</h3>
<p>A friend, Alex, tried HomeBite in person on my laptop and agreed to be named by first name. He entered his mom's potato beef stew with Whole Foods selected, no allergies, the lower-sodium goal and 2 servings.
The run took 18 seconds, used 5,458 input tokens (0 cached) and 1,776 output tokens over 5 requests, and cost an estimated $0.0015. No substitutions were needed (0 substitutes, 0 items left out).
This was a single tester and a dish with no substitutions, so it tested usability, not the substitution engine.</p>
<p>He thought it was a cool concept, found the instructions easy to follow and the ingredient list clear. In his words: “This is fun to use and I look forward to recreating my mom's dishes using this!”
His three ideas: allow multiple selections for allergens, dietary preferences and goals (for example low sodium and low calorie together; the allergy box already allows several choices, so he may not have noticed);
show pictures of the dishes; and turn the input into a chatbot that talks with you about the dish. Two of those, pictures and conversation, are things ChatGPT did in the head-to-head test in section 3.</p>
{fig('friend1', 'Alex\'s run. Left: the summary strip, ingredients and steps for his potato beef stew (18 s, $0.0015). Right: the usage panel (5,458 input, 0 cached, 1,776 output tokens, 5 requests).', ['friend_test_1.png', 'friend_test_3.png'], cls='w70')}
<h3>(b) Time</h3>
<p>My manual web search for one vegetarian kimchi jjigae recipe took about 2 minutes and gave a recipe only. HomeBite's measured run times were {F['lat_min']:.1f} to {F['lat_max']:.1f} seconds across the {F['runs']} runs, averaging {F['avg_lat']} seconds for the baseline,
and it returns an adapted ingredient list, steps, substitutes and a nutrition comparison. These are not like-for-like: one self-timed search for one dish against 20 runs of an app, and the search time excludes looking up nutrition.</p>
<h3>(c) Cost</h3>
<p>Measured: {F['avg_cost']} per run on average ({F['p90_cost']} at p90). Projected at 12 runs per user per month (my assumption): {F['proj']['1'][2]} per user per month.</p>
<h3>(d) Quality measures from the {F['runs']} runs</h3>
{table(['Measure', 'Baseline (10 runs)', 'Cost-saver (10 runs)', 'Note'], [
    ['Proposed substitutes found in the store catalog', f"{QB['valid']} of {QB['proposed']}", f"{QS['valid']} of {QS['proposed']}", 'The Verifier would also downgrade an invalid one.'],
    ['Substituted / left out (total over 10 dishes)', f"{QB['substituted']} / {QB['none']}", f"{QS['substituted']} / {QS['none']}", 'Many left-out ingredients: the catalog is small.'],
    ['Allergen conflict detected by the first check, for dishes where one was expected', f"{QB['detected']} of {QB['expected_dishes']} dishes", f"{QS['detected']} of {QS['expected_dishes']} dishes", 'Caveat: I chose the expected words myself, and this was measured before the panko keyword fix.'],
    ['Residual allergen conflicts in the final recipe', f"{QB['residual']} of {QB['with_allergy']} runs with an allergy", f"{QS['residual']} of {QS['with_allergy']}", 'By the code check. The panko case was only marked uncertain at the time.'],
    ['Nutrition match rate (average)', exp_rows['Nutrition match rate (avg)'][0], exp_rows['Nutrition match rate (avg)'][1], 'Share of ingredients with a verified USDA entry.'],
    ['Writer needed a retry / fell back to the template', f"{QB['regenerated']} / {QB['fallback']}", f"{QS['regenerated']} / {QS['fallback']}", ''],
], widths=['36%', '19%', '19%', '26%'])}
<h3>(e) Reach</h3>
<p>For context only, not a forecast: 1,177,766 international students were enrolled at U.S. institutions in 2024/25. I have no data on how many would use an app like this.</p>
{callout('<b>Measured:</b> token use, cost and latency of 20 runs; safety demo results; one user test. <b>Potential, not measured:</b> time saved for students, savings in money, adoption, and any health benefit.')}
""")

# ---- 8. Limits and next steps -------------------------------------------------------------------------------------
section("8. Limits and next steps", f"""
<h3>What does not work yet</h3>
{fig('nutr_limit', 'A live kung pao run: calories fall by 82.66 and sodium rises by 161.59 mg. The totals exclude the ingredients listed at the bottom (no USDA entry), so the change reflects what could be matched, not a healthier recipe.', 'result_3_nutrition.png', cls='w52')}
<ul>
<li>The catalog is a starter set of {F['catalog_rows']} illustrative items, none verified against real listings. Over the 10 baseline runs, {QB['substituted']} ingredients got a substitute and {QB['none']} were left out.</li>
<li>Some ingredients have no USDA entry and are excluded from the nutrition totals; the page says which.</li>
<li>The Goal selector (for example lower sodium) is passed to the AI as context but is not enforced or verified by code, and the results page does not say whether the goal was met. Allergies, the store and the vegetarian, vegan and pescatarian preferences are enforced by code; goals and other preferences (halal, kosher) are not.</li>
<li>Nutrition differences between the original and the adapted dish mostly reflect ingredients that were left out or have no USDA entry, not a healthier recipe. Figure §nutr_limit§ shows this: sodium rises, which is consistent with the original dish's dark soy sauce having no USDA entry (so it is excluded) while its substitute does.</li>
<li>Allergies accept several selections; dietary preference and goal accept one choice each.</li>
<li>When a check removes the main protein, HomeBite does not rebalance the dish: in the diet-fix example calories fell from 530.42 to 131.2 per serving, because the pork belly was removed and nothing replaced it, so the adapted dish is a very light stew, not a healthier recipe.</li>
<li>The diet check was verified live on one dish and offline on the saved results, and the keyword list is not a guarantee.</li>
<li>The starter catalog has no vegan-labeled kimchi, so HomeBite keeps generic kimchi with a check-the-label warning, where ChatGPT named a specific vegan-labeled product.</li>
<li>There are no dish pictures and no chat. The combined cost-saver did not raise caching. Most of the roughly 33 seconds is model generation, and I did not break latency down by stage.</li>
<li>Allergen checks are not a guarantee, and this is not medical advice. The Windows setup steps in the README are untested. Only one person tested the app.</li>
</ul>
<h3>If I had another month</h3>
<ul>
<li>Use real, licensed store data and verify it, replacing the starter catalog.</li>
<li>Have the Verifier compute whether a goal was met and show it on the page, and rebalance a dish when a check removes its main protein.</li>
<li>Allow several goals and diets at once.</li>
<li>Add conversational follow-ups, which would raise both cost and the safety surface.</li>
<li>Add dish images, after checking licensing.</li>
<li>Run a wider user study, with people who need substitutions.</li>
<li>Test the batched-lookup lever on its own, to find which lever lowered the nutrition match rate.</li>
<li>Add gluten-free and other allergen-safe items to the catalog, so the re-run has safe options to choose from.</li>
</ul>
""")

# ---- Appendix -----------------------------------------------------------------------------------------------------
APPENDIX = f"""
<section class="appendix"><h2>Appendix: where the numbers come from</h2>
{table(['Metric', 'Source'], [
    ['Per-run tokens, cost, latency, cache ratio, stage breakdown, projections, daily-cap spend; cost-saver comparison and quality columns; latency range, cache-hit flags, tool calls, cache-write tokens, experiment totals, substitute and allergen counts', 'logs/token_summary.md, logs/cost_experiment.md and logs/token_report.csv (columns summed by submission/build_report.py; costs recomputed with usage.py prices)'],
    ['Safety demo pass count and guard tokens; allergen keyword fix, 2 of 14 results changed; diet check second run and offline false-alarm check', 'logs/safety_demo_output.txt; logs/allergen_fix_check.md; logs/diet_fix_check.md'],
    ['Limits and caps; prices per million tokens and cache-write rate', 'safety.py; usage.py (source: course slides, Cached Token Cost slide, gpt-6-luna row)'],
    [f"{F['tests']} automated tests; {F['nutrition_rows']:,} USDA foods; {F['catalog_rows']} catalog items, {F['catalog_verified']} verified; known limits; repository URL", 'python -m pytest -q, run when this report was built (no tokens spent); data/*.csv; README.md; git remote get-url origin'],
    ['Alex\'s test (18 s, 5,458 / 0 / 1,776 tokens, 5 requests, $0.0015); manual search about 2 minutes; 12 runs per user per month; Vietnamese chicken pho run and about 35 seconds from clone to a running page', 'My inputs and assumption; the pho run and the 35 seconds are from the Prompt 9 fresh-clone report (not in the repo logs); Alex\'s numbers cross-checked against his usage screenshot'],
    ['Kung pao run totals (13,661 / 2,855 / 3,879, 10 requests); ChatGPT test (1 m 15 s, prices, about 300 kcal and 850 mg); HomeBite test and after-fix runs (33 s, 41 s, nutrition values)', 'Usage screenshot and trace panels (section 4); my inputs and the chatgpt_test and homebite screenshots (section 3)'],
], widths=['55%', '45%'])}
<h2>Sources</h2>
<ol class="sources">
<li>Institute of International Education, <i>Open Doors 2025 press release</i>. <a href="https://www.iie.org/news/open-doors-2025-press-release/">https://www.iie.org/news/open-doors-2025-press-release/</a></li>
<li>Alakaam, Castellanos, Bodzio and Harrison (2015), <i>Journal of International Students</i> 5(2): 104-120. <a href="https://doi.org/10.32674/jis.v5i2.428">https://doi.org/10.32674/jis.v5i2.428</a></li>
<li>Noyongoyo, East Carolina University master's thesis (survey of 142 international students, spring 2011, plus interviews). <a href="https://thescholarship.ecu.edu/handle/10342/3755">https://thescholarship.ecu.edu/handle/10342/3755</a></li>
<li>Thesis, <i>Identity in the ecosystem: a study of international students, belonging, and culturally relevant foods</i>. <a href="https://open.bu.edu/items/92757102-c12a-4b58-ae13-5a820690536a">https://open.bu.edu/items/92757102-c12a-4b58-ae13-5a820690536a</a></li>
<li><i>Nutrients</i> 2025, 17(2):237, food insecurity among 853 students at one Midwest university. <a href="https://doi.org/10.3390/nu17020237">https://doi.org/10.3390/nu17020237</a></li>
<li>Samsung Food launch announcement. <a href="https://news.samsung.com/ca/samsung-announces-global-launch-of-samsung-food-an-ai-powered-personalized-food-and-recipe-service">https://news.samsung.com/ca/samsung-announces-global-launch-of-samsung-food-an-ai-powered-personalized-food-and-recipe-service</a> and Android Central, <a href="https://www.androidcentral.com/apps-software/samsung-food-app-launch">https://www.androidcentral.com/apps-software/samsung-food-app-launch</a></li>
<li>Ask Instacart (2023). <a href="https://cordcuttersnews.com/instacart-is-now-making-shopping-even-easier-by-using-ai/">https://cordcuttersnews.com/instacart-is-now-making-shopping-even-easier-by-using-ai/</a> and <a href="https://www.supermarketnews.com/grocery-technology/instacart-rolls-out-ask-instacart-chatgpt-feature">https://www.supermarketnews.com/grocery-technology/instacart-rolls-out-ask-instacart-chatgpt-feature</a></li>
<li>Cronometer, accurate databases. <a href="https://cronometer.com/features/accurate-databases.html">https://cronometer.com/features/accurate-databases.html</a></li>
</ol>
</section>
"""

# ================================================================ CSS and assembly

CSS = """
@page { size: letter; margin: 0.7in; }
* { box-sizing: border-box; }
html { font-size: 10.5pt; }
body { font-family: -apple-system, "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif; color: #3A2330; line-height: 1.27; margin: 0 auto; max-width: 7.1in; padding: 0.4in 0.2in; background: #fff; }
h1 { color: #D6336C; font-size: 24pt; margin: 0 0 4px; }
h2 { color: #D6336C; font-size: 15pt; margin: 14px 0 6px; padding-bottom: 3px; border-bottom: 2px solid #D6336C; break-after: avoid; }
h3 { color: #D6336C; font-size: 11.5pt; margin: 9px 0 3px; break-after: avoid; }
p { margin: 4px 0 6px; }
ul, ol { margin: 4px 0 8px; padding-left: 20px; } li { margin: 1px 0; }
a { color: #B02458; word-break: break-all; text-decoration: none; }
code { font-family: Menlo, Consolas, monospace; font-size: 9pt; background: #FFF0F5; padding: 0 3px; border-radius: 3px; }
.lead { font-size: 12pt; color: #3A2330; margin: 2px 0 8px; }
.callout { background: #FFF0F5; border-left: 4px solid #D6336C; padding: 7px 12px; margin: 9px 0; break-inside: avoid; }
.callout ul { margin: 3px 0 2px; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 9px; font-size: 8.8pt; }
th, td { border: 1px solid #E7C7D3; padding: 2px 6px; vertical-align: top; text-align: left; }
th { background: #FFF0F5; color: #3A2330; }
tr { break-inside: avoid; }
table.meta td { border: none; border-bottom: 1px solid #F1DDE5; padding: 3px 4px; } table.meta td:first-child { width: 12%; white-space: nowrap; }
figure { margin: 8px 0; break-inside: avoid; }
figure img, figure svg { width: 100%; height: auto; display: block; border: 1px solid #E7C7D3; }
figure svg { border: none; }
figure.w52 { width: 52%; margin-left: auto; margin-right: auto; }
figure.w60 { width: 60%; margin-left: auto; margin-right: auto; }
figure.w70 { width: 70%; margin-left: auto; margin-right: auto; }
figure.w56 { width: 46%; margin-left: auto; margin-right: auto; }
figure.w80 { width: 80%; margin-left: auto; margin-right: auto; }
figure.w86 { width: 78%; margin-left: auto; margin-right: auto; }
figure.narrow2 { width: 80%; margin-left: auto; margin-right: auto; }
figure.narrow { width: 62%; margin-left: auto; margin-right: auto; }
figcaption { font-size: 8.8pt; color: #6B4A5A; margin-top: 3px; }
.row { display: flex; gap: 6px; align-items: flex-start; } .row img { flex: 1 1 0; min-width: 0; width: 50%; }
.tcols { display: grid; grid-template-columns: 37% 1fr; gap: 8px; align-items: start; } .tcols > div { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.tcols img { width: 100%; }
.tsub { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; align-items: start; } .tsub > div { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.tsub > div:last-child img:last-child { width: 62%; }
.grid4 .row { flex-wrap: wrap; } .grid4 .row img { flex: 0 0 calc(50% - 3px); width: calc(50% - 3px); }
.splittable { break-inside: auto; } .splittable img { break-inside: avoid; }
.g3 .row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; align-items: start; } .g3 .row img { width: 100%; }
.g2 .row { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; align-items: start; } .g2 .row img { width: 100%; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; align-items: start; } .two > div { min-width: 0; }
.split { display: grid; grid-template-columns: 1.15fr 1fr; gap: 10px; align-items: start; }
.two figure { margin: 6px 0; }
section { margin-bottom: 4px; }
.appendix { font-size: 8.8pt; } .appendix table { font-size: 8.3pt; } ol.sources { font-size: 7.8pt; line-height: 1.2; padding-left: 18px; margin: 2px 0; } ol.sources li { margin: 0; }
@media print { body { padding: 0; max-width: none; } a { color: #B02458; } }
"""

TITLE = f"""
<header><h1>HomeBite</h1>
<div style="color:#6B4A5A;margin-bottom:6px">Final project report · Nicole Lin · MGT 409, AI Foundations for Managers, Yale SOM, Fall 2026</div></header>
"""

body = TITLE + "".join(SECTIONS) + APPENDIX
# number figures in order of appearance, then resolve references
order = re.findall(r'id="fig-([a-z0-9_]+)"', body)
numbers = {k: i + 1 for i, k in enumerate(order)}
body = re.sub(r"§([a-z0-9_]+)§", lambda m: str(numbers[m.group(1)]), body)
page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>HomeBite: final report</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><style>{CSS}</style></head>
<body>{body}</body></html>"""
OUT.write_text(page, encoding="utf-8")

print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB), {len(order)} figures")
for name, (w, h, size) in sorted(IMG_INFO.items()):
    print(f"  {name:45s} {w}x{h}  {size / 1024:.0f} KB")
if DISAGREE:
    print("CROSS-CHECK DIFFERENCES (files win):")
    for n, got, want in DISAGREE:
        print(f"  {n}: file says {got}, earlier report said {want}")
else:
    print("cross-check list: all values match the files")
