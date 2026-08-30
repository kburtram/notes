from __future__ import annotations

import os
import math
import html
from dataclasses import dataclass
from typing import Iterable, Sequence, Optional

W, H = 2400, 1350

# Palette from the source prompt
INK = "#18222D"
SLATE = "#4D5B6A"
VIOLET = "#6D5BD0"
DARK_VIOLET = "#4E3DA8"
PALE_VIOLET = "#F0EEFF"
TEAL = "#0C7C86"
DARK_TEAL = "#075D66"
MINT = "#E9F7F4"
PALE_TEAL = "#F3FBFA"
AMBER = "#A86500"
PALE_AMBER = "#FFF5DD"
BLUE = "#2D6CDF"
PALE_BLUE = "#EAF0F5"
GREEN = "#277A55"
PALE_GREEN = "#EAF7F0"
RED = "#A43842"
PALE_RED = "#FFF0F1"
WHITE = "#FFFFFF"
LIGHT = "#F8FAFC"
MID = "#C7D2DE"
DARK_MID = "#91A0AF"

FONT = "Lato, 'Noto Sans', Arial, sans-serif"
MONO = "'DejaVu Sans Mono', Consolas, monospace"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


@dataclass
class SVG:
    width: int = W
    height: int = H

    def __post_init__(self):
        self.parts: list[str] = []
        self.markers: dict[tuple[str, str], str] = {}
        self._marker_counter = 0
        self.parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">'
        )
        self.parts.append('<defs>')
        self.parts.append(
            '<style>'
            f'text{{font-family:{FONT};fill:{INK};}}'
            '.title{font-weight:900;letter-spacing:-0.4px;}'
            '.region{font-weight:800;}'
            '.cardtitle{font-weight:800;}'
            '.smallcaps{font-weight:800;letter-spacing:0.7px;}'
            '</style>'
        )
        self.parts.append('</defs>')
        # Opaque canvas background for PNG/PDF export.
        self.parts.append(f'<rect x="0" y="0" width="{self.width}" height="{self.height}" fill="{WHITE}"/>')

    def _insert_def(self, definition: str):
        # insert just before closing defs (the first occurrence)
        idx = self.parts.index('</defs>')
        self.parts.insert(idx, definition)

    def marker(self, color: str, kind: str = "arrow") -> str:
        key = (color, kind)
        if key in self.markers:
            return self.markers[key]
        self._marker_counter += 1
        mid = f"m{self._marker_counter}"
        if kind == "arrow":
            d = (
                f'<marker id="{mid}" markerWidth="12" markerHeight="12" refX="10" refY="5" '
                'orient="auto" markerUnits="strokeWidth">'
                f'<path d="M0,0 L10,5 L0,10 z" fill="{color}"/></marker>'
            )
        elif kind == "dot":
            d = (
                f'<marker id="{mid}" markerWidth="8" markerHeight="8" refX="4" refY="4" '
                'orient="auto" markerUnits="strokeWidth">'
                f'<circle cx="4" cy="4" r="3" fill="{color}"/></marker>'
            )
        else:
            raise ValueError(kind)
        self._insert_def(d)
        self.markers[key] = mid
        return mid

    def rect(self, x, y, w, h, fill=WHITE, stroke=MID, sw=2, rx=18, opacity=1.0, dash=None):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" fill-opacity="{opacity}" stroke="{stroke}" stroke-width="{sw}"{dash_attr}/>'
        )

    def line(self, x1, y1, x2, y2, color=SLATE, sw=3, dash=None, arrow=False, start_dot=False, opacity=1.0):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
        marker_end = f' marker-end="url(#{self.marker(color)})"' if arrow else ''
        marker_start = f' marker-start="url(#{self.marker(color, "dot")})"' if start_dot else ''
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{sw}" stroke-linecap="round" opacity="{opacity}"{dash_attr}{marker_end}{marker_start}/>'
        )

    def polyline(self, pts: Sequence[tuple[float, float]], color=SLATE, sw=3, dash=None, arrow=False, fill="none", opacity=1.0):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
        marker_end = f' marker-end="url(#{self.marker(color)})"' if arrow else ''
        p = " ".join(f"{x},{y}" for x, y in pts)
        self.parts.append(
            f'<polyline points="{p}" fill="{fill}" stroke="{color}" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}"{dash_attr}{marker_end}/>'
        )

    def path(self, d, fill="none", stroke=SLATE, sw=3, dash=None, arrow=False, opacity=1.0):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
        marker_end = f' marker-end="url(#{self.marker(stroke)})"' if arrow else ''
        self.parts.append(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}"{dash_attr}{marker_end}/>'
        )

    def circle(self, cx, cy, r, fill=WHITE, stroke=MID, sw=2):
        self.parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def text(self, x, y, lines: str | Sequence[str], size=24, color=INK, weight=400,
             anchor="start", line_h=None, family=None, cls=None, italic=False, opacity=1.0):
        if isinstance(lines, str):
            lines = [lines]
        line_h = line_h or size * 1.25
        family_attr = f' font-family="{family}"' if family else ''
        cls_attr = f' class="{cls}"' if cls else ''
        style = f'font-size:{size}px;font-weight:{weight};fill:{color};'
        if italic:
            style += 'font-style:italic;'
        self.parts.append(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" style="{style}" '
            f'opacity="{opacity}"{family_attr}{cls_attr}>'
        )
        for i, line in enumerate(lines):
            dy = 0 if i == 0 else line_h
            self.parts.append(f'<tspan x="{x}" dy="{dy}">{esc(line)}</tspan>')
        self.parts.append('</text>')

    def bullets(self, x, y, lines: Sequence[str], size=21, color=INK, bullet_color=None,
                line_h=None, gap_after=0, max_lines=None):
        line_h = line_h or size * 1.35
        bullet_color = bullet_color or color
        yy = y
        for idx, line in enumerate(lines[:max_lines] if max_lines else lines):
            self.circle(x + 5, yy - size * 0.27, 3.5, fill=bullet_color, stroke=bullet_color, sw=1)
            self.text(x + 18, yy, line, size=size, color=color, weight=450)
            yy += line_h + gap_after
        return yy

    def pill(self, x, y, w, h, label, fill=PALE_GREEN, stroke=GREEN, color=GREEN,
             size=18, icon=None, sw=2):
        self.rect(x, y, w, h, fill=fill, stroke=stroke, sw=sw, rx=h/2)
        tx = x + w/2
        if icon:
            self.text(x + 20, y + h/2 + size*0.34, icon, size=size+2, color=color, weight=900, anchor="middle")
            tx = x + w/2 + 8
        self.text(tx, y + h/2 + size*0.34, label, size=size, color=color, weight=800, anchor="middle")

    def card(self, x, y, w, h, title, fill=WHITE, stroke=MID, title_color=INK,
             title_size=24, body_lines: Optional[Sequence[str]] = None, body_size=20,
             body_color=SLATE, accent=None, dash=None, rx=18, top_pad=24, side_pad=24):
        self.rect(x, y, w, h, fill=fill, stroke=stroke, sw=2.5, rx=rx, dash=dash)
        if accent:
            self.rect(x, y, 10, h, fill=accent, stroke=accent, sw=0, rx=rx)
        self.text(x + side_pad + (4 if accent else 0), y + top_pad + title_size*0.72,
                  title, size=title_size, color=title_color, weight=850)
        if body_lines:
            self.bullets(x + side_pad + (4 if accent else 0), y + top_pad + title_size*1.65,
                         body_lines, size=body_size, color=body_color,
                         bullet_color=stroke, line_h=body_size*1.3)

    def region(self, x, y, w, h, title, stroke, fill=WHITE, title_fill=None, dash=None,
               title_size=26, inner_pad=18):
        self.rect(x, y, w, h, fill=fill, stroke=stroke, sw=3, rx=24, dash=dash)
        if title_fill:
            self.rect(x, y, w, 48, fill=title_fill, stroke=stroke, sw=0, rx=24)
            self.rect(x, y+24, w, 24, fill=title_fill, stroke=title_fill, sw=0, rx=0)
            self.text(x+inner_pad, y+34, title, size=title_size, color=stroke, weight=850)
        else:
            self.text(x+inner_pad, y-12, title, size=title_size, color=stroke, weight=850)

    def header(self, title, subtitle):
        self.text(70, 72, title, size=55, color=INK, weight=900, cls="title")
        self.text(72, 116, subtitle, size=23, color=SLATE, weight=500)
        self.line(70, 137, self.width-70, 137, color=MID, sw=2)

    def icon(self, kind, x, y, s=34, color=BLUE):
        # Simple, restrained line icons. x/y is top-left of nominal square.
        sw = max(2, s*0.08)
        if kind == "query":
            self.rect(x, y+4, s*0.62, s*0.78, fill="none", stroke=color, sw=sw, rx=3)
            self.line(x+s*0.12, y+s*0.28, x+s*0.46, y+s*0.28, color=color, sw=sw)
            self.line(x+s*0.12, y+s*0.45, x+s*0.46, y+s*0.45, color=color, sw=sw)
            self.path(f'M{x+s*0.68},{y+s*0.28} C{x+s*0.68},{y+s*0.15} {x+s*0.98},{y+s*0.15} {x+s*0.98},{y+s*0.28} '
                      f'L{x+s*0.98},{y+s*0.72} C{x+s*0.98},{y+s*0.85} {x+s*0.68},{y+s*0.85} {x+s*0.68},{y+s*0.72} Z',
                      fill="none", stroke=color, sw=sw)
        elif kind == "code":
            self.polyline([(x+s*0.38,y+s*0.18),(x+s*0.12,y+s*0.5),(x+s*0.38,y+s*0.82)], color=color, sw=sw)
            self.polyline([(x+s*0.62,y+s*0.18),(x+s*0.88,y+s*0.5),(x+s*0.62,y+s*0.82)], color=color, sw=sw)
            self.line(x+s*0.56,y+s*0.12,x+s*0.44,y+s*0.88,color=color,sw=sw)
        elif kind == "spark":
            self.path(f'M{x+s*0.5},{y} L{x+s*0.6},{y+s*0.38} L{x+s},{y+s*0.5} '
                      f'L{x+s*0.6},{y+s*0.62} L{x+s*0.5},{y+s} L{x+s*0.4},{y+s*0.62} '
                      f'L{x},{y+s*0.5} L{x+s*0.4},{y+s*0.38} Z', fill=color, stroke=color, sw=1)
        elif kind == "tree":
            self.circle(x+s*0.5,y+s*0.15,s*0.1,fill=WHITE,stroke=color,sw=sw)
            self.circle(x+s*0.2,y+s*0.8,s*0.1,fill=WHITE,stroke=color,sw=sw)
            self.circle(x+s*0.5,y+s*0.8,s*0.1,fill=WHITE,stroke=color,sw=sw)
            self.circle(x+s*0.8,y+s*0.8,s*0.1,fill=WHITE,stroke=color,sw=sw)
            self.line(x+s*0.5,y+s*0.25,x+s*0.5,y+s*0.56,color=color,sw=sw)
            self.line(x+s*0.2,y+s*0.56,x+s*0.8,y+s*0.56,color=color,sw=sw)
            self.line(x+s*0.2,y+s*0.56,x+s*0.2,y+s*0.7,color=color,sw=sw)
            self.line(x+s*0.5,y+s*0.56,x+s*0.5,y+s*0.7,color=color,sw=sw)
            self.line(x+s*0.8,y+s*0.56,x+s*0.8,y+s*0.7,color=color,sw=sw)
        elif kind == "doc":
            self.path(f'M{x+s*0.2},{y+s*0.05} L{x+s*0.65},{y+s*0.05} L{x+s*0.85},{y+s*0.25} '
                      f'L{x+s*0.85},{y+s*0.95} L{x+s*0.2},{y+s*0.95} Z', fill="none", stroke=color, sw=sw)
            self.line(x+s*0.65,y+s*0.05,x+s*0.65,y+s*0.28,color=color,sw=sw)
            self.line(x+s*0.65,y+s*0.28,x+s*0.85,y+s*0.28,color=color,sw=sw)
            self.line(x+s*0.32,y+s*0.46,x+s*0.72,y+s*0.46,color=color,sw=sw)
            self.line(x+s*0.32,y+s*0.64,x+s*0.72,y+s*0.64,color=color,sw=sw)
        elif kind == "graph":
            pts=[(x+s*0.2,y+s*0.72),(x+s*0.5,y+s*0.2),(x+s*0.82,y+s*0.68)]
            self.line(*pts[0],*pts[1],color=color,sw=sw)
            self.line(*pts[1],*pts[2],color=color,sw=sw)
            self.line(*pts[0],*pts[2],color=color,sw=sw)
            for px,py in pts:
                self.circle(px,py,s*0.11,fill=WHITE,stroke=color,sw=sw)
        elif kind == "db":
            self.path(f'M{x+s*0.1},{y+s*0.25} C{x+s*0.1},{y+s*0.08} {x+s*0.9},{y+s*0.08} {x+s*0.9},{y+s*0.25} '
                      f'L{x+s*0.9},{y+s*0.75} C{x+s*0.9},{y+s*0.92} {x+s*0.1},{y+s*0.92} {x+s*0.1},{y+s*0.75} Z',
                      fill="none", stroke=color, sw=sw)
            self.path(f'M{x+s*0.1},{y+s*0.25} C{x+s*0.1},{y+s*0.42} {x+s*0.9},{y+s*0.42} {x+s*0.9},{y+s*0.25}',
                      fill="none", stroke=color, sw=sw)
            self.path(f'M{x+s*0.1},{y+s*0.5} C{x+s*0.1},{y+s*0.67} {x+s*0.9},{y+s*0.67} {x+s*0.9},{y+s*0.5}',
                      fill="none", stroke=color, sw=sw)
        elif kind == "lock":
            self.rect(x+s*0.18,y+s*0.44,s*0.64,s*0.48,fill="none",stroke=color,sw=sw,rx=4)
            self.path(f'M{x+s*0.32},{y+s*0.44} L{x+s*0.32},{y+s*0.3} C{x+s*0.32},{y+s*0.03} {x+s*0.68},{y+s*0.03} {x+s*0.68},{y+s*0.3} L{x+s*0.68},{y+s*0.44}',
                      fill="none",stroke=color,sw=sw)
        elif kind == "server":
            self.rect(x+s*0.08,y+s*0.12,s*0.84,s*0.28,fill="none",stroke=color,sw=sw,rx=4)
            self.rect(x+s*0.08,y+s*0.55,s*0.84,s*0.28,fill="none",stroke=color,sw=sw,rx=4)
            self.circle(x+s*0.22,y+s*0.26,s*0.035,fill=color,stroke=color,sw=1)
            self.circle(x+s*0.22,y+s*0.69,s*0.035,fill=color,stroke=color,sw=1)
        else:
            self.circle(x+s/2,y+s/2,s*0.45,fill="none",stroke=color,sw=sw)

    def finish(self, path):
        self.parts.append('</svg>')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.parts))


