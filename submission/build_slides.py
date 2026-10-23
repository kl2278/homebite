"""Builds submission/slides.html (reveal.js, 10 slides). Every number and claim comes from submission/report.html.

Run from the project root with the project venv: python submission/build_slides.py
Standard library + Pillow only. Screenshots come from submission/screenshots/ (git-ignored) and are embedded as base64.
"""

import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "submission" / "screenshots"
OUT = ROOT / "submission" / "slides.html"
REVEAL = "5.1.0"
CDN = f"https://cdnjs.cloudflare.com/ajax/libs/reveal.js/{REVEAL}"
FONT_URL = "https://fonts.googleapis.com/css2?family=Nunito:wght@600;700;800&display=swap"
LABEL_FONT = "/System/Library/Fonts/Helvetica.ttc"


# ---------------------------------------------------------------- images

def crop(name, *boxes, gap=10, pad=(255, 255, 255)):
    """Crop one or more regions of a screenshot and stack them (a PIL image)."""
    im = Image.open(SHOTS / name).convert("RGB")
    parts = [im.crop(b) for b in boxes]
    width = max(p.width for p in parts)
    canvas = Image.new("RGB", (width, sum(p.height for p in parts) + gap * (len(parts) - 1)), pad)
    y = 0
    for p in parts:
        canvas.paste(p, (0, y))
        y += p.height + gap
    return canvas


def uri(im, max_w=1600):
    if im.width < 900:  # small crops are scaled up so they stay sharp when shown large
        im = im.resize((900, round(im.height * 900 / im.width)), Image.LANCZOS)
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    data, mime = buf.getvalue(), "image/png"
    if len(data) > 500_000:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88, optimize=True)
        data, mime = buf.getvalue(), "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def label_bar(text, width, fill):
    bar = Image.new("RGB", (width, 40), fill)
    d = ImageDraw.Draw(bar)
    d.text((14, 6), text, font=ImageFont.truetype(LABEL_FONT, 26), fill=(255, 255, 255))
    return bar


def stack(*ims, gap=8):
    width = max(i.width for i in ims)
    canvas = Image.new("RGB", (width, sum(i.height for i in ims) + gap * (len(ims) - 1)), (255, 255, 255))
    y = 0
    for i in ims:
        canvas.paste(i, (0, y))
        y += i.height + gap
    return canvas


def shot(im, alt, cls=""):
    return f'<img class="shot {cls}" alt="{alt}" src="{uri(im)}">'


# ---------------------------------------------------------------- art (original inline SVG)

DEFS = """<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
<symbol id="bowl" viewBox="0 0 120 110">
  <path d="M40 30c-8-8 8-12 0-22M60 30c-8-8 8-12 0-22M80 30c-8-8 8-12 0-22" fill="none" stroke="#F25C8A" stroke-width="5" stroke-linecap="round" class="steam"/>
  <path d="M10 52h100c0 30-20 48-50 48S10 82 10 52z" fill="#FF8FB1" stroke="#B8325F" stroke-width="5" stroke-linejoin="round"/>
  <path d="M10 52h100" stroke="#B8325F" stroke-width="5" stroke-linecap="round"/>
  <path d="M30 70q30 12 60 0" fill="none" stroke="#FFE4EC" stroke-width="5" stroke-linecap="round"/>
  <path d="M86 6L66 50M96 10L74 52" stroke="#B8325F" stroke-width="5" stroke-linecap="round"/>
  <circle cx="45" cy="52" r="5" fill="#FFFBF7"/><circle cx="58" cy="54" r="4" fill="#FFFBF7"/>
</symbol>
<symbol id="spark" viewBox="0 0 40 40"><path d="M20 2c2 11 7 16 18 18-11 2-16 7-18 18-2-11-7-16-18-18C13 18 18 13 20 2z" fill="#FFB8CF"/></symbol>
<symbol id="heart" viewBox="0 0 40 36"><path d="M20 34C4 22 2 14 6 8c4-6 11-4 14 2 3-6 10-8 14-2 4 6 2 14-14 26z" fill="#FF8FB1"/></symbol>
<symbol id="bag" viewBox="0 0 60 70"><path d="M8 22h44l4 44H4z" fill="#FFE4EC" stroke="#B8325F" stroke-width="4" stroke-linejoin="round"/><path d="M20 22c0-14 20-14 20 0" fill="none" stroke="#B8325F" stroke-width="4" stroke-linecap="round"/><path d="M30 38c-6-6-12 2-6 8l6 6 6-6c6-6 0-14-6-8z" fill="#F25C8A"/></symbol>
<symbol id="tick" viewBox="0 0 40 40"><circle cx="20" cy="20" r="19" fill="#BDEBD6"/><path d="M11 21l7 7 12-14" fill="none" stroke="#2F6B52" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></symbol>
</defs></svg>"""

