#!/usr/bin/env python3
"""
Build the guest guide from markdown into:
  - docs/index.html        a self-contained web page (GitHub Pages)
  - docs/welcome-guide.pdf a print-ready A5 booklet PDF (bleed + crop marks)

Single source of truth:
  - site.yaml        global settings (names, contacts, colours, brand, domain)
  - content/*.md     one file per section, ordered by filename, first line = "# Title"

Usage:  python build.py
"""

import base64
import re
from pathlib import Path

import yaml
import markdown
from weasyprint import HTML

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
FONTS = ROOT / "assets" / "fonts"
BRAND = ROOT / "assets" / "brand"
DOCS = ROOT / "docs"
PRIVATE = ROOT / "private"

MD_EXT = ["extra", "admonition", "sane_lists", "smarty", "attr_list"]

INTER_WEIGHTS = [200, 300, 400, 500, 600, 700]


# ---------- helpers ----------------------------------------------------------

def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def data_uri(path, mime):
    return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"


IMG_MIME = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}


def embed_images(html):
    """Inline <img src="assets/..."> as data URIs so the web page stays self-contained."""
    def repl(m):
        rel = m.group(1)
        fp = ROOT / rel
        if not fp.exists():
            return m.group(0)
        mime = IMG_MIME.get(fp.suffix.lower(), "application/octet-stream")
        b64 = base64.b64encode(fp.read_bytes()).decode()
        return f'src="data:{mime};base64,{b64}"'
    return re.sub(r'src="(assets/[^"]+)"', repl, html)


def load_sections():
    sections = []
    for i, f in enumerate(sorted(CONTENT.glob("*.md")), start=1):
        raw = f.read_text(encoding="utf-8").strip()
        lines = raw.splitlines()
        title, body_lines = "Untitled", lines
        for j, line in enumerate(lines):
            if line.startswith("# "):
                title = line[2:].strip()
                body_lines = lines[j + 1:]
                break
        sid = re.sub(r"^\d+[-_]", "", f.stem)
        sid = re.sub(r"[^a-z0-9]+", "-", sid.lower()).strip("-")
        sections.append({"num": f"{i:02d}", "id": sid, "title": title,
                         "md": "\n".join(body_lines).strip()})
    return sections


def apply_templates(text, cfg, mode):
    """Substitute {{key}} from cfg; redact private keys on the web."""
    private = set(cfg.get("private", []))
    placeholder = cfg.get("private_placeholder", "Provided privately")

    def repl(m):
        key = m.group(1).strip()
        if mode == "web" and key in private:
            return placeholder
        val = cfg.get(key)
        return str(val) if val is not None else m.group(0)

    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", repl, text)


def apply_private_blocks(text, cfg, mode):
    """:::private ... ::: blocks render in the PDF; on the web they become a note."""
    note = cfg.get("private_block_note",
                   "These details are shared in your booking confirmation and welcome PDF.")

    def repl(m):
        if mode == "web":
            return f'!!! note "Provided privately"\n    {note}'
        return m.group(1)

    return re.sub(r"(?ms)^:::private[ \t]*\n(.*?)\n:::[ \t]*$", repl, text)


def font_faces(embed):
    """embed=True -> base64 woff2 data URIs (web); else local ttf file URLs (print)."""
    out = []
    for wt in INTER_WEIGHTS:
        if embed:
            src = f"url({data_uri(FONTS / f'inter-latin-{wt}-normal.woff2','font/woff2')}) format('woff2')"
        else:
            url = (FONTS / f"inter-latin-{wt}-normal.ttf").resolve().as_uri()
            src = f"url({url}) format('truetype')"
        out.append(f"@font-face{{font-family:'Inter';font-style:normal;"
                   f"font-weight:{wt};font-display:swap;src:{src};}}")
    return "\n".join(out)


# ---------- shared CSS -------------------------------------------------------