def consumer_card(svg: SVG, x, y, w, title, icon, lines, scope="downstream"):
    h = 185
    svg.rect(x, y, w, h, fill=WHITE, stroke=BLUE, sw=2.5, rx=18)
    svg.icon(icon, x+20, y+23, s=38, color=BLUE)
    svg.text(x+70, y+48, title, size=23, color=DARK_VIOLET, weight=850)
    svg.bullets(x+26, y+87, lines, size=18.5, color=INK, bullet_color=BLUE, line_h=25)
    if scope:
        svg.text(x+w-18, y+h-14, scope, size=14, color=DARK_MID, weight=700, anchor="end", italic=True)


def draw_overview(outdir: str):
    s = SVG()
    s.header(
        "Shared Metadata Substrate: Architecture and Consumer Flow",
        "Composite view: PR #22836 substrate below; downstream dev/refactor consumers above (not cut over by this PR).",
    )

    # Top consumer area
    s.region(60, 165, 2280, 286, "Consumers - leases and pinned views only", stroke=BLUE, fill="#FBFDFF", title_fill="#EEF5FF")
    gap = 18
    cw = (2280 - 2*22 - 5*gap)/6
    xs = [82 + i*(cw+gap) for i in range(6)]
    consumer_card(s, xs[0], 222, cw, "Query Studio", "query", [
        "database binding + lease",
        "successful DDL -> notify",
        "shares one pinned generation",
    ])
    consumer_card(s, xs[1], 222, cw, "Native T-SQL", "code", [
        "IPinnedMetadataView",
        "pin once; synchronous reads",
        "no network on keystroke path",
    ])
    consumer_card(s, xs[2], 222, cw, "AI completions", "spark", [
        "allowStale schema context",
        "bounded + deterministic",
        "cache keyed by generation",
    ])
    consumer_card(s, xs[3], 222, cw, "Object Explorer v2", "tree", [
        "server + lazy DB leases",
        "requireValidated browse",
        "unavailable is not empty",
    ])
    consumer_card(s, xs[4], 222, cw, "Scripting", "doc", [
        "requireLive for fidelity",
        "explicit offline path only",
        "one pinned view",
    ])
    consumer_card(s, xs[5], 222, cw, "Schema visualizer", "graph", [
        "lease -> one snapshot",
        "snapshot -> graph model",
        "no ad-hoc catalog SQL",
    ])

    # Interface seams
    s.rect(120, 418, 980, 42, fill=PALE_VIOLET, stroke=VIOLET, sw=2, rx=13)
    s.text(610, 446, "Language-provider seam  |  ISqlLanguageMetadataProvider / IPinnedMetadataView",
           size=18, color=DARK_VIOLET, weight=800, anchor="middle")
    s.rect(1215, 418, 1045, 42, fill=PALE_VIOLET, stroke=VIOLET, sw=2, rx=13)
    s.text(1738, 446, "Lease surface  |  ServerCatalogLease / DatabaseCatalogLease",
           size=18, color=DARK_VIOLET, weight=800, anchor="middle")

    # Main panels
    store_x, store_y, store_w, store_h = 70, 505, 650, 675
    snap_x, snap_y, snap_w, snap_h = 765, 505, 715, 675
    live_x, live_y, live_w, live_h = 1525, 505, 805, 315
    disk_x, disk_y, disk_w, disk_h = 1525, 865, 805, 315

    s.region(store_x, store_y, store_w, store_h, "Extension-host ownership and policy", stroke=VIOLET, fill="#FCFBFF", title_fill=PALE_VIOLET)
    s.icon("server", store_x+24, store_y+73, s=46, color=DARK_VIOLET)
    s.text(store_x+83, store_y+102, "MetadataStoreService / MetadataStore", size=27, color=DARK_VIOLET, weight=900)
    s.text(store_x+83, store_y+132, "one per extension host", size=18, color=SLATE, weight=600)

    s.card(store_x+24, store_y+160, 288, 142, "Server map", fill=WHITE, stroke=VIOLET,
           title_color=DARK_VIOLET, title_size=21, body_lines=[
               "sfp_* key",
               "ServerMetadataService",
               "lazy server auxiliary",
           ], body_size=17.5, top_pad=18, side_pad=18)
    s.card(store_x+332, store_y+160, 294, 142, "Database map", fill=WHITE, stroke=VIOLET,
           title_color=DARK_VIOLET, title_size=21, body_lines=[
               "sfp_* + exact DB spelling",
               "MetadataService + main source",
               "separate auxiliary source",
           ], body_size=17.5, top_pad=18, side_pad=18)

    s.text(store_x+30, store_y+338, "Lifecycle and safety", size=21, color=DARK_VIOLET, weight=850)
    s.bullets(store_x+31, store_y+374, [
        "same-key first acquire is single-flight",
        "ref-counted leases; bounded warm idle TTL + LRU",
        "deferred credentials and lazy provider resolution",
        "dynamic network-authorization gate",
        "H0 identity proof before H1 or cache publication",
    ], size=18.5, color=INK, bullet_color=VIOLET, line_h=27)

    s.rect(store_x+24, store_y+526, 602, 124, fill=WHITE, stroke=VIOLET, sw=2, rx=16)
    s.text(store_x+44, store_y+556, "ensureFresh(policy)", size=21, color=DARK_VIOLET, weight=900)
    segs = [
        ("allowStale", "serve now; refresh async"),
        ("requireValidated", "TTL or coalesced digest"),
        ("requireLive", "full refresh or unavailable"),
        ("offlineSnapshot", "zero live work"),
    ]
    swid = 139
    for i,(a,b) in enumerate(segs):
        xx=store_x+36+i*146
        fill = PALE_GREEN if i==0 else (PALE_BLUE if i==1 else (PALE_RED if i==2 else PALE_AMBER))
        stroke = GREEN if i==0 else (BLUE if i==1 else (RED if i==2 else AMBER))
        s.rect(xx, store_y+574, swid, 58, fill=fill, stroke=stroke, sw=1.8, rx=10)
        s.text(xx+swid/2, store_y+595, a, size=16, color=stroke, weight=850, anchor="middle")
        s.text(xx+swid/2, store_y+618, b, size=12.5, color=INK, weight=600, anchor="middle")

    # Snapshot panel
    s.region(snap_x, snap_y, snap_w, snap_h, "Shared immutable catalog", stroke=TEAL, fill="#FBFEFD", title_fill=MINT)
    # Older generation tabs behind the current snapshot card.
    for dx, lab, op in [(94,"N-3",0.42),(64,"N-2",0.58),(34,"N-1",0.76)]:
        s.rect(snap_x+snap_w-155-dx, snap_y+81+dx*0.35, 138, 505-dx*0.2,
               fill=WHITE, stroke=TEAL, sw=2, rx=14, opacity=op)
        s.text(snap_x+snap_w-60-dx, snap_y+119+dx*0.35, lab, size=17, color=TEAL, weight=900, anchor="middle")
    s.rect(snap_x+28, snap_y+75, 520, 538, fill=WHITE, stroke=TEAL, sw=3, rx=18)
    s.icon("db", snap_x+50, snap_y+94, s=42, color=TEAL)
    s.text(snap_x+105, snap_y+126, "CatalogSnapshot - immutable generation N", size=23, color=DARK_TEAL, weight=900)
    s.pill(snap_x+52, snap_y+150, 235, 38, "PIN ONCE PER RESPONSE", fill=PALE_GREEN, stroke=GREEN, color=GREEN, size=15)
    s.pill(snap_x+301, snap_y+150, 220, 38, "ATOMIC REPLACEMENT", fill=MINT, stroke=TEAL, color=TEAL, size=15)

    s.text(snap_x+55, snap_y+225, "Header / truth", size=20, color=DARK_TEAL, weight=850)
    s.bullets(snap_x+57, snap_y+258, [
        "generation, capturedAtUtc, optional contentHash",
        "mode: full | partial | lite",
        "per-section readiness: absent/loading/ready/failed/stale/lite",
        "readiness/completeness is separate from freshness/age",
    ], size=17.3, color=INK, bullet_color=TEAL, line_h=25)

    s.text(snap_x+55, snap_y+385, "Shared storage + read-only indexes", size=20, color=DARK_TEAL, weight=850)
    s.bullets(snap_x+57, snap_y+418, [
        "interned structure-of-arrays storage",
        "object ID, folded-name, schema-name indexes",
        "column/parameter ranges; key/FK/description maps",
    ], size=17.3, color=INK, bullet_color=TEAL, line_h=25)

    s.text(snap_x+55, snap_y+520, "Pure synchronous reads", size=20, color=DARK_TEAL, weight=850)
    s.text(snap_x+57, snap_y+553, [
        "resolveName  |  search  |  listSchemas/listObjects",
        "getColumns  |  getKeys  |  getFKs  |  getParameters",
        "build bounded deterministic schema context",
    ], size=17.3, color=INK, weight=650, line_h=25)
    s.text(snap_x+575, snap_y+490, ["older generations", "remain valid", "for holders"], size=17, color=DARK_TEAL, weight=800, anchor="middle", line_h=22)

    # Live panel
    s.region(live_x, live_y, live_w, live_h, "Live hydration and drift", stroke=BLUE, fill="#FBFDFF", title_fill="#EEF5FF")
    labels = [
        (["LazyMetadata", "Connection"], 160),
        (["SQL Data Plane"], 145),
        (["STS2 local", "backend"], 155),
        (["SQL Server", "sys.* catalogs"], 165),
    ]
    xx=live_x+24
    centers=[]
    for label_lines, ww in labels:
        s.rect(xx, live_y+82, ww, 68, fill=WHITE, stroke=BLUE, sw=2, rx=13)
        if len(label_lines) == 1:
            s.text(xx+ww/2, live_y+122, label_lines, size=15.5, color=INK, weight=800, anchor="middle")
        else:
            s.text(xx+ww/2, live_y+108, label_lines, size=14.5, color=INK, weight=800, anchor="middle", line_h=19)
        centers.append((xx+ww/2, live_y+116, ww))
        xx += ww+26
    for i in range(len(centers)-1):
        s.line(centers[i][0]+centers[i][2]/2-12, live_y+116, centers[i+1][0]-centers[i+1][2]/2+12, live_y+116,
               color=BLUE, sw=3, arrow=True)
    s.text(live_x+402, live_y+177, "v2/connection.open; v2/query.execute -> row pages + query.complete", size=15.5, color=SLATE, weight=650, anchor="middle")
    s.pill(live_x+560, live_y+60, 205, 34, "ONE ACTIVE QUERY / CONNECTION", fill=PALE_AMBER, stroke=AMBER, color=AMBER, size=13.5)
    # H ladder
    steps=["H0 identity", "H1 schemas", "H2 objects", "H3 columns", "H4 PK/UQ", "H5 FKs", "H6 params", "H7 desc"]
    xx=live_x+27
    for i,lab in enumerate(steps):
        ww=88 if i not in (2,3) else 94
        fill=PALE_GREEN if i==0 else PALE_TEAL
        stroke=GREEN if i==0 else TEAL
        s.rect(xx, live_y+218, ww, 48, fill=fill, stroke=stroke, sw=1.8, rx=9)
        s.text(xx+ww/2, live_y+248, lab, size=14.5, color=stroke, weight=800, anchor="middle")
        if i < len(steps)-1:
            s.line(xx+ww, live_y+242, xx+ww+12, live_y+242, color=TEAL, sw=2, arrow=True)
        xx += ww+15
    s.text(live_x+28, live_y+289, [
        "DDL notify + T1 digest + explicit policy -> one coalesced refresh.",
        "Identity drift or timeout fences the epoch and recycles the source.",
    ], size=14.8, color=INK, weight=650, line_h=20)

    # Persistence panel
    s.region(disk_x, disk_y, disk_w, disk_h, "Optional persistent database cache - not authority", stroke=AMBER, fill="#FFFEFA", title_fill=PALE_AMBER)
    s.icon("lock", disk_x+25, disk_y+73, s=40, color=AMBER)
    s.text(disk_x+82, disk_y+102, "globalStorage/metadata-cache/v1/", size=19, color=AMBER, weight=850, family=MONO)
    s.text(disk_x+82, disk_y+132, "manifest.json + content-addressed catalog.<sha>.json.gz", size=16.5, color=INK, weight=650, family=MONO)
    s.text(disk_x+28, disk_y+177, "Verified read", size=18, color=AMBER, weight=850)
    s.text(disk_x+150, disk_y+171, [
        "manifest + key binding + size/SHA/gunzip + shape/hash",
        "policy intersection -> rehydrate with original age/generation",
    ], size=14.1, color=INK, weight=620, line_h=19)
    s.text(disk_x+28, disk_y+226, "Atomic write", size=18, color=AMBER, weight=850)
    s.text(disk_x+150, disk_y+220, [
        "debounce + canonical/privacy projection + gzip/SHA + authority lock",
        "payload atomic -> manifest LAST",
    ], size=14.1, color=INK, weight=620, line_h=19)
    s.pill(disk_x+28, disk_y+252, 232, 38, "SAFE MISS ON FAILED PROOF", fill=PALE_RED, stroke=RED, color=RED, size=14)
    s.pill(disk_x+276, disk_y+252, 218, 38, "CAPTURE TIME + HASH", fill=PALE_AMBER, stroke=AMBER, color=AMBER, size=14)
    s.pill(disk_x+510, disk_y+252, 266, 38, "SERVER/AUXILIARY STAY LIVE", fill=PALE_BLUE, stroke=BLUE, color=BLUE, size=14)

    # Arrows between panels
    # Seams into store
    s.polyline([(610,460),(610,482),(395,482),(395,505)], color=VIOLET, sw=4, arrow=True)
    s.polyline([(1738,460),(1738,480),(600,480),(600,505)], color=VIOLET, sw=4, arrow=True)
    # Store to snapshot
    s.line(store_x+store_w, store_y+320, snap_x, snap_y+320, color=VIOLET, sw=5, arrow=True)
    s.text((store_x+store_w+snap_x)/2, store_y+302, "leases / pinned views", size=16, color=DARK_VIOLET, weight=800, anchor="middle")
    # Live to snapshot
    s.polyline([(live_x,live_y+200),(1500,live_y+200),(1500,snap_y+395),(snap_x+snap_w,snap_y+395)], color=TEAL, sw=5, arrow=True)
    s.text(1510, snap_y+374, "H0-H7 rows -> atomic publish", size=15, color=DARK_TEAL, weight=800, anchor="end")
    # Snapshot/cache bidirectional
    s.polyline([(snap_x+snap_w,snap_y+545),(1502,snap_y+545),(1502,disk_y+110),(disk_x,disk_y+110)], color=AMBER, sw=4, arrow=True)
    s.text(1500, disk_y+95, "debounced save", size=15, color=AMBER, weight=800, anchor="end")
    s.polyline([(disk_x,disk_y+165),(1498,disk_y+165),(1498,snap_y+585),(snap_x+snap_w,snap_y+585)], color=AMBER, sw=4, dash="12 10", arrow=True)
    s.text(1500, snap_y+610, "verified load / rehydrate", size=15, color=AMBER, weight=800, anchor="end")
    # Legend and invariant footer
    s.rect(70, 1210, 2260, 86, fill=WHITE, stroke=MID, sw=2, rx=18)
    pills = [
        ("PIN ONCE PER RESPONSE", PALE_GREEN, GREEN, 430),
        ("FAILURE IS NEVER EMPTINESS", PALE_RED, RED, 470),
        ("NO NETWORK ON THE KEYSTROKE PATH", PALE_GREEN, GREEN, 550),
        ("MANIFEST LAST; CACHE IS NOT AUTHORITY", PALE_AMBER, AMBER, 610),
    ]
    xx=92
    for label,fill,stroke,ww in pills:
        s.pill(xx, 1229, ww, 48, label, fill=fill, stroke=stroke, color=stroke, size=17)
        xx += ww+18
    s.finish(os.path.join(outdir, "01_metadata_cache_architecture_overview.svg"))