SPARKLES = ('<svg class="sp s1" viewBox="0 0 40 40"><use href="#spark"/></svg><svg class="sp s2" viewBox="0 0 40 40"><use href="#spark"/></svg>'
            '<svg class="sp s3" viewBox="0 0 40 36"><use href="#heart"/></svg>')


def icon(name="bowl", cls="ico"):
    vb = {"bowl": "0 0 120 110", "bag": "0 0 60 70", "heart": "0 0 40 36", "spark": "0 0 40 40", "tick": "0 0 40 40"}[name]
    return f'<svg class="{cls}" viewBox="{vb}"><use href="#{name}"/></svg>'


def slide(title, body, notes, extra_cls=""):
    head = f'<div class="hd">{icon()}<h2>{title}</h2></div>' if title else ""
    return (f'<section class="{extra_cls}" data-background-gradient="linear-gradient(135deg,#FFF5F8 0%,#FFE4EC 100%)"><div class="inner">{SPARKLES}{head}{body}</div>'
            f'<aside class="notes">{notes}</aside></section>')


# ---------------------------------------------------------------- diagram (slide 4)

def box(x, y, w, h, title, sub, fill, stroke, tag=None):
    t = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="{fill}" stroke="{stroke}" stroke-width="4"/>'
         f'<text x="{x + w / 2}" y="{y + h / 2 - 2}" text-anchor="middle" font-size="26" font-weight="800" fill="#4A2C3A">{title}</text>'
         f'<text x="{x + w / 2}" y="{y + h / 2 + 26}" text-anchor="middle" font-size="20" font-weight="700" fill="#7A4A60">{sub}</text>')
    if tag:
        t += (f'<rect x="{x + w - 58}" y="{y - 14}" width="50" height="28" rx="14" fill="#F25C8A"/>'
              f'<text x="{x + w - 33}" y="{y + 6}" text-anchor="middle" font-size="18" font-weight="800" fill="#FFFFFF">{tag}</text>')
    return t


def arrow(x1, y1, x2, y2, color="#F25C8A", dash=False):
    d = ' stroke-dasharray="10,8"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="6" stroke-linecap="round"{d} marker-end="url(#ah)"/>'


