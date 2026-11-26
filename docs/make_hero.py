#!/usr/bin/env python3
"""Draws the animated README hero (docs/img/hero-light.svg, hero-dark.svg). Standard library only.
A short story that loops every 20 s, no words you have to read: a person asks for something in a chat bubble; the
dispatcher robot turns it into a task card (size L, not urgent) and puts it in the queue; the agent's usage gauge is
almost full, so the card waits (pulsing) while the clock turns and the gauge resets; the card goes to the agent, who
works; a green check says done and the person gets a notification.
Pure CSS @keyframes inside the SVG (no scripts, fonts or images). The element base styles are the FINAL frame, so
with prefers-reduced-motion the picture shows the finished state. Run: python3 docs/make_hero.py"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / 'img'
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Helvetica, Arial, sans-serif"
VIOLET, INDIGO, PINK = '#8b5cf6', '#6366f1', '#ec4899'
GREEN, AMBER, RED, SKY = '#10b981', '#f59e0b', '#ef4444', '#38bdf8'

THEMES = {
    'light': dict(bg1='#f7f5ff', bg2='#eef4ff', ink='#1f1d2e', sub='#6b6880', paper='#ffffff', line='#d9d6ea',
                  desk='#e9e6f7', deskedge='#d6d1ee', skin='#f2c6a8', hair='#3b2f4a', shirt=INDIGO, screen='#1e1b3a',
                  robot='#ffffff', robotedge='#d9d6ea', shadow='0.10', star='#c9c2f0'),
    'dark': dict(bg1='#14122a', bg2='#0d1526', ink='#ecebf7', sub='#9b98b5', paper='#1d1b33', line='#353252',
                 desk='#211f3a', deskedge='#2e2b4d', skin='#e7b48f', hair='#a78bfa', shirt=VIOLET, screen='#0b0a17',
                 robot='#262443', robotedge='#3d3a62', shadow='0.45', star='#3d3870'),
}


class Pic:
    def __init__(self, t, w=1200, h=600):
        self.t, self.w, self.h, self.p, self.css = t, w, h, [], []

    def add(self, s):
        self.p.append(s)

    def text(self, x, y, s, size=14, weight=600, color=None, anchor='middle', op=1):
        self.add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color or self.t["ink"]}" '
                 f'text-anchor="{anchor}" opacity="{op}">{escape(s)}</text>')

    def render(self):
        t = self.t
        defs = f'''<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{t['bg1']}"/><stop offset="1" stop-color="{t['bg2']}"/></linearGradient>
  <linearGradient id="acc" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{INDIGO}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>
  <linearGradient id="glow" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{SKY}" stop-opacity="0.55"/><stop offset="1" stop-color="{SKY}" stop-opacity="0"/></linearGradient>
  <radialGradient id="halo"><stop offset="0" stop-color="{VIOLET}" stop-opacity="0.35"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
  <filter id="sh" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#1e1b4b" flood-opacity="{t['shadow']}"/></filter>
</defs>'''
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
                f'font-family="{FONT}">\n{defs}\n<style>\n' + '\n'.join(self.css) + '\n</style>\n' + '\n'.join(self.p) + '\n</svg>\n')


def background(p):
    t = p.t
    p.add(f'<rect x="0" y="0" width="{p.w}" height="{p.h}" rx="28" fill="url(#bg)"/>')
    for x, y, r in ((90, 70, 3), (260, 40, 2), (520, 60, 2.5), (760, 36, 2), (1010, 72, 3), (1130, 140, 2), (640, 120, 1.8),
                    (40, 300, 2), (1160, 330, 2.5), (400, 150, 1.6)):
        p.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{t["star"]}"/>')
    # floor line
    p.add(f'<path d="M40 520 H1160" stroke="{t["line"]}" stroke-width="2" stroke-linecap="round"/>')


def person(p, x, y):
    """A person at a laptop, (x, y) = seat point."""
    t = p.t
    # chair
    p.add(f'<rect x="{x - 46}" y="{y + 20}" width="92" height="12" rx="6" fill="{t["deskedge"]}"/>')
    p.add(f'<rect x="{x - 6}" y="{y + 32}" width="12" height="70" rx="6" fill="{t["deskedge"]}"/>')
    # body
    p.add(f'<path d="M{x - 40} {y + 22} C{x - 40} {y - 50}, {x + 40} {y - 50}, {x + 40} {y + 22} Z" fill="{t["shirt"]}"/>')
    # head + hair
    p.add(f'<circle cx="{x}" cy="{y - 72}" r="30" fill="{t["skin"]}"/>')
    p.add(f'<path d="M{x - 31} {y - 74} C{x - 34} {y - 112}, {x + 30} {y - 118}, {x + 32} {y - 78} C{x + 18} {y - 92}, {x - 10} {y - 96}, {x - 31} {y - 74} Z" fill="{t["hair"]}"/>')
    p.add(f'<circle cx="{x + 12}" cy="{y - 70}" r="3" fill="{t["ink"]}"/>')
    p.add(f'<path d="M{x + 8} {y - 57} q6 4 12 0" stroke="{t["ink"]}" stroke-width="2.4" fill="none" stroke-linecap="round"/>')
    # desk + laptop
    p.add(f'<rect x="{x + 20}" y="{y + 4}" width="150" height="14" rx="7" fill="{t["desk"]}" stroke="{t["deskedge"]}"/>')
    p.add(f'<rect x="{x + 60}" y="{y + 18}" width="10" height="84" rx="5" fill="{t["deskedge"]}"/>')
    p.add(f'<rect x="{x + 150}" y="{y + 18}" width="10" height="84" rx="5" fill="{t["deskedge"]}"/>')
    p.add(f'<path d="M{x + 70} {y + 4} L{x + 82} {y - 52} L{x + 150} {y - 52} L{x + 140} {y + 4} Z" fill="{t["screen"]}"/>')
    p.add(f'<circle cx="{x + 114}" cy="{y - 24}" r="5" fill="{VIOLET}" opacity="0.8"/>')
    # arm
    p.add(f'<path d="M{x + 22} {y - 18} Q{x + 52} {y - 8} {x + 72} {y}" stroke="{t["shirt"]}" stroke-width="16" fill="none" stroke-linecap="round"/>')


def robot(p, x, y, s=1.0, body=None, eyes='open', glow=False):
    """A small rounded robot head+body centred at x, bottom at y."""
    t = p.t
    body = body or t['robot']
    if glow:
        p.add(f'<circle cx="{x}" cy="{y - 70 * s}" r="{90 * s}" fill="url(#halo)"/>')
    p.add(f'<g filter="url(#sh)">')
    p.add(f'<rect x="{x - 42 * s}" y="{y - 60 * s}" width="{84 * s}" height="{60 * s}" rx="{22 * s}" fill="{body}" stroke="{t["robotedge"]}"/>')
    p.add(f'<rect x="{x - 50 * s}" y="{y - 132 * s}" width="{100 * s}" height="{74 * s}" rx="{26 * s}" fill="{body}" stroke="{t["robotedge"]}"/>')
    p.add('</g>')
    p.add(f'<line x1="{x}" y1="{y - 132 * s}" x2="{x}" y2="{y - 152 * s}" stroke="{t["robotedge"]}" stroke-width="{4 * s}" stroke-linecap="round"/>')
    p.add(f'<circle cx="{x}" cy="{y - 156 * s}" r="{7 * s}" fill="{PINK if glow else t["robotedge"]}"/>')
    p.add(f'<rect x="{x - 36 * s}" y="{y - 118 * s}" width="{72 * s}" height="{40 * s}" rx="{16 * s}" fill="{t["screen"]}"/>')
    if eyes == 'open':
        for dx in (-14, 14):
            p.add(f'<circle cx="{x + dx * s}" cy="{y - 100 * s}" r="{5.5 * s}" fill="{SKY}"/>')
        p.add(f'<path d="M{x - 9 * s} {y - 89 * s} q{9 * s} {6 * s} {18 * s} 0" stroke="{SKY}" stroke-width="{2.6 * s}" fill="none" stroke-linecap="round"/>')
    elif eyes == 'sleep':
        for dx in (-14, 14):
            p.add(f'<path d="M{x + (dx - 6) * s} {y - 99 * s} q{6 * s} {5 * s} {12 * s} 0" stroke="{SKY}" stroke-width="{2.6 * s}" fill="none" stroke-linecap="round"/>')
    elif eyes == 'wait':
        for dx in (-14, 14):
            p.add(f'<rect x="{x + (dx - 6) * s}" y="{y - 102 * s}" width="{12 * s}" height="{4 * s}" rx="{2 * s}" fill="{AMBER}"/>')


T = 20.0   # seconds per loop


def anim(p, cls, base, frames, extra=''):
    """Registers a CSS class: `base` = final frame (shown with reduced motion), `frames` = [(sec, 'css props'), ...]
    for the loop. A frame at 0 s is required."""
    name = 'k_' + cls
    kf = ''.join(f'{sec / T * 100:.2f}%{{{props}}}' for sec, props in frames)
    p.css.append(f'.{cls}{{{base};animation:{name} {T}s cubic-bezier(.45,0,.25,1) infinite both}}'
                 f'@keyframes {name}{{{kf}}}')


def bubble_box(p, x, y, w, h, cls, fill=None):
    t = p.t
    p.add(f'<g class="{cls}" filter="url(#sh)"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="{fill or t["paper"]}"/>'
          f'<path d="M{x + 34} {y + h - 1} l-10 22 l28 -22 Z" fill="{fill or t["paper"]}"/>')


def smiley(p, cx, cy, r=11):
    t = p.t
    p.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{AMBER}"/>'
          f'<circle cx="{cx - 4}" cy="{cy - 2.5}" r="1.5" fill="{t["hair"] if t is THEMES["light"] else "#1f1d2e"}"/>'
          f'<circle cx="{cx + 4}" cy="{cy - 2.5}" r="1.5" fill="{t["hair"] if t is THEMES["light"] else "#1f1d2e"}"/>'
          f'<path d="M{cx - 5} {cy + 2.5} q5 5 10 0" stroke="{t["hair"] if t is THEMES["light"] else "#1f1d2e"}" stroke-width="1.8" fill="none" stroke-linecap="round"/>')


def check(p, cx, cy, r, color=GREEN, stroke='#ffffff'):
    p.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>'
          f'<path d="M{cx - r * .42} {cy + r * .02} l{r * .28} {r * .3} l{r * .55} {-r * .62}" stroke="{stroke}" '
          f'stroke-width="{r * .22}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')


def pill(p, x, y, w, h, color, label, size=13):
    p.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{color}"/>')
    p.text(x + w / 2, y + h / 2 + size * .36, label, size, 700, '#ffffff')


def task_card(p, x, y):
    """The task card: a little login-page thumbnail, two grey lines, tags 'L' and 'not urgent'."""
    t = p.t
    w, h = 190, 88
    p.add(f'<g filter="url(#sh)"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{t["paper"]}" stroke="{t["line"]}"/></g>')
    # thumbnail of a login page
    p.add(f'<rect x="{x + 12}" y="{y + 12}" width="46" height="40" rx="8" fill="{t["bg2"]}" stroke="{t["line"]}"/>'
          f'<circle cx="{x + 35}" cy="{y + 23}" r="5" fill="{VIOLET}"/>'
          f'<rect x="{x + 21}" y="{y + 32}" width="28" height="4" rx="2" fill="{t["line"]}"/>'
          f'<rect x="{x + 24}" y="{y + 40}" width="22" height="6" rx="3" fill="{PINK}"/>')
    p.add(f'<rect x="{x + 70}" y="{y + 18}" width="104" height="8" rx="4" fill="{t["line"]}"/>'
          f'<rect x="{x + 70}" y="{y + 34}" width="70" height="8" rx="4" fill="{t["line"]}" opacity="0.7"/>')
    pill(p, x + 12, y + 58, 30, 22, VIOLET, 'L', 13)
    pill(p, x + 50, y + 58, 84, 22, SKY, 'not urgent', 12)


def clock(p, cx, cy, r=40):
    t = p.t
    p.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{t["paper"]}" stroke="{AMBER}" stroke-width="5" filter="url(#sh)"/>')
    for k in range(12):
        a = k * 30
        l = 6 if k % 3 == 0 else 3
        p.add(f'<line x1="{cx}" y1="{cy - r + 8}" x2="{cx}" y2="{cy - r + 8 + l}" stroke="{t["sub"]}" stroke-width="2" '
              f'stroke-linecap="round" transform="rotate({a} {cx} {cy})"/>')
    p.add(f'<line class="hhand" x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy - r * .5}" stroke="{t["ink"]}" stroke-width="5" stroke-linecap="round" '
          f'style="transform-origin:{cx}px {cy}px"/>')
    p.add(f'<line class="mhand" x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy - r * .72}" stroke="{AMBER}" stroke-width="3.5" stroke-linecap="round" '
          f'style="transform-origin:{cx}px {cy}px"/>')
    p.add(f'<circle cx="{cx}" cy="{cy}" r="4" fill="{t["ink"]}"/>')


def agent_desk(p, X, s, eyes, op=1.0):
    """A desk with a robot and a monitor, scaled s about the floor point (X, 520). Returns monitor origin."""
    t = p.t
    Y = 392
    p.add(f'<g opacity="{op}" transform="translate({X} 520) scale({s}) translate({-X} -520)">')
    p.add(f'<rect x="{X - 70}" y="{Y}" width="140" height="14" rx="7" fill="{t["desk"]}" stroke="{t["deskedge"]}"/>')
    p.add(f'<rect x="{X - 58}" y="{Y + 14}" width="10" height="{520 - Y - 14}" rx="5" fill="{t["deskedge"]}"/>')
    p.add(f'<rect x="{X + 48}" y="{Y + 14}" width="10" height="{520 - Y - 14}" rx="5" fill="{t["deskedge"]}"/>')
    robot(p, X - 30, Y + 2, 0.52, eyes=eyes)
    mx, my = X + 2, Y - 92
    p.add(f'<rect x="{mx}" y="{my}" width="66" height="62" rx="10" fill="{t["screen"]}" stroke="{t["robotedge"]}"/>')
    p.add(f'<rect x="{mx + 27}" y="{my + 62}" width="12" height="30" fill="{t["robotedge"]}"/>')
    if eyes == 'sleep':
        p.text(mx + 33, my + 38, 'z z', 16, 700, t['sub'])
    else:   # tired: a small amber clock, the agent is near its limit
        cx, cy = mx + 33, my + 31
        p.add(f'<circle cx="{cx}" cy="{cy}" r="17" fill="none" stroke="{AMBER}" stroke-width="3"/>'
              f'<path d="M{cx} {cy - 10} V{cy} L{cx + 7} {cy + 5}" stroke="{AMBER}" stroke-width="3" fill="none" stroke-linecap="round"/>')
    p.add('</g>')


def hero(t):
    p = Pic(t)
    GX, GY, GW = 790, 204, 200            # usage gauge
    CX, CY = 1075, 205                    # clock
    background(p)

    # dotted paths: person -> robot -> queue -> agent
    for d in ('M268 236 C320 236, 360 270, 392 318', 'M470 400 C500 410, 515 400, 530 392', 'M742 376 C780 376, 800 360, 830 340'):
        p.add(f'<path d="{d}" stroke="{VIOLET}" stroke-width="2.4" fill="none" stroke-dasharray="2 9" stroke-linecap="round" opacity="0.6"/>')

    person(p, 110, 410)

    # dispatcher robot with a clipboard (bobs once when it catches the message)
    p.add('<g class="bob">')
    robot(p, 425, 470, 1.1, glow=True)
    p.add(f'<g transform="rotate(12 478 376)"><rect x="456" y="347" width="44" height="58" rx="8" fill="{t["paper"]}" stroke="{t["line"]}"/>'
          + ''.join(f'<rect x="464" y="{358 + i * 12}" width="28" height="5" rx="2.5" fill="{t["line"]}"/>' for i in range(3)) + '</g>')
    p.add('</g>')

    # the queue: an empty tray
    p.add(f'<rect x="526" y="324" width="218" height="112" rx="22" fill="none" stroke="{t["line"]}" stroke-width="2.5" stroke-dasharray="7 9"/>')

    agent_desk(p, 900, 1.2, 'wait')
    agent_desk(p, 1112, 0.9, 'sleep', 0.7)

    for x, label in ((110, 'you'), (425, 'dispatcher'), (635, 'queue'), (900, 'agent')):
        p.text(x, 552, label, 16, 700)

    # ---- everything that moves -------------------------------------------------------------------------------
    anim(p, 'scene', 'opacity:1', [(0, 'opacity:0'), (0.5, 'opacity:1'), (18.4, 'opacity:1'), (19.4, 'opacity:0')])
    p.add('<g class="scene">')

    # 1. the person's chat bubble, then it flies into the robot's clipboard
    bubble_box(p, 30, 190, 232, 70, 'say')
    p.text(50, 220, 'Make the login page', 16, 700, anchor='start')
    p.text(50, 244, 'prettier — no rush', 15, 500, t['sub'], anchor='start')
    smiley(p, 232, 239)
    p.add('</g>')
    anim(p, 'say', 'opacity:0', [(0, 'opacity:0;transform:scale(.6)'), (0.4, 'opacity:0;transform:scale(.6)'), (1.4, 'opacity:1;transform:scale(1)'),
                                 (3.6, 'opacity:1;transform:scale(1)'), (4.4, 'opacity:1;transform:translate(332px,150px) scale(.2)'),
                                 (4.6, 'opacity:0;transform:translate(332px,150px) scale(.2)'), (20, 'opacity:0;transform:scale(.6)')])
    anim(p, 'bob', 'transform:none', [(0, 'transform:none'), (4.1, 'transform:none'), (4.5, 'transform:translateY(-10px)'), (5.0, 'transform:none')])

    # 3. waiting: a pulsing amber ring around the card + a label
    p.add('<g class="waitwrap"><g class="pulse">'
          f'<rect x="533" y="328" width="204" height="102" rx="22" fill="none" stroke="{AMBER}" stroke-width="4"/></g>')
    p.add(f'<rect x="545" y="462" width="180" height="30" rx="15" fill="{AMBER}"/>')
    p.add(f'<circle cx="565" cy="477" r="8" fill="none" stroke="#ffffff" stroke-width="2"/><path d="M565 472 V477 L569 479.5" stroke="#ffffff" stroke-width="2" fill="none" stroke-linecap="round"/>')
    p.text(644, 482, 'waiting for reset', 14, 700, '#ffffff')
    p.add('</g>')
    anim(p, 'waitwrap', 'opacity:0', [(0, 'opacity:0'), (5.8, 'opacity:0'), (6.6, 'opacity:1'), (12.2, 'opacity:1'), (12.8, 'opacity:0')])
    p.css.append('.pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.2s ease-in-out infinite}'
                 '@keyframes pulse{0%,100%{opacity:.25;transform:scale(1)}50%{opacity:1;transform:scale(1.035)}}')

    # clock + usage gauge on the agent
    clock(p, CX, CY)
    anim(p, 'mhand', 'transform:rotate(0deg)', [(0, 'transform:rotate(0deg)'), (8.0, 'transform:rotate(0deg)'), (11.0, 'transform:rotate(720deg)'), (20, 'transform:rotate(720deg)')])
    anim(p, 'hhand', 'transform:rotate(150deg)', [(0, 'transform:rotate(90deg)'), (8.0, 'transform:rotate(90deg)'), (11.0, 'transform:rotate(150deg)'), (20, 'transform:rotate(150deg)')])
    p.add(f'<rect x="{GX}" y="{GY}" width="{GW}" height="20" rx="10" fill="{t["line"]}"/>')
    p.add(f'<rect class="gfull" x="{GX}" y="{GY}" width="{GW}" height="20" rx="10" fill="{AMBER}" style="transform-origin:{GX}px {GY}px"/>')
    p.add(f'<rect class="gnew" x="{GX}" y="{GY}" width="{GW}" height="20" rx="10" fill="url(#acc)" style="transform-origin:{GX}px {GY}px"/>')
    anim(p, 'gfull', 'transform:scaleX(0)', [(0, 'transform:scaleX(.85)'), (10.8, 'transform:scaleX(.85)'), (11.7, 'transform:scaleX(0)'), (20, 'transform:scaleX(0)')])
    anim(p, 'gnew', 'transform:scaleX(.22)', [(0, 'transform:scaleX(0)'), (13.7, 'transform:scaleX(0)'), (15.2, 'transform:scaleX(.22)'), (20, 'transform:scaleX(.22)')])
    for cls, txt, col, base, fr in (
            ('u85', 'usage 85%', AMBER, 'opacity:0', [(0, 'opacity:1'), (10.8, 'opacity:1'), (11.2, 'opacity:0'), (20, 'opacity:0')]),
            ('u0', 'usage 0%', GREEN, 'opacity:0', [(0, 'opacity:0'), (10.8, 'opacity:0'), (11.2, 'opacity:1'), (13.5, 'opacity:1'), (13.9, 'opacity:0'), (20, 'opacity:0')]),
            ('u22', 'usage 22%', VIOLET, 'opacity:1', [(0, 'opacity:0'), (13.5, 'opacity:0'), (13.9, 'opacity:1'), (20, 'opacity:1')])):
        p.add(f'<g class="{cls}">')
        p.text(GX, GY - 10, 'usage', 16, 700, anchor='start')
        p.text(GX + GW, GY - 10, txt.split()[1], 16, 800, col, anchor='end')
        p.add('</g>')
        anim(p, cls, base, fr)
    # reset badge
    p.add('<g class="resetok">')
    pill(p, CX - 46, CY + 52, 92, 26, GREEN, 'reset', 13)
    check(p, CX + 30, CY + 65, 8, '#ffffff', GREEN)
    p.add('</g>')
    anim(p, 'resetok', 'opacity:0', [(0, 'opacity:0'), (11.4, 'opacity:0;transform:scale(.7)'), (11.9, 'opacity:1;transform:scale(1)'), (14.2, 'opacity:1'), (14.8, 'opacity:0'), (20, 'opacity:0')])
    p.css.append('.resetok{transform-box:fill-box;transform-origin:center}')

    # 2/5. the task card: appears from the clipboard, lies in the queue, flies to the agent
    p.add('<g class="tcard">')
    task_card(p, 540, 334)
    p.add('</g>')
    anim(p, 'tcard', 'opacity:0', [(0, 'opacity:0;transform:translate(-157px,0) scale(.2)'), (4.5, 'opacity:0;transform:translate(-157px,0) scale(.2)'),
                                    (4.9, 'opacity:1;transform:translate(-130px,-6px) scale(.45)'), (6.2, 'opacity:1;transform:translate(0,0) scale(1)'),
                                    (12.4, 'opacity:1;transform:translate(0,0) scale(1)'), (13.6, 'opacity:1;transform:translate(318px,-90px) scale(.36)'),
                                    (13.9, 'opacity:0;transform:translate(318px,-90px) scale(.3)'), (20, 'opacity:0;transform:translate(318px,-90px) scale(.3)')])
    p.css.append('.tcard,.say,.donebadge,.notif{transform-box:fill-box;transform-origin:center}')

    # 5. the agent wakes up and works
    mx, my = 902, 300
    p.add('<g class="work" transform="translate(900 520) scale(1.2) translate(-900 -520)">')
    p.add(f'<rect x="{mx}" y="{my}" width="66" height="62" rx="10" fill="{t["screen"]}" stroke="{t["robotedge"]}"/>'
          f'<rect x="{mx}" y="{my}" width="66" height="62" rx="10" fill="url(#glow)"/>')
    for i, (w, c) in enumerate(((40, VIOLET), (30, SKY), (46, PINK), (24, GREEN))):
        p.add(f'<rect class="stripe s{i}" x="{mx + 10}" y="{my + 10 + i * 11}" width="{w}" height="6" rx="3" fill="{c}" opacity="0.9"/>')
    # awake eyes on the agent robot (covers the tired ones)
    rx, ry, rs = 870, 394, 0.52
    p.add(f'<rect x="{rx - 36 * rs}" y="{ry - 118 * rs}" width="{72 * rs}" height="{40 * rs}" rx="{16 * rs}" fill="{t["screen"]}"/>')
    for dx in (-14, 14):
        p.add(f'<circle cx="{rx + dx * rs}" cy="{ry - 100 * rs}" r="{5.5 * rs}" fill="{SKY}"/>')
    p.add(f'<path d="M{rx - 9 * rs} {ry - 89 * rs} q{9 * rs} {6 * rs} {18 * rs} 0" stroke="{SKY}" stroke-width="{2.6 * rs}" fill="none" stroke-linecap="round"/>')
    p.add('</g>')
    anim(p, 'work', 'opacity:1', [(0, 'opacity:0'), (13.6, 'opacity:0'), (14.1, 'opacity:1'), (20, 'opacity:1')])
    p.css.append('.stripe{transform-box:fill-box;transform-origin:left center;animation:stripe 1.8s ease-in-out infinite alternate}'
                 '.s1{animation-delay:-.4s}.s2{animation-delay:-.9s}.s3{animation-delay:-1.3s}'
                 '@keyframes stripe{0%{transform:scaleX(.35)}100%{transform:scaleX(1)}}')

    # 6. done: green check over the agent, a notification for the person
    p.add('<g class="donebadge">')
    p.add(f'<rect x="760" y="98" width="290" height="46" rx="23" fill="{GREEN}" filter="url(#sh)"/>')
    check(p, 787, 121, 15, '#ffffff', GREEN)
    p.text(812, 127, 'Done — checked, no errors', 15, 700, '#ffffff', anchor='start')
    p.add('</g>')
    anim(p, 'donebadge', 'opacity:1', [(0, 'opacity:0;transform:scale(.6)'), (15.0, 'opacity:0;transform:scale(.6)'), (15.6, 'opacity:1;transform:scale(1.05)'),
                                       (15.9, 'opacity:1;transform:scale(1)'), (20, 'opacity:1;transform:scale(1)')])
    bubble_box(p, 30, 190, 250, 70, 'notif')
    check(p, 62, 225, 17)
    p.text(90, 232, 'Login page is ready', 16, 700, anchor='start')
    p.add(f'<circle cx="274" cy="192" r="10" fill="{RED}"/>')
    p.add('</g>')
    anim(p, 'notif', 'opacity:1', [(0, 'opacity:0;transform:scale(.6)'), (15.9, 'opacity:0;transform:scale(.6)'), (16.5, 'opacity:1;transform:scale(1.06)'),
                                   (16.8, 'opacity:1;transform:scale(1)'), (20, 'opacity:1;transform:scale(1)')])

    p.add('</g>')   # closes scene
    p.css.append('@media (prefers-reduced-motion:reduce){.scene,.say,.bob,.waitwrap,.pulse,.mhand,.hhand,.gfull,.gnew,.u85,.u0,.u22,.resetok,'
                 '.tcard,.work,.stripe,.donebadge,.notif{animation:none!important}}')
    return p


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, t in THEMES.items():
        (OUT / f'hero-{name}.svg').write_text(hero(t).render(), encoding='utf-8')
    print('written: hero-light.svg, hero-dark.svg')


if __name__ == '__main__':
    main()