def draw_layout(outdir: str):
    s=SVG()
    s.header(
        "Immutable Catalog Data Layout",
        "SQL catalog row pages are accumulated in a private structure-of-arrays builder, then published as one immutable generation.",
    )

    # incoming ladder
    s.region(60, 170, 395, 1095, "Live row pages", stroke=BLUE, fill="#FBFDFF", title_fill="#EEF5FF")
    s.text(84, 235, "Dedicated main DB session", size=22, color=BLUE, weight=900)
    s.text(84, 267, "serial H0-H7; one active query", size=17.5, color=SLATE, weight=650)
    steps=[
        ("H0", ["environment + authoritative", "database identity"], GREEN, PALE_GREEN),
        ("H1", ["schemas"], TEAL, MINT),
        ("H2", ["objects + synonyms"], TEAL, MINT),
        ("H3", ["columns + exact type/default/", "identity/computed facts"], TEAL, MINT),
        ("H4", ["primary + unique keys"], TEAL, MINT),
        ("H5/H5B", ["foreign keys + ordered", "column pairs"], TEAL, MINT),
        ("H6", ["parameters"], TEAL, MINT),
        ("H7", ["descriptions"], TEAL, MINT),
    ]
    yy=310
    for i,(code,lines,stroke,fill) in enumerate(steps):
        h=84 if len(lines)>1 else 72
        s.rect(83, yy, 350, h, fill=fill, stroke=stroke, sw=2, rx=14)
        code_size = 17 if code == "H5/H5B" else 20
        desc_x = 205 if code == "H5/H5B" else 176
        s.text(105, yy+31, code, size=code_size, color=stroke, weight=900)
        s.text(desc_x, yy+31, lines, size=15.7, color=INK, weight=650, line_h=21)
        if i < len(steps)-1:
            s.line(258, yy+h, 258, yy+h+17, color=TEAL, sw=3, arrow=True)
        yy += h+22
    s.pill(84, 1138, 350, 48, "H0 GATES EVERY LATER PUBLICATION", fill=PALE_GREEN, stroke=GREEN, color=GREEN, size=15.5)
    s.pill(84, 1200, 350, 48, "H3-H7 FAILURE -> FAILED/PARTIAL", fill=PALE_RED, stroke=RED, color=RED, size=15.5)

    # Builder area
    bx,by,bw,bh=500,170,1030,1095
    s.region(bx,by,bw,bh,"CatalogBuilder - private, mutable during hydration",stroke=TEAL,fill="#FBFEFD",title_fill=MINT)
    s.pill(bx+770, by+66, 225, 40, "NOT VISIBLE TO READERS", fill=PALE_RED, stroke=RED, color=RED, size=14.5)

    # intern table
    s.rect(bx+28,by+76,610,160,fill=WHITE,stroke=TEAL,sw=2.5,rx=16)
    s.text(bx+50,by+108,"strings[] - one intern table",size=22,color=DARK_TEAL,weight=900)
    # cells
    vals=["dbo","Users","int","CreatedAt","nvarchar"]
    xx=bx+50
    widths=[82,112,74,142,130]
    for i,(v,ww) in enumerate(zip(vals,widths)):
        s.rect(xx,by+130,ww,54,fill=PALE_TEAL,stroke=TEAL,sw=1.6,rx=8)
        s.text(xx+ww/2,by+152,str(i),size=12,color=SLATE,weight=700,anchor="middle")
        s.text(xx+ww/2,by+174,v,size=15.5,color=INK,weight=750,anchor="middle",family=MONO)
        xx+=ww+10
    s.text(bx+50,by+215,"Every *Sym column stores an integer into this table.",size=16.5,color=SLATE,weight=650)

    s.rect(bx+665,by+76,337,160,fill=WHITE,stroke=TEAL,sw=2.5,rx=16)
    s.text(bx+690,by+108,"Build-time indexes",size=22,color=DARK_TEAL,weight=900)
    s.text(bx+690,by+142,[
        "stringIndex: string -> sym",
        "objectIndexById: objectId -> row",
        "foreignKeyConstraintIds: Set",
    ],size=15.2,color=INK,weight=650,line_h=21,family=MONO)
    s.pill(bx+690,by+199,280,30,"O(1) dependent-row attachment",fill=PALE_GREEN,stroke=GREEN,color=GREEN,size=12.5)

    s.text(bx+32,by+282,"Parallel structure-of-arrays tables",size=23,color=DARK_TEAL,weight=900)
    s.text(bx+440,by+282,"owner indexes join dependent rows; no per-item heap-object tree",size=16.5,color=SLATE,weight=650)

    # Table cards grid 3x3-ish
    cards=[
        ("Schemas", ["schemaIds[]", "schemaNameSyms[]"]),
        ("Objects", ["objectIds[]", "objectSchemaIds[]", "objectNameSyms[]", "objectKinds[]", "modifyDates[]"]),
        ("Columns", ["columnOwner[]", "columnNameSyms[]", "columnTypeSyms[]", "nullable/identity/computed[]", "+ exact detail arrays"]),
        ("Keys", ["keyConstraintOwner[]", "constraintNameSyms[]", "kind[]", "ordered columnSyms[]"]),
        ("Foreign keys", ["fkFrom[] / fkTo[]", "fkNameSyms[]", "constraintIds[]", "delete/update actions[]"]),
        ("FK pairs", ["constraintIds[]", "ordinals[]", "from/to columnSyms[]", "from/to columnIds[]"]),
        ("Parameters", ["paramOwner[]", "ordinals[]", "name/typeSyms[]", "output[]"]),
        ("Descriptions", ["descriptionOwner[]", "optional columnSym[]", "valueSym[]", "live-only by current policy"]),
        ("Environment", ["engineEdition", "defaultSchema", "collationName", "caseSensitive / unknown"]),
    ]
    grid_x=bx+28; grid_y=by+310
    col_w=314; row_h=205; gx=16; gy=18
    for idx,(title,lines) in enumerate(cards):
        r=idx//3; c=idx%3
        x=grid_x+c*(col_w+gx); y=grid_y+r*(row_h+gy)
        fill=WHITE if title!="Environment" else PALE_BLUE
        stroke=TEAL if title!="Environment" else BLUE
        s.rect(x,y,col_w,row_h,fill=fill,stroke=stroke,sw=2,rx=14)
        s.text(x+18,y+32,title,size=19.5,color=DARK_TEAL if stroke==TEAL else BLUE,weight=900)
        s.text(x+18,y+66,lines,size=15.8,color=INK,weight=650,line_h=25,family=MONO)
        # small owner/index visual in selected cards
        if title in ("Columns","Parameters","Descriptions"):
            s.pill(x+18,y+162,col_w-36,29,"owner[] -> object table row",fill=PALE_VIOLET,stroke=VIOLET,color=DARK_VIOLET,size=12.8)

    # pointer lines from sym tables to intern table
    targets=[
        (grid_x+col_w*0.5,grid_y),
        (grid_x+(col_w+gx)+col_w*0.5,grid_y),
        (grid_x+2*(col_w+gx)+col_w*0.5,grid_y),
        (grid_x+2*(col_w+gx)+col_w*0.5,grid_y+row_h+gy),
        (grid_x+(col_w+gx)+col_w*0.5,grid_y+2*(row_h+gy)),
    ]
    for tx,ty in targets:
        s.polyline([(bx+330,by+236),(bx+330,by+260),(tx,by+260),(tx,ty)],color=TEAL,sw=1.8,dash="7 7",arrow=True,opacity=0.75)

    # Ingestion arrows from left to builder
    for y in [400,560,740,930]:
        s.line(455,y,500,y,color=TEAL,sw=4,arrow=True)
    s.text(477,376,"typed compact rows",size=14.5,color=DARK_TEAL,weight=800,anchor="middle")

    # Build arrow
    s.rect(1548,566,142,130,fill=PALE_TEAL,stroke=TEAL,sw=2.5,rx=18)
    s.text(1619,601,["build(N+1,", "readiness,", "mode)"],size=15.2,color=DARK_TEAL,weight=850,anchor="middle",line_h=23,family=MONO)
    s.line(1530,631,1548,631,color=TEAL,sw=5,arrow=True)
    s.line(1690,631,1710,631,color=TEAL,sw=5,arrow=True)
    s.pill(1539,714,160,42,"ATOMIC FULL REPLACE",fill=PALE_GREEN,stroke=GREEN,color=GREEN,size=13)

    # Snapshot area
    sx,sy,swid,sh=1710,170,630,1095
    s.region(sx,sy,swid,sh,"CatalogSnapshot - immutable generation N",stroke=TEAL,fill="#FBFEFD",title_fill=MINT,title_size=24)
    # Older generation tabs; the front card itself is generation N.
    for dx,lab,op in [(94,"N-3",0.4),(66,"N-2",0.56),(38,"N-1",0.72)]:
        s.rect(sx+swid-172-dx,sy+84+dx*0.42,140,540-dx*0.4,fill=WHITE,stroke=TEAL,sw=2,rx=14,opacity=op)
        s.text(sx+swid-102-dx,sy+119+dx*0.42,lab,size=17,color=TEAL,weight=900,anchor="middle")
    s.rect(sx+28,sy+84,420,560,fill=WHITE,stroke=TEAL,sw=3,rx=18)
    s.text(sx+49,sy+120,"A. Header / truth",size=21,color=DARK_TEAL,weight=900)
    s.text(sx+50,sy+156,[
        "generation + capturedAtUtc",
        "optional contentHash",
        "mode: full | partial | lite",
        "section state: absent/loading/",
        "ready/failed/stale/lite",
    ],size=16.2,color=INK,weight=650,line_h=24)
    s.pill(sx+50,sy+276,375,42,"READINESS != FRESHNESS / AGE",fill=PALE_AMBER,stroke=AMBER,color=AMBER,size=14)
    s.text(sx+49,sy+350,"B. Shared SoA + read-only indexes",size=21,color=DARK_TEAL,weight=900)
    s.text(sx+50,sy+386,[
        "same interned arrays",
        "objectId -> object row",
        "folded-name prefix index",
        "schemaId -> schema name",
        "column/parameter [start,end) ranges",
        "PK/UQ, FK-pair, degree, description maps",
    ],size=15.7,color=INK,weight=650,line_h=23)
    s.text(sx+49,sy+532,"C. Pure synchronous APIs",size=21,color=DARK_TEAL,weight=900)
    s.text(sx+50,sy+567,[
        "resolveName / search / list",
        "getColumns / getKeys / getFKs",
        "getParameters / bounded context",
    ],size=15.7,color=INK,weight=650,line_h=23,family=MONO)

    s.text(sx+500,sy+430,["older", "generations", "remain valid", "for holders"],size=17,color=DARK_TEAL,weight=850,anchor="middle",line_h=23)

    # pin/consumer section
    s.rect(sx+28,sy+646,574,170,fill=PALE_VIOLET,stroke=VIOLET,sw=2.5,rx=16)
    s.text(sx+52,sy+684,"Pinned reader contract",size=22,color=DARK_VIOLET,weight=900)
    s.bullets(sx+53,sy+722,[
        "pin one generation for the whole response",
        "never mix N and N+1 during one operation",
        "read methods perform no I/O and no mutation",
    ],size=17,color=INK,bullet_color=VIOLET,line_h=25)

    s.rect(sx+28,sy+846,574,155,fill=WHITE,stroke=BLUE,sw=2.5,rx=16)
    s.icon("doc",sx+49,sy+880,s=40,color=BLUE)
    s.text(sx+105,sy+905,"Lazy module definitions",size=21,color=BLUE,weight=900)
    s.text(sx+50,sy+943,[
        "sys.sql_modules on explicit resolve",
        "cached only for the current generation",
        "never included in the persistent payload",
    ],size=16.2,color=INK,weight=650,line_h=24)

    s.pill(sx+28,sy+1030,276,48,"INTERNED + COMPACT",fill=MINT,stroke=TEAL,color=TEAL,size=15.5)
    s.pill(sx+326,sy+1030,276,48,"CONSISTENT + IMMUTABLE",fill=PALE_GREEN,stroke=GREEN,color=GREEN,size=15.5)

    # Footer invariant strip
    s.rect(60,1280,2280,44,fill=WHITE,stroke=MID,sw=1.5,rx=14)
    s.text(1200,1308,"Private mutable build  ->  atomic CatalogSnapshot  ->  pinned generation  ->  synchronous consumer reads",
           size=18,color=SLATE,weight=800,anchor="middle")
    s.finish(os.path.join(outdir,"02_metadata_catalog_data_layout.svg"))