def diagram():
    pink, cream, mint, blue = "#FFE4EC", "#FFFBF7", "#BDEBD6", "#E6F0FF"
    cols = [30, 270, 510, 750, 990]
    w, h = 200, 92
    y1, y2 = 120, 300
    p = ['<svg class="diagram" viewBox="0 0 1220 440" xmlns="http://www.w3.org/2000/svg" font-family="Nunito, ui-rounded, Trebuchet MS, system-ui, sans-serif">',
         '<defs><marker id="ah" markerUnits="userSpaceOnUse" markerWidth="18" markerHeight="18" refX="12" refY="9" orient="auto"><path d="M0,0L18,9L0,18z" fill="#F25C8A"/></marker></defs>']
    # trusted settings on top
    p.append(f'<rect x="270" y="6" width="680" height="62" rx="31" fill="{blue}" stroke="#6C8FD6" stroke-width="4"/>'
             '<text x="610" y="45" text-anchor="middle" font-size="26" font-weight="800" fill="#2D467F">Sidebar settings (trusted): store, allergies, diet</text>')
    p.append(arrow(390, 70, 390, 112, "#6C8FD6") + arrow(610, 70, 610, 112, "#6C8FD6"))
    p.append(box(cols[0], y1, w, h, "Input guard", "rules + 1 AI call", cream, "#F25C8A"))
    p.append(box(cols[1], y1, w, h, "Intake", "agent", pink, "#F25C8A", "AI"))
    p.append(box(cols[2], y1, w, h, "Analyst", "agent", pink, "#F25C8A", "AI"))
    p.append(box(cols[3], y1, w, h, "Substitution", "agent", pink, "#F25C8A", "AI"))
    p.append(box(cols[4], y1, w, h, "Catalog", "163 items", blue, "#6C8FD6"))
    p.append(box(cols[3], y2, w, h, "Verifier", "plain code", mint, "#2F8F6B"))
    p.append(box(cols[2], y2, w, h, "Writer", "agent", pink, "#F25C8A", "AI"))
    p.append(box(cols[1], y2, w, h, "Output check", "code", cream, "#F25C8A"))
    p.append(box(cols[0], y2, w, h, "Results", "tables by code", cream, "#F25C8A"))
    for i in range(3):
        p.append(arrow(cols[i] + w + 2, y1 + h / 2, cols[i + 1] - 4, y1 + h / 2))
    p.append(arrow(cols[3] + w + 2, y1 + h / 2, cols[4] - 4, y1 + h / 2, "#6C8FD6"))
    p.append(arrow(cols[3] + w / 2 - 30, y1 + h + 2, cols[3] + w / 2 - 30, y2 - 4))
    for i in (3, 2, 1):
        p.append(arrow(cols[i] - 2, y2 + h / 2, cols[i - 1] + w + 4, y2 + h / 2))
    # re-run loop
    p.append(f'<path d="M{cols[3] + w / 2 + 40} {y2 - 2} C{cols[3] + w / 2 + 40} {y1 + h + 40}, {cols[3] + w / 2 + 40} {y1 + h + 40}, {cols[3] + w / 2 + 40} {y1 + h + 4}" fill="none" stroke="#B8325F" stroke-width="6" stroke-dasharray="10,8" stroke-linecap="round" marker-end="url(#ah)"/>')
    p.append('<text x="1010" y="248" font-size="22" font-weight="800" fill="#B8325F">allergen or diet</text><text x="1010" y="274" font-size="22" font-weight="800" fill="#B8325F">conflict: re-run once</text>')
    p.append('<text x="610" y="430" text-anchor="middle" font-size="24" font-weight="700" fill="#7A4A60">Four AI agents. One Verifier that is plain code. A guard before, a check after.</text>')
    p.append("</svg>")
    return "".join(p)


def cost_chart():
    rows = [("Analyst", 59.0), ("Substitution", 21.4), ("Writer", 14.3), ("Intake", 3.1), ("Guard", 2.2)]
    p = ['<svg class="chart" viewBox="0 0 560 290" xmlns="http://www.w3.org/2000/svg" font-family="Nunito, ui-rounded, Trebuchet MS, system-ui, sans-serif">']
    for i, (name, share) in enumerate(rows):
        y = 8 + i * 56
        wbar = 3.4 * share + 8
        p.append(f'<text x="0" y="{y + 32}" font-size="26" font-weight="800" fill="#4A2C3A">{name}</text>'
                 f'<rect x="170" y="{y}" width="{wbar:.0f}" height="44" rx="22" fill="{"#F25C8A" if i == 0 else "#FF8FB1"}"/>'
                 f'<text x="{176 + wbar:.0f}" y="{y + 32}" font-size="26" font-weight="800" fill="#B8325F">{share}%</text>')
    p.append("</svg>")
    return "".join(p)