def base_css(cfg):
    r, g, b = hex_to_rgb(cfg["accent"])
    return f"""
:root{{
  --paper:#FCFCFC; --ink:#232427; --muted:#6E7176; --line:#E6E6E6;
  --accent:{cfg['accent']};
  --accent-soft:rgba({r},{g},{b},.12); --accent-line:#D2D2D2;
}}
*{{box-sizing:border-box;}}
body{{font-family:'Inter',system-ui,sans-serif;color:var(--ink);background:var(--paper);
  line-height:1.62;margin:0;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;}}
h1,h2,h3{{margin:0;font-weight:400;}}
h1,h2{{font-weight:300;letter-spacing:-.01em;line-height:1.15;}}
h3{{font-weight:600;letter-spacing:.005em;}}
p{{margin:0 0 .85em;}}
a{{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--accent-line);}}
strong{{font-weight:600;}}
ul,ol{{margin:0 0 1em;padding-left:1.2em;}}
li{{margin:.32em 0;}}
li::marker{{color:var(--accent);}}

.eyebrow{{font-weight:600;text-transform:uppercase;letter-spacing:.16em;color:var(--accent);}}

/* at-a-glance */
.glance{{border:1px solid var(--line);border-radius:4px;}}
.glance .label{{font-weight:600;text-transform:uppercase;letter-spacing:.16em;
  color:var(--accent);}}
.glance .row{{display:flex;gap:1em;padding:.55em 0;border-top:1px solid var(--line);}}
.glance .row:first-of-type{{border-top:0;}}
.glance .k{{flex:0 0 36%;color:var(--muted);}}
.glance .v{{flex:1;}}

/* contents */
.contents .label{{font-weight:600;text-transform:uppercase;letter-spacing:.16em;
  color:var(--accent);}}
.contents ol{{list-style:none;padding:0;margin:0;}}
.contents li{{display:flex;align-items:baseline;border-bottom:1px solid var(--line);}}
.contents .c-num{{color:var(--accent);font-weight:600;font-variant-numeric:tabular-nums;}}

/* sections */
.section-num{{color:var(--accent);font-weight:600;font-variant-numeric:tabular-nums;}}

/* callouts */
/* callouts (monochrome — hierarchy by border weight) */
.admonition{{border-left:2px solid #C9CCCF;background:#F4F4F4;
  border-radius:0 3px 3px 0;}}
.admonition>:last-child{{margin-bottom:0;}}
.admonition-title{{font-weight:600;margin:0 0 .3em;color:var(--ink);}}
.admonition.warning{{border-left:3px solid #8A8E92;}}
.admonition.danger{{border-left:4px solid #2A2C2F;}}
.admonition.danger .admonition-title{{text-transform:uppercase;letter-spacing:.05em;}}
.admonition.danger .admonition-title::before{{content:"";display:inline-block;
  width:.95em;height:.95em;margin-right:.45em;vertical-align:-.14em;
  background:no-repeat center/contain;
  background-image:url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjMjMyNDI3IiBzdHJva2Utd2lkdGg9IjIuMSIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMTIgMy40IDIyIDIwLjQgSDIgWiIvPjxsaW5lIHgxPSIxMiIgeTE9IjkuNiIgeDI9IjEyIiB5Mj0iMTQuMiIvPjxsaW5lIHgxPSIxMiIgeTE9IjE3LjQiIHgyPSIxMiIgeTI9IjE3LjQiLz48L3N2Zz4=");}}

/* figures / images */
figure.fig{{margin:1.4rem 0;text-align:center;}}
.section img,figure.fig img{{max-width:100%;height:auto;display:block;margin:0 auto;border-radius:4px;}}
figure.fig figcaption{{font-size:.82rem;color:var(--muted);margin-top:.5rem;}}
"""


def web_css(cfg):
    return """
.page{max-width:46rem;margin:0 auto;padding:0 1.4rem 5rem;}

/* masthead: sticky bar + hero (silver / white) */
.masthead{background:var(--paper);color:var(--ink);}
.bar{position:sticky;top:0;z-index:10;background:rgba(252,252,252,.92);
  backdrop-filter:saturate(140%) blur(8px);border-bottom:1px solid var(--line);}
.bar .inner{max-width:46rem;margin:0 auto;padding:.7rem 1.4rem;
  display:flex;align-items:center;justify-content:space-between;gap:1rem;}
.bar img{height:1.5rem;width:auto;display:block;}
.btn{font-size:.74rem;font-weight:600;letter-spacing:.04em;color:var(--paper);
  background:var(--ink);padding:.46rem .85rem;border-radius:3px;border-bottom:0;
  white-space:nowrap;text-transform:uppercase;}
.btn:hover{background:#000;}

.hero{max-width:46rem;margin:0 auto;padding:3.4rem 1.4rem 3.4rem;
  border-bottom:1px solid var(--line);}
.hero .eyebrow{font-size:.72rem;color:var(--accent);}
.hero .place{font-weight:200;text-transform:uppercase;letter-spacing:.06em;
  font-size:clamp(2rem,6.5vw,3.05rem);color:var(--ink);margin:.7rem 0 .6rem;}
.hero .tagline{font-size:1.08rem;color:var(--muted);max-width:32ch;}
.hero .loc{font-size:.72rem;font-weight:500;text-transform:uppercase;letter-spacing:.18em;
  color:var(--muted);margin-top:1.4rem;}
.hero .rule{width:2.6rem;height:1px;background:var(--accent);border:0;margin:1.4rem 0 0;}

.glance{padding:1.1rem 1.3rem;margin:2.8rem 0 3rem;}
.glance .label{font-size:.72rem;margin-bottom:.4rem;display:block;}

.contents{margin:0 0 3.4rem;}
.contents .label{font-size:.72rem;margin-bottom:.7rem;display:block;}
.contents li{padding:.62rem 0;}
.contents .c-num{margin-right:.9rem;font-size:.9rem;}
.contents a{border-bottom:0;color:var(--ink);}
.contents a:hover{color:var(--accent);}

.section{padding:2.6rem 0;border-top:1px solid var(--line);}
.section .eyebrow{font-size:.72rem;display:block;margin-bottom:.5rem;}
.section .section-num{margin-right:.5rem;}
.section-title{font-size:clamp(1.65rem,4.4vw,2.05rem);margin-bottom:1.1rem;}
.section h3{font-size:.96rem;margin:1.6rem 0 .5rem;text-transform:uppercase;letter-spacing:.04em;}
.section h3:first-of-type{margin-top:.3rem;}
.admonition{padding:.85rem 1.1rem;margin:1.2rem 0;}

.foot{color:var(--muted);font-size:.82rem;text-align:center;padding-top:2rem;}
.foot .co{display:block;color:var(--muted);text-transform:uppercase;letter-spacing:.16em;
  font-size:.68rem;margin-top:.4rem;}

:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:2px;}
html{scroll-behavior:smooth;}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto;}}
@media (max-width:480px){.hero{padding-top:2.4rem;}.glance .row{flex-direction:column;gap:.1em;}
  .glance .k{flex-basis:auto;}}
"""