def draw_lifecycle(outdir: str):
    s=SVG()
    s.header(
        "Metadata Acquisition, Freshness, and Drift",
        "Cache-first acquisition and live refresh share one rule: return the best snapshot with an explicit truth label, never an empty lie.",
    )

    # Acquisition path
    s.region(60,170,1050,470,"Acquire a database lease",stroke=VIOLET,fill="#FCFBFF",title_fill=PALE_VIOLET)
    # flow boxes
    boxes=[
        (95,260,190,98,"Acquire key",["sfp_* + DB spelling","prepared auth closures"],VIOLET,PALE_VIOLET),
        (335,260,205,98,"Load cache",["verify key, bytes,","shape, hash, policy"],AMBER,PALE_AMBER),
        (590,260,205,98,"Network allowed?",["dynamic host policy","rechecked on every path"],BLUE,PALE_BLUE),
        (845,260,220,98,"Resolve live source",["hydrate / validate / poll","definitions / auxiliary"],BLUE,PALE_BLUE),
    ]
    for x,y,w,h,t,lines,stroke,fill in boxes:
        s.rect(x,y,w,h,fill=fill,stroke=stroke,sw=2.5,rx=16)
        s.text(x+w/2,y+32,t,size=19.5,color=stroke,weight=900,anchor="middle")
        s.text(x+w/2,y+61,lines,size=14.5,color=INK,weight=650,anchor="middle",line_h=20)
    for a,b in [(boxes[0],boxes[1]),(boxes[1],boxes[2]),(boxes[2],boxes[3])]:
        s.line(a[0]+a[2],309,b[0],309,color=VIOLET if b==boxes[1] else BLUE,sw=4,arrow=True)

    # cache hit branch
    s.polyline([(437,358),(437,405),(300,405),(300,500)],color=AMBER,sw=3,dash="10 8",arrow=True)
    s.rect(115,500,370,95,fill=PALE_GREEN,stroke=GREEN,sw=2.5,rx=16)
    s.text(300,530,"Verified disk hit",size=20,color=GREEN,weight=900,anchor="middle")
    s.text(300,558,["publish immediately", "preserve original capture age + generation"],size=15.5,color=INK,weight=650,anchor="middle",line_h=21)
    # offline branch
    s.polyline([(693,358),(693,410),(745,410),(745,500)],color=RED,sw=3,dash="10 8",arrow=True)
    s.rect(545,500,400,95,fill=PALE_RED,stroke=RED,sw=2.5,rx=16)
    s.text(745,530,"Network forbidden",size=20,color=RED,weight=900,anchor="middle")
    s.text(745,558,["hit -> stale with age", "miss -> unavailable; zero live work"],size=15.5,color=INK,weight=650,anchor="middle",line_h=21)
    # live success to lease
    s.line(955,358,955,500,color=BLUE,sw=4,arrow=True)
    s.rect(967,500,116,95,fill=PALE_VIOLET,stroke=VIOLET,sw=2.5,rx=16)
    s.text(1025,530,"Return",size=19,color=DARK_VIOLET,weight=900,anchor="middle")
    s.text(1025,555,["lease +", "truth state"],size=15,color=INK,weight=700,anchor="middle",line_h=20)
    s.pill(520,180,560,32,"CACHE FIRST; LIVE INFRASTRUCTURE ONLY WHEN AUTHORIZED",fill=PALE_AMBER,stroke=AMBER,color=AMBER,size=13.2)

    # Policy modes
    s.region(1150,170,1190,470,"Freshness policy router",stroke=TEAL,fill="#FBFEFD",title_fill=MINT)
    modes=[
        ("allowStale", "completion / AI", ["return any snapshot now", "if absent: bounded wait", "refresh may continue async"], GREEN, PALE_GREEN),
        ("requireValidated", "diagnostics / browse", ["accept recent validation TTL", "else one coalesced T1 digest", "changed -> full refresh"], BLUE, PALE_BLUE),
        ("requireLive", "scripting / strict work", ["join or start forced refresh", "failure / timeout / drift", "-> unavailable"], RED, PALE_RED),
        ("offlineSnapshot", "explicit offline mode", ["no resolver/session/query/timer", "memory/disk hit -> stale", "miss -> unavailable"], AMBER, PALE_AMBER),
    ]
    mx=1178; my=252; mw=272; mh=300; mg=17
    for i,(title,use,lines,stroke,fill) in enumerate(modes):
        x=mx+i*(mw+mg)
        s.rect(x,my,mw,mh,fill=fill,stroke=stroke,sw=2.5,rx=18)
        s.text(x+mw/2,my+42,title,size=21,color=stroke,weight=900,anchor="middle")
        s.text(x+mw/2,my+70,use,size=14.5,color=SLATE,weight=700,anchor="middle",italic=True)
        s.bullets(x+20,my+115,lines,size=16.2,color=INK,bullet_color=stroke,line_h=26)
        if title=="requireValidated":
            s.pill(x+20,my+244,mw-40,34,"UNCHANGED -> TIMESTAMP ONLY",fill=WHITE,stroke=stroke,color=stroke,size=12.5)
        elif title=="allowStale":
            s.pill(x+20,my+244,mw-40,34,"BEST SNAPSHOT IMMEDIATELY",fill=WHITE,stroke=stroke,color=stroke,size=12.5)
        elif title=="requireLive":
            s.pill(x+20,my+244,mw-40,34,"RETAINED SNAPSHOT IS NOT LIVE",fill=WHITE,stroke=stroke,color=stroke,size=12.5)
        else:
            s.pill(x+20,my+244,mw-40,34,"ZERO NEW LIVE CALLS",fill=WHITE,stroke=stroke,color=stroke,size=12.5)
    s.text(1745,600,"Caller timeout / abort stops only that caller's wait; it never cancels shared hydration or validation.",
           size=16.5,color=DARK_TEAL,weight=800,anchor="middle")

    # Live hydration and drift lower section
    s.region(60,690,2280,570,"Live hydration and drift",stroke=BLUE,fill="#FBFDFF",title_fill="#EEF5FF")
    # transport row
    tx=92; ty=780
    nodes=[
        ("LazyMetadataConnection",230),
        ("SQL Data Plane service view",245),
        ("STS2 local backend",220),
        ("SQL Server sys.* catalogs",255),
    ]
    centers=[]
    for label,ww in nodes:
        s.rect(tx,ty,ww,76,fill=WHITE,stroke=BLUE,sw=2.5,rx=15)
        s.text(tx+ww/2,ty+34,label,size=17,color=INK,weight=850,anchor="middle")
        centers.append((tx+ww/2,ww))
        tx += ww+55
    for i in range(len(centers)-1):
        x1=centers[i][0]+centers[i][1]/2
        x2=centers[i+1][0]-centers[i+1][1]/2
        s.line(x1,ty+38,x2,ty+38,color=BLUE,sw=4,arrow=True)
    s.text(682,ty+105,"v2/connection.open",size=14.5,color=SLATE,weight=700,anchor="middle")
    s.text(1250,ty+105,"v2/query.execute -> result metadata + row pages + query.complete",size=14.5,color=SLATE,weight=700,anchor="middle")
    s.pill(1890,ty+17,405,42,"NO v2/metadata.* ENDPOINT TODAY",fill=PALE_AMBER,stroke=AMBER,color=AMBER,size=15)

    # session lanes
    s.text(92,905,"Dedicated metadata session lanes",size=21,color=BLUE,weight=900)
    lanes=[
        (92,935,570,"Main DB lane","serial H0-H7 + T1 digest + lazy definitions",TEAL,MINT),
        (682,935,570,"DB auxiliary lane","separate source; catalog-wide FIFO across section keys",VIOLET,PALE_VIOLET),
        (1272,935,570,"Server metadata / auxiliary","independent sources",VIOLET,PALE_VIOLET),
    ]
    for x,y,w,title,desc,stroke,fill in lanes:
        s.rect(x,y,w,70,fill=fill,stroke=stroke,sw=2,rx=14)
        s.text(x+18,y+30,title,size=18.5,color=stroke,weight=900)
        s.text(x+18,y+55,desc,size=14.5,color=INK,weight=650)
    s.pill(1880,925,420,42,"ONE ACTIVE QUERY PER PHYSICAL CONNECTION",fill=PALE_AMBER,stroke=AMBER,color=AMBER,size=14.5)

    # H ladder
    hy=1050; hx=90
    hsteps=[
        ("H0", "env + DB identity", GREEN, PALE_GREEN, 180),
        ("H1", "schemas", TEAL, MINT, 145),
        ("H2", "objects", TEAL, MINT, 145),
        ("H3", "columns/details", TEAL, MINT, 185),
        ("H4", "PK/UQ", TEAL, MINT, 145),
        ("H5/H5B", "FKs + pairs", TEAL, MINT, 180),
        ("H6", "parameters", TEAL, MINT, 155),
        ("H7", "descriptions", TEAL, MINT, 165),
    ]
    for i,(code,desc,stroke,fill,ww) in enumerate(hsteps):
        s.rect(hx,hy,ww,72,fill=fill,stroke=stroke,sw=2,rx=13)
        s.text(hx+ww/2,hy+28,code,size=19,color=stroke,weight=900,anchor="middle")
        s.text(hx+ww/2,hy+53,desc,size=14,color=INK,weight=650,anchor="middle")
        if i<len(hsteps)-1:
            s.line(hx+ww,hy+36,hx+ww+22,hy+36,color=TEAL,sw=3,arrow=True)
        hx+=ww+28
    # publication and rejection
    s.rect(1980,1034,310,102,fill=PALE_GREEN,stroke=GREEN,sw=2.5,rx=16)
    s.text(2135,1065,"Atomic publish",size=21,color=GREEN,weight=900,anchor="middle")
    s.text(2135,1095,["CatalogSnapshot N+1", "readiness + mode preserved"],size=15.5,color=INK,weight=650,anchor="middle",line_h=21)
    s.line(hx-28,1086,1980,1086,color=TEAL,sw=4,arrow=True)
    s.polyline([(180,1122),(180,1175),(470,1175)],color=RED,sw=3,dash="10 8",arrow=True)
    s.rect(470,1140,520,82,fill=PALE_RED,stroke=RED,sw=2.5,rx=15)
    s.text(730,1170,"H0 mismatch / timeout / identity drift",size=18,color=RED,weight=900,anchor="middle")
    s.text(730,1198,"fence epoch -> recycle source -> no cross-key publication",size=14.5,color=INK,weight=650,anchor="middle")

    # Drift inputs to refresh
    s.text(1030,1156,"Drift inputs",size=19,color=DARK_VIOLET,weight=900)
    drifts=[
        (1025,1174,305,"Successful local DDL",["CREATE / ALTER / DROP", "SP_RENAME; EXEC -> digest"],VIOLET,PALE_VIOLET),
        (1345,1174,320,"T1 cheap digest",["object count + ID + schema", "exact name + modifyDate"],BLUE,PALE_BLUE),
        (1680,1174,285,"Explicit policy",["consumer validation", "or forced refresh"],TEAL,MINT),
    ]
    for x,y,w,t,desc_lines,stroke,fill in drifts:
        s.rect(x,y,w,76,fill=fill,stroke=stroke,sw=2,rx=13)
        s.text(x+15,y+26,t,size=16.2,color=stroke,weight=900)
        s.text(x+15,y+49,desc_lines,size=11.8,color=INK,weight=620,line_h=16)
        s.polyline([(x+w/2,y),(x+w/2,1155),(1960,1155),(1960,1125)],color=VIOLET,sw=2.5,dash="8 7",arrow=True)
    s.pill(1985,1176,305,48,"CHANGED -> COALESCED FULL REFRESH",fill=PALE_VIOLET,stroke=VIOLET,color=DARK_VIOLET,size=12.7)

    s.finish(os.path.join(outdir,"03_metadata_acquisition_freshness_drift.svg"))