# ---------------------------------------------------------------- screenshots

# slide 5: the kung pao peanut run (left-out ingredients and the allergen warning) and the Verifier trace panel
demo_result = crop("safety_peanuts_removed.png", (55, 150, 420, 300), (60, 690, 415, 810))
demo_trace = crop("trace_verifier.png", (0, 22, 300, 108), (0, 225, 460, 378), gap=6)
# slide 6: ChatGPT shopping list; HomeBite before / after the diet fix (one composite with labels)
chat_shot = crop("chatgpt_test_2.png", (0, 0, 605, 417))
before = crop("homebite_test_1.png", (300, 640, 800, 705))
after = stack(crop("homebite_after_diet_2.png", (300, 165, 800, 260)), crop("homebite_after_diet_3.png", (300, 16, 800, 136)))
before_after = stack(label_bar("BEFORE the fix", 500, (184, 50, 95)), before, label_bar("AFTER the fix", 500, (242, 92, 138)), after)
# slide 8: what the student typed, the pass/fail evidence
inj = crop("safety_injection_v2.png", (140, 322, 1100, 388))
med = crop("safety_medical_v2.png", (30, 315, 1000, 375))
peanut = crop("safety_peanuts_removed.png", (63, 155, 392, 225))
pork = crop("homebite_after_diet_2.png", (300, 165, 800, 230))

SLIDES = []

# 1 ------------------------------------------------------------------ title
SLIDES.append(slide("", f"""
<div class="title-wrap">
  <div class="big-bowl">{icon("bowl", "bowl-lg")}</div>
  <div class="title-text">
    <h1>HomeBite</h1>
    <p class="tag">A bite of home, built from what your store sells.</p>
    <p class="pitch">Adapt a dish from home to your local store, with nutrition computed in code instead of guessed by AI.</p>
    <p class="who"><span class="pill">Nicole Lin</span> <span class="pill soft">MGT 409 - AI Foundations for Managers - Yale SOM</span></p>
  </div>
</div>""", "HomeBite helps international students recreate dishes from home with what their own grocery store sells. The model proposes ingredients and substitutes, and code does the checking and the nutrition math. This is a prototype I built for MGT 409.", "title-slide"))

# 2 ------------------------------------------------------------------ problem
SLIDES.append(slide("Food is part of the move.", """
<div class="cards3">
  <div class="card fragment fade-up"><div class="num">1,177,766</div><p>international students in the U.S., 2024/25</p></div>
  <div class="card fragment fade-up"><div class="num sm">Stores matter</div><p>Food choices followed whether native foods were sold locally</p><span class="note">one survey, 142 students</span></div>
  <div class="card fragment fade-up"><div class="num">80%</div><p>of those who rated belonging differently felt more with home foods</p><span class="note">small study: a hint</span></div>
</div>
<div class="card wide fragment fade-up"><p><b>Today:</b> a web search, a chatbot, or asking family. My timed search took about 2 minutes and gave a recipe only.</p><span class="note">one dish, one attempt, self-timed</span></div>
""", "The Open Doors figure counts international students at U.S. institutions in 2024/25. The two studies are small, so I use them as hints that familiar food matters and that store availability shapes choices. My own timing is one dish, one attempt, and produced a recipe only."))