def print_css(cfg):
    return """
@page{
  size:A5; bleed:3mm; marks:crop;
  margin:16mm 15mm 17mm;
  @bottom-center{content:counter(page);font-family:'Inter';font-size:8pt;color:#9aa4ae;}
}
@page :left { margin-left:14mm; margin-right:19mm; }
@page :right{ margin-left:19mm; margin-right:14mm; }
@page cover{ margin:0; @bottom-center{content:none;} }

html,body{font-size:10.2pt;line-height:1.5;background:#fff;}
a{color:var(--ink);border-bottom:0;}

.cover{page:cover;height:210mm;color:var(--ink);text-align:center;
  display:flex;flex-direction:column;justify-content:center;align-items:center;
  padding:0 18mm;break-after:page;}
.cover-content{width:100%;}
.cover-logo{display:block;width:80mm;max-width:80%;margin:0 auto 14mm;}
.cover .eyebrow{font-size:8pt;color:var(--accent);}
.cover .place{font-weight:200;text-transform:uppercase;letter-spacing:.08em;
  font-size:25pt;color:var(--ink);margin:5mm 0 4mm;}
.cover .tagline{font-size:12pt;color:var(--muted);}
.cover .rule{width:16mm;height:.4pt;background:var(--accent);border:0;margin:8mm auto 0;}
.cover .loc{font-size:8pt;font-weight:500;text-transform:uppercase;letter-spacing:.2em;
  color:var(--muted);margin-top:7mm;}

.bar,.btn,.foot{display:none;}

.front{break-after:page;}
.glance{padding:5mm 6mm;margin:0 0 8mm;}
.glance .label{font-size:8pt;margin-bottom:2mm;display:block;}

.contents .label{font-size:8pt;margin-bottom:3mm;display:block;}
.contents li{padding:2.4mm 0;display:block;}
.contents .c-num{margin-right:4mm;}
.contents a{color:var(--ink);}
.contents a::after{content:leader('. ') target-counter(attr(href), page);
  color:var(--muted);font-variant-numeric:tabular-nums;}

.section{break-before:page;padding:0;border:0;}
.section .eyebrow{font-size:7.5pt;display:block;margin-bottom:2mm;}
.section .section-num{margin-right:2mm;}
.section-title{font-size:19pt;margin-bottom:5mm;}
.section h3{font-size:9.5pt;margin:5mm 0 1.5mm;text-transform:uppercase;letter-spacing:.04em;}
.admonition{padding:3mm 4mm;margin:4mm 0;break-inside:avoid;}
.admonition-title{margin-bottom:1mm;}
h2,h3{break-after:avoid;}
figure.fig{margin:5mm 0;text-align:center;break-inside:avoid;}
figure.fig img{max-width:78%;height:auto;}
figure.fig figcaption{font-size:8pt;color:var(--muted);margin-top:2mm;}
li{break-inside:avoid;}
"""


# ---------- HTML assembly ----------------------------------------------------

def glance_html(cfg, mode):
    rows = [("Hosts", cfg["host_name"]),
            ("Address", "{{address}}"),
            ("Message us", cfg["contact_primary"]),
            ("Urgent", "WhatsApp or call {{phone}}"),
            ("Emergency", cfg["emergency_number"]),
            ("Hospital", cfg["nearest_hospital"]),
            ("Pharmacy", cfg["nearest_pharmacy"])]
    body = "".join(
        f'<div class="row"><div class="k">{k}</div>'
        f'<div class="v">{apply_templates(str(v), cfg, mode)}</div></div>'
        for k, v in rows)
    return f'<section class="glance"><span class="label">At a glance</span>{body}</section>'