def draw_persistence(outdir: str):
    s=SVG()
    s.header(
        "Persistent Catalog Cache: Trust and Publication Protocol",
        "The cache is an optional projection of a published database snapshot. It is verified local input, never catalog authority.",
    )

    # filesystem spine
    s.region(60,170,2280,180,"On-disk representation",stroke=AMBER,fill="#FFFEFA",title_fill=PALE_AMBER)
    s.icon("lock",85,233,s=50,color=AMBER)
    s.text(153,246,"globalStorage/metadata-cache/v1/",size=23,color=AMBER,weight=900,family=MONO)
    s.text(153,282,"index.json (advisory listing/LRU; approximate across windows)",size=17,color=INK,weight=650,family=MONO)
    s.text(765,246,"databases/<sfp_*>/<dbh_...>/",size=21,color=AMBER,weight=850,family=MONO)
    chip_x=765
    for label,ww in [(".publication.lock",185),("manifest.json",165),("catalog.<compressed-sha256>.json.gz",390)]:
        s.rect(chip_x,263,ww,38,fill=WHITE,stroke=AMBER,sw=1.5,rx=9)
        s.text(chip_x+ww/2,288,label,size=13.2,color=INK,weight=700,anchor="middle",family=MONO)
        chip_x += ww+12
    s.pill(1735,224,560,45,"ONLY DATABASE SNAPSHOTS ARE PERSISTED",fill=PALE_BLUE,stroke=BLUE,color=BLUE,size=15.5)
    s.text(2015,299,"server catalogs and auxiliary sections remain live/lazy memory structures",size=14.5,color=SLATE,weight=650,anchor="middle")

    # Read and write columns
    s.region(60,390,1085,800,"Verified READ path",stroke=AMBER,fill="#FFFEFA",title_fill=PALE_AMBER)
    s.region(1190,390,1150,800,"Atomic WRITE and cross-window authority",stroke=AMBER,fill="#FFFEFA",title_fill=PALE_AMBER)

    # Read path steps
    read_steps=[
        ("1", "Manifest contract", "format / codec / model / shape"),
        ("2", "Requested-key binding", "server fingerprint + database hash + optional exact name"),
        ("3", "Physical bytes", "file exists; compressed-size bound; SHA-256; bounded gunzip"),
        ("4", "Logical payload", "parallel-array + referential invariants; canonical contentHash"),
        ("5", "Policy intersection", "privacy/readiness may be reduced, never elevated"),
        ("6", "Publish from disk", "rehydrate with original capture age + generation"),
    ]
    yy=470
    for i,(num,title,desc) in enumerate(read_steps):
        h=89
        fill=WHITE if i<5 else PALE_GREEN
        stroke=AMBER if i<5 else GREEN
        s.circle(105,yy+42,24,fill=stroke,stroke=stroke,sw=1)
        s.text(105,yy+50,num,size=18,color=WHITE,weight=900,anchor="middle")
        s.rect(145,yy,940,h,fill=fill,stroke=stroke,sw=2,rx=15)
        s.text(170,yy+34,title,size=20,color=stroke,weight=900)
        s.text(170,yy+64,desc,size=15.8,color=INK,weight=650)
        if i<len(read_steps)-1:
            s.line(105,yy+66,105,yy+102,color=AMBER,sw=3,arrow=True)
        yy += 105
    # Any read-proof failure joins one safe-miss rail.
    for fy in [512,617,722,827,932]:
        s.line(145,fy,82,fy,color=RED,sw=2,dash="7 7")
    s.polyline([(82,512),(82,1125),(165,1125)],color=RED,sw=3,dash="10 8",arrow=True)
    s.rect(165,1092,920,76,fill=PALE_RED,stroke=RED,sw=2.5,rx=16)
    s.text(190,1121,"Any failed proof -> SAFE MISS",size=19,color=RED,weight=900)
    s.text(190,1142,[
        "invalidate manifest; quarantine/delete best effort",
        "live hydrate only if network policy allows",
    ], size=13.2,color=INK,weight=650,line_h=17)
    s.pill(760,1109,295,42,"NEVER ADOPT PARTIAL TRUST",fill=WHITE,stroke=RED,color=RED,size=13.2)

    # Write flow top boxes
    write_steps=[
        ("Eligible snapshot", "published DB snapshot; latest generation wins", TEAL, MINT, 230),
        ("Canonical projection", "cm2 JSON; frozen field order; privacy stripping", TEAL, MINT, 245),
        ("Hash + compress", "csh_* logical hash; gzip + compressed SHA; 32 MiB cap", AMBER, PALE_AMBER, 230),
        ("Per-key authority", "exclusive lock; compare capturedAtUtc; equal time -> ordinal hash", VIOLET, PALE_VIOLET, 260),
    ]
    xx=1220; y=475
    centers=[]
    for title,desc,stroke,fill,ww in write_steps:
        s.rect(xx,y,ww,132,fill=fill,stroke=stroke,sw=2.5,rx=16)
        s.text(xx+ww/2,y+34,title,size=18.5,color=stroke,weight=900,anchor="middle")
        # two/three line desc by split
        lines=[]
        if title=="Eligible snapshot": lines=["published DB snapshot", "debounce 5 s", "latest generation wins"]
        elif title=="Canonical projection": lines=["CatalogCodecView -> cm2 JSON", "frozen field order", "strip prose / SQL definitions"]
        elif title=="Hash + compress": lines=["logical csh_* over canonical JSON", "gzip + compressed SHA", "enforce 32 MiB cap"]
        else: lines=["exclusive per-key lock", "capturedAtUtc authority", "equal time -> ordinal contentHash"]
        s.text(xx+ww/2,y+66,lines,size=14.2,color=INK,weight=650,anchor="middle",line_h=20)
        centers.append((xx+ww/2,ww))
        xx+=ww+32
    for i in range(len(centers)-1):
        s.line(centers[i][0]+centers[i][1]/2,y+66,centers[i+1][0]-centers[i+1][1]/2,y+66,color=AMBER,sw=4,arrow=True)

    # Commit sequence
    s.text(1224,650,"Commit sequence under the winning publication decision",size=21,color=AMBER,weight=900)
    commits=[
        ("1", "payload temp", "write + fsync"),
        ("2", "payload rename", "content-addressed filename"),
        ("3", "manifest temp", "write + fsync"),
        ("4", "manifest rename LAST", "pointer becomes authoritative"),
        ("5", "postcheck", "winning writer / equality proof"),
    ]
    cx=1220; cy=694; cws=[175,205,175,225,170]
    for i,((num,title,desc),ww) in enumerate(zip(commits,cws)):
        stroke=GREEN if i==3 else AMBER
        fill=PALE_GREEN if i==3 else WHITE
        s.rect(cx,cy,ww,118,fill=fill,stroke=stroke,sw=2.3,rx=15)
        s.circle(cx+25,cy+25,18,fill=stroke,stroke=stroke,sw=1)
        s.text(cx+25,cy+31,num,size=14,color=WHITE,weight=900,anchor="middle")
        title_size = 15.5 if title in ("manifest rename LAST", "payload rename") else 16.2
        s.text(cx+ww/2+7,cy+48,title,size=title_size,color=stroke,weight=900,anchor="middle")
        s.text(cx+ww/2,cy+79,desc,size=12.8,color=INK,weight=650,anchor="middle")
        if i<len(commits)-1:
            s.line(cx+ww,cy+59,cx+ww+16,cy+59,color=AMBER,sw=3,arrow=True)
        cx+=ww+18

    # Cross-window race illustration
    s.text(1224,860,"Why the per-key lock is load-bearing",size=21,color=DARK_VIOLET,weight=900)
    s.rect(1220,895,1090,206,fill=WHITE,stroke=VIOLET,sw=2.5,rx=17)
    # timeline labels
    s.text(1245,928,"Writer A - older capture",size=17.5,color=RED,weight=900)
    s.text(1245,1004,"Writer B - newer capture",size=17.5,color=GREEN,weight=900)
    x0=1500; x1=2245
    s.line(x0,925,x1,925,color=MID,sw=3)
    s.line(x0,1001,x1,1001,color=MID,sw=3)
    points=[
        (1560,"read M0"),(1760,"A pauses"),(2040,"waits for lock"),(2220,"sees newer B")
    ]
    for x,lab in points:
        s.circle(x,925,8,fill=RED if x<2000 else VIOLET,stroke=WHITE,sw=2)
        s.text(x,957,lab,size=13,color=INK,weight=650,anchor="middle")
    points2=[
        (1605,"read M0"),(1795,"lock"),(1955,"payload"),(2085,"manifest last"),(2220,"commit")
    ]
    for x,lab in points2:
        s.circle(x,1001,8,fill=GREEN,stroke=WHITE,sw=2)
        s.text(x,1033,lab,size=13,color=INK,weight=650,anchor="middle")
    s.polyline([(1795,1001),(1795,1072),(2040,1072),(2040,925)],color=VIOLET,sw=3,dash="8 7",arrow=True)
    s.pill(1530,1052,720,38,"A'S DECISION WAITS; A CANNOT INSTALL AN OLDER MANIFEST AFTER B",fill=PALE_VIOLET,stroke=VIOLET,color=DARK_VIOLET,size=13.5)

    # Manifest card and boundaries
    s.rect(1220,1118,780,58,fill=PALE_BLUE,stroke=BLUE,sw=2,rx=12)
    s.text(1610,1140,[
        "Manifest: producer | writerId | key | capture/generation/source | validation",
        "environment | readiness/mode | payload file/SHA/contentHash",
    ], size=12.2,color=INK,weight=650,anchor="middle",line_h=18)
    s.pill(2015,1124,295,46,"CONTENT ADDRESSING PROTECTS BYTES",fill=PALE_AMBER,stroke=AMBER,color=AMBER,size=12.3)

    # Footer constraints
    s.rect(60,1215,2280,92,fill=WHITE,stroke=MID,sw=2,rx=18)
    footer=[
        ("DEFAULT OFF",190),
        ("MAX AGE 14 DAYS",235),
        ("TOTAL 256 MiB",220),
        ("32 MiB COMPRESSED / ENTRY",315),
        ("ORPHAN GRACE 10 MIN",270),
        ("CLEAR MANIFEST FIRST; REMAINING BYTES ARE INERT",600),
    ]
    fx=82
    for label,ww in footer:
        s.pill(fx,1238,ww,46,label,fill=PALE_AMBER,stroke=AMBER,color=AMBER,size=14.5)
        fx+=ww+15
    s.finish(os.path.join(outdir,"04_metadata_cache_persistence_protocol.svg"))


def main():
    outdir="/mnt/data/metadata_cache_diagrams"
    os.makedirs(outdir,exist_ok=True)
    draw_overview(outdir)
    draw_layout(outdir)
    draw_lifecycle(outdir)
    draw_persistence(outdir)
    print(outdir)

if __name__=="__main__":
    main()