# 3 ------------------------------------------------------------------ what is new
SLIDES.append(slide("What's new, and what isn't", """
<div class="cols2">
  <div class="card"><h3>Already out there <small>(as publicly described)</small></h3>
    <ul class="plain">
      <li><b>General chatbots:</b> in my one test, named products and photos</li>
      <li><b>Samsung Food:</b> recipes, swaps, shopping lists</li>
      <li><b>Ask Instacart:</b> real catalogs at huge scale</li>
      <li><b>Cronometer:</b> broader nutrition databases</li>
    </ul></div>
  <div class="card hot"><h3>HomeBite adds</h3>
    <ul class="plain ticks">
      <li>Starts from a dish from home</li>
      <li>Products only from the store's catalog</li>
      <li>Nutrition computed in code from USDA data; excluded items listed</li>
      <li>Allergen and diet checks that trigger a re-run</li>
      <li>"Left out" is an allowed answer</li>
    </ul></div>
</div>
<div class="ribbon">Prototype: 163-item starter catalog</div>
""", "The other tools are described as publicly announced in 2023 and I did not test them hands-on, apart from one chatbot test. HomeBite is narrower: it starts from one dish and rebuilds it for one store. The difference is the verification layer, and it runs on a starter catalog of 163 illustrative items."))

# 4 ------------------------------------------------------------------ how it works
SLIDES.append(slide("How it works", f"""
<div class="diag">{diagram()}</div>
<div class="ribbon big">The model proposes. Code checks.</div>
""", "A request first passes the input guard, which is free rules plus one cheap classifier call. Four AI agents do the language work and a Verifier that is plain code checks products, computes nutrition and runs the allergen and diet checks. If a conflict is found, Substitution is re-run once, and an output check screens the final text."))

# 5 ------------------------------------------------------------------ demo
SLIDES.append(slide("A real run: kung pao, peanut allergy", f"""
<div class="cols2 tight">
  <div class="card imgcard">{shot(demo_result, "Peanuts left out and struck through; yellow allergen warning")}<span class="cap">Peanuts left out; yellow check-the-label warning</span></div>
  <div class="card imgcard">{shot(demo_trace, "Verifier trace panel: catalog checks, nutrition, allergen check")}<span class="cap">The Verifier panel is code, not AI</span></div>
</div>
<div class="chips three"><span class="chip">{icon("tick", "tk")}Every ingredient matched to USDA or listed as unmatched</span><span class="chip">{icon("tick", "tk")}Every product exists in the catalog</span><span class="chip">{icon("tick", "tk")}Every number comes from a tool result</span></div>
""", "This is a live run with Walmart selected and a peanut allergy. The first check flagged peanuts, the substitution step re-ran once, and four ingredients were left out. The page shows a yellow warning, not a green box, because soy sauce, cornstarch and vegetable oil could not be confirmed peanut-free."))

# 6 ------------------------------------------------------------------ head to head
SLIDES.append(slide("The test found a bug in my app. I fixed it.", f"""
<div class="cols2 tight">
  <div class="card imgcard">{shot(chat_shot, "ChatGPT Walmart shopping list")}<span class="cap">ChatGPT (GPT-6): vegetarian, three named Walmart products, photos; 1 m 15 s displayed</span></div>
  <div class="card imgcard">{shot(before_after, "HomeBite before and after the diet fix")}<span class="cap">HomeBite: pork belly in a "vegetarian" recipe, then flagged and removed, with a Diet check box</span></div>
</div>
<div class="chips"><span class="chip soft">One dish, one run each</span><span class="chip soft">ChatGPT did several things better in this test</span></div>
""", "I gave ChatGPT and HomeBite the same vegetarian kimchi jjigae request for Walmart. ChatGPT met the vegetarian requirement and named three products with prices, and I clicked two of its links and both were real. HomeBite kept pork belly because the diet reached the AI only as text, so I added a code check and re-ran it. This is one dish and one run each, so it shows a gap, not a ranking."))