def contents_html(sections):
    items = "".join(f'<li><span class="c-num">{s["num"]}</span>'
                    f'<a href="#{s["id"]}">{s["title"]}</a></li>' for s in sections)
    return f'<nav class="contents"><span class="label">Contents</span><ol>{items}</ol></nav>'


def sections_html(sections, cfg, mode):
    out = []
    for s in sections:
        raw = apply_private_blocks(s["md"], cfg, mode)
        body = markdown.markdown(apply_templates(raw, cfg, mode), extensions=MD_EXT)
        out.append(
            f'<section class="section" id="{s["id"]}">'
            f'<span class="eyebrow"><span class="section-num">{s["num"]}</span></span>'
            f'<h2 class="section-title">{s["title"]}</h2>{body}</section>')
    return "\n".join(out)


def hero_inner(cfg):
    return (f'<span class="eyebrow">Guest guide</span>'
            f'<h1 class="place">{cfg["property_name"]}</h1>'
            f'<p class="tagline">{cfg["tagline"]}</p>'
            f'<hr class="rule"><p class="loc">{cfg["location_line"]}</p>')


def build_web(cfg, sections):
    css = font_faces(embed=True) + base_css(cfg) + web_css(cfg)
    logo = data_uri(BRAND / "logo-silver.png", "image/png")
    pdf_btn = ('<a class="btn" href="welcome-guide.pdf">Download PDF</a>'
               if cfg.get("publish_pdf") else '')
    masthead = (f'<header class="masthead">'
                f'<div class="bar"><div class="inner">'
                f'<img src="{logo}" alt="{cfg.get("company","")}">'
                f'{pdf_btn}</div></div>'
                f'<div class="hero">{hero_inner(cfg)}</div></header>')
    co = cfg.get("company", "")
    body = (masthead + '<main class="page">' + glance_html(cfg, "web")
            + contents_html(sections) + sections_html(sections, cfg, "web")
            + f'<p class="foot">{cfg["footer_note"]}<span class="co">{co}</span></p></main>')
    body = embed_images(body)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{cfg["property_name"]} — Guest guide</title>'
            f'<style>{css}</style></head><body>{body}</body></html>')


def build_print_html(cfg, sections):
    css = font_faces(embed=False) + base_css(cfg) + print_css(cfg)
    cover = (f'<header class="cover">'
             f'<div class="cover-content">'
             f'<img class="cover-logo" src="assets/brand/logo-silver.png" alt="">'
             f'<span class="eyebrow">Guest guide</span>'
             f'<h1 class="place">{cfg["property_name"]}</h1>'
             f'<p class="tagline">{cfg["tagline"]}</p>'
             f'<hr class="rule"><p class="loc">{cfg["location_line"]}</p>'
             f'</div></header>')
    front = '<div class="front">' + glance_html(cfg, "pdf") + contents_html(sections) + '</div>'
    body = cover + front + sections_html(sections, cfg, "pdf")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>{cfg["property_name"]}</title>'
            f'<style>{css}</style></head><body>{body}</body></html>')


# ---------- main -------------------------------------------------------------

def main():
    cfg = yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))
    secrets_file = ROOT / "secrets.local.yaml"
    if secrets_file.exists():
        cfg.update(yaml.safe_load(secrets_file.read_text(encoding="utf-8")) or {})
    sections = load_sections()
    DOCS.mkdir(exist_ok=True)

    (DOCS / "index.html").write_text(build_web(cfg, sections), encoding="utf-8")
    print(f"web : docs/index.html  ({len(sections)} sections)")

    publish_pdf = bool(cfg.get("publish_pdf"))
    pdf_dir = DOCS if publish_pdf else PRIVATE
    pdf_dir.mkdir(exist_ok=True)
    # never leave a private PDF sitting in the published folder
    stale = DOCS / "welcome-guide.pdf"
    if not publish_pdf and stale.exists():
        stale.unlink()
    pdf_path = pdf_dir / "welcome-guide.pdf"
    HTML(string=build_print_html(cfg, sections),
         base_url=str(ROOT)).write_pdf(pdf_path)
    print(f"pdf : {pdf_path.relative_to(ROOT)}" + ("" if publish_pdf else "  (private — not published)"))

    domain = (cfg.get("domain") or "").strip()
    cname_file = DOCS / "CNAME"
    if domain:
        cname_file.write_text(domain + "\n", encoding="utf-8")
        print(f"cname: {domain}")
    elif cname_file.exists():
        cname_file.unlink()
    print("done.")


if __name__ == "__main__":
    main()