# 7 ------------------------------------------------------------------ cost
SLIDES.append(slide("Cost to run", f"""
<div class="cols2 tight">
  <div>
    <div class="bigs"><div class="card"><div class="num">$0.002414</div><p>per run</p></div><div class="card"><div class="num">33.2 s</div><p>per run</p></div></div>
    <div class="card"><div class="mini">Cost share by stage</div>{cost_chart()}</div>
  </div>
  <div>
    <div class="card"><div class="mini">Per month, 12 runs per user <small>(my assumption)</small></div>
      <div class="proj"><span>1 user</span><b>$0.03</b><span>100 users</span><b>$2.90</b><span>10,000 users</span><b>$289.72</b></div></div>
    <div class="card hot"><p>Cost-saver: cost <b>-16.9%</b>, but nutrition matching fell from <b>91.7%</b> to <b>82.0%</b>, so I did not ship it.</p></div>
  </div>
</div>
""", "These are averages over 10 baseline runs, computed from token counts with the course prices; the Analyst, which looks up every ingredient, is more than half of the cost. The monthly figures use 12 runs per user per month, which is my assumption, and exclude hosting. The cost-saver tested three levers together, so I cannot say which one lowered the match rate."))

# 8 ------------------------------------------------------------------ safety
SLIDES.append(slide("Safety", f"""
<div class="grid2x2">
  <div class="card imgcard">{shot(inj, "Typed injection request", "sm")}<b>Prompt injection blocked at 0 tokens</b></div>
  <div class="card imgcard">{shot(med, "Typed medical question", "sm")}<b>Medical request declined</b><span class="note">342 in, 41 out tokens</span></div>
  <div class="card imgcard">{shot(peanut, "Peanuts struck through", "sm")}<b>Allergen found, removed, re-checked</b></div>
  <div class="card imgcard">{shot(pork, "Pork belly struck through", "sm")}<b>Diet conflict found, removed, re-checked</b></div>
</div>
<p class="line">Caps on spend: per run, session, day and hour. <span class="pill">Safety demo 19/19</span> <span class="pill">268 tests</span></p>
<p class="line soft">My own measurement and a head-to-head test found two gaps (panko, pork belly). Both fixed and re-checked.</p>
""", "Each defense has evidence in the report: the blocked and declined requests, the live peanut run, and the pork belly run after the fix. The safety demo passed 19 of 19 again, but the model replies were probably served from the provider's cache, so that is not a fresh sample of the model. The checks are keyword lists, not guarantees."))

# 9 ------------------------------------------------------------------ impact
SLIDES.append(slide("A real user tried it", """
<div class="cols2 tight">
  <div class="card">
    <div class="bigs"><div><div class="num">18 s</div><span class="note">run time</span></div><div><div class="num">$0.0015</div><span class="note">estimated cost</span></div></div>
    <p>A friend tried it on my laptop and found the instructions easy to follow. <span class="pill soft">1 tester - needed no substitutions</span></p>
    <p class="quote">“This is so interesting! I can't wait to try recreating my mom's dishes with this!”</p>
  </div>
  <div>
    <div class="card"><div class="mini">His ideas</div><div class="chips left"><span class="chip soft">Multi-select goals and diets</span><span class="chip soft">Dish pictures</span><span class="chip soft">Chat about the dish</span></div></div>
    <div class="card"><p>My search: about 2 min, recipe only. App: 16.1 to 56.6 s over 20 runs.</p><span class="note">not like-for-like</span></div>
  </div>
</div>
""", "Alex is a friend who tried the app on my laptop with his mom's potato beef stew. It needed no substitutions, so this tested usability, not the substitution engine. These are measured numbers from one run and one tester; time saved, money saved and health benefit are potential, not measured."))

# 10 ----------------------------------------------------------------- limits and next
SLIDES.append(slide("Limits and next", f"""
<div class="cols2">
  <div class="card"><h3>Not there yet</h3>
    <ul class="plain">
      <li>163-item starter catalog: 7 substitutes, 13 no match, 5 allergy removals</li>
      <li>Goal selector not enforced</li>
      <li>No rebalancing when a main protein is removed</li>
      <li>One tester</li>
    </ul></div>
  <div class="card hot"><h3>Next</h3>
    <ul class="plain">
      <li>Real store data</li>
      <li>Goal check in code</li>
      <li>Multi-select goals and diets</li>
      <li>Chat and pictures</li>
    </ul></div>
</div>
<div class="thanks">{icon("bowl", "bowl-sm")}<span>Thank you</span></div>
""", "The catalog numbers are from the 10 baseline measurement runs: seven ingredients got a substitute, thirteen had no catalog match and five were removed because of the dish's allergy. The goal selector is passed to the AI but not verified by code. Next steps are real store data, a goal check in code, multi-select goals and diets, chat and pictures."))

CSS = """
:root{--bg:#FFF5F8;--card:#FFFFFF;--soft:#FFE4EC;--candy:#FF8FB1;--hot:#F25C8A;--rose:#B8325F;--text:#4A2C3A;--cream:#FFFBF7;--mint:#BDEBD6}
html,body{background:var(--bg)}
.reveal{font-family:"Nunito",ui-rounded,"Avenir Next Rounded","Trebuchet MS",system-ui,sans-serif;font-weight:600;color:var(--text);font-size:30px}
.reveal .slides{text-align:left}
.reveal .slides>section{height:720px;padding:0;box-sizing:border-box}
.inner{position:relative;height:720px;box-sizing:border-box;padding:30px 56px 26px;display:flex;flex-direction:column;gap:18px;overflow:hidden}
.hd{display:flex;align-items:center;gap:18px;flex:none}
.reveal h1,.reveal h2,.reveal h3{font-family:inherit;color:var(--rose);text-transform:none;margin:0;letter-spacing:0}
.reveal h2{font-size:54px;font-weight:800;line-height:1.1}
.reveal h3{font-size:34px;font-weight:800;margin-bottom:10px}
.reveal h3 small{font-size:24px;color:var(--text);font-weight:700}
.ico{width:64px;height:58px;flex:none}
.reveal p{margin:0;line-height:1.25}
.card{background:var(--card);border-radius:24px;box-shadow:0 8px 24px rgba(184,50,95,.14);padding:20px 26px;box-sizing:border-box}
.card.hot{background:var(--soft);border:3px solid var(--candy)}
.card.wide{flex:none}
.cards3{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;flex:1}
.cards3 .card{display:flex;flex-direction:column;justify-content:center;gap:10px}
.num{font-size:64px;font-weight:800;color:var(--hot);line-height:1.05}
.num.sm{font-size:48px}
.note{font-size:22px;color:var(--rose);font-weight:700}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:24px;flex:1;min-height:0}
.cols2.tight{gap:20px}
ul.plain{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:12px}
ul.plain li{font-size:29px;line-height:1.2;padding-left:34px;position:relative}
ul.plain li::before{content:"";position:absolute;left:0;top:9px;width:18px;height:18px;border-radius:50%;background:var(--candy)}
ul.ticks li::before{background:var(--mint);box-shadow:inset 0 0 0 3px #2F6B52}
.ribbon{flex:none;align-self:flex-start;background:var(--hot);color:#fff;border-radius:999px;padding:8px 30px;font-size:30px;font-weight:800}
.ribbon.big{align-self:center;font-size:40px;padding:10px 40px}
.diag{flex:1;display:flex;align-items:center;justify-content:center;min-height:0}
.diagram{width:100%;height:100%}
.imgcard{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;min-height:0;text-align:center}
.imgcard img.shot{max-width:100%;max-height:330px;border-radius:16px;border:3px solid var(--candy);object-fit:contain}
.cols2.tight .imgcard img.shot{max-height:330px}
.grid2x2 .imgcard img.shot{max-height:110px}
.cap{font-size:21px;color:var(--rose);font-weight:700;line-height:1.2}
.chips{display:flex;gap:14px;flex-wrap:wrap;flex:none;justify-content:center}
.chips.three{display:grid;grid-template-columns:repeat(3,1fr)}
.chips.three .chip{border-radius:28px;font-size:28px;text-align:left}
.chips.left{justify-content:flex-start;margin-top:8px}
.chip{display:inline-flex;align-items:center;gap:10px;background:#fff;border:3px solid var(--candy);border-radius:999px;padding:8px 20px;font-size:28px;font-weight:800;line-height:1.15}
.chip.soft{background:var(--soft)}
.tk{width:34px;height:34px;flex:none}
.pill{display:inline-block;background:var(--hot);color:#fff;border-radius:999px;padding:4px 20px;font-size:28px;font-weight:800}
.pill.soft{background:var(--soft);color:var(--rose)}
.bigs{display:flex;gap:18px;margin-bottom:14px}
.cols2.tight>.card{display:flex;flex-direction:column;justify-content:center;gap:14px}
.bigs .card{flex:1;text-align:center;padding:12px}
.bigs .card p{font-size:26px}
.mini{font-size:26px;font-weight:800;color:var(--rose);margin-bottom:6px}
.mini small{font-size:22px;color:var(--text)}
.chart{width:100%;height:auto}
.proj{display:grid;grid-template-columns:1fr auto;gap:8px 20px;font-size:30px;align-items:center}
.proj b{color:var(--hot);font-size:36px;font-weight:800}
.cols2>div>.card+.card{margin-top:16px}
.grid2x2{display:grid;grid-template-columns:1fr 1fr;gap:16px;flex:1;min-height:0}
.grid2x2 .card{padding:12px 16px;gap:6px}
.grid2x2 b{font-size:27px;color:var(--rose);font-weight:800;line-height:1.1}
.line{font-size:29px;flex:none;line-height:1.2}
.line.soft{color:var(--rose)}
.quote{font-size:30px;color:var(--rose);font-weight:700;margin-top:10px}
.thanks{display:flex;align-items:center;gap:18px;align-self:center;font-size:52px;font-weight:800;color:var(--rose);flex:none}
.bowl-sm{width:70px;height:64px}
.title-slide .inner{justify-content:center}
.title-wrap{display:flex;align-items:center;gap:50px}
.bowl-lg{width:330px;height:300px;flex:none}
.title-text h1{font-size:112px;font-weight:800;line-height:1}
.tag{font-size:40px;font-weight:800;color:var(--hot);margin:12px 0}
.pitch{font-size:30px;margin-bottom:22px}
.who{display:flex;gap:12px;flex-wrap:wrap}
.sp{position:absolute;width:44px;height:44px;opacity:.8;animation:float 6s ease-in-out infinite;pointer-events:none}
.s1{right:60px;top:26px}.s2{right:150px;top:90px;width:28px;height:28px;animation-delay:-2s}.s3{right:40px;bottom:30px;width:40px;height:36px;animation-delay:-4s}
@keyframes float{0%,100%{transform:translateY(0) rotate(0)}50%{transform:translateY(-14px) rotate(12deg)}}
.steam{animation:float 4s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){.sp,.steam{animation:none}}
.reveal .slide-number{color:var(--rose);background:transparent;font-weight:800;font-size:22px}
.reveal .progress{color:var(--hot)}
@page{size:1280px 720px;margin:0}
@media print{*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""

HTML = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>HomeBite: slides</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONT_URL}">
<link rel="stylesheet" href="{CDN}/reveal.min.css">
<style>{CSS}</style></head>
<body>{DEFS}
<div class="reveal"><div class="slides">
{"".join(SLIDES)}
</div></div>
<script src="{CDN}/reveal.min.js"></script>
<script src="{CDN}/plugin/notes/notes.min.js"></script>
<script>
Reveal.initialize({{width:1280,height:720,margin:0,minScale:0.2,maxScale:2,center:false,hash:true,slideNumber:true,progress:true,controls:true,
  transition:"fade",pdfSeparateFragments:false,plugins:[RevealNotes]}});
</script></body></html>"""

OUT.write_text(HTML, encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB), {len(SLIDES)} slides, reveal.js {REVEAL}")
