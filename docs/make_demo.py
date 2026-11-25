#!/usr/bin/env python3
"""Draws the README terminal demo (docs/img/demo-light.svg, demo-dark.svg). Standard library only.
One looping scene, pure CSS animation inside the SVG (no scripts, no fonts, no images): a person asks, the agent
queues the task, it waits for the window reset, `tick` starts it, `queue show` reports done.
With prefers-reduced-motion the animation is off and the final frame is shown. Run: python3 docs/make_demo.py"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent / 'img'
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
VIOLET, INDIGO = '#8b5cf6', '#6366f1'
GREEN, AMBER, SKY = '#10b981', '#f59e0b', '#38bdf8'

THEMES = {
    'light': dict(win='#fbfbfe', bar='#f0eff8', edge='#e4e4ee', text='#1f1d2e', sub='#6b6b7b', prompt=INDIGO,
                  human='#0284c7', waiting='#b45309', running='#6d5ae6', done='#059669', queued='#0284c7',
                  shadow='0.10', dots=('#fca5a5', '#fcd34d', '#86efac')),
    'dark': dict(win='#0d1117', bar='#161b22', edge='#2d333b', text='#e6edf3', sub='#8b949e', prompt='#818cf8',
                 human=SKY, waiting=AMBER, running='#a78bfa', done=GREEN, queued=SKY,
                 shadow='0.45', dots=('#ef4444', '#f59e0b', '#10b981')),
}

W, H = 900, 420
LOOP = 17.0          # seconds for one turn of the scene
CW, FS = 8.1, 13.5   # width of one character, font size: textLength pins the width, so every font lines up
X0, Y0, STEP = 34, 88, 23
CMD = 'python3 dispatcher.py'

# (start second, kind, segments) — kind 'type' types the line letter by letter, 'show' makes it appear at once.
# A segment is (text, colour key); None as colour key means the main text colour.
SCENE = [
    (0.5, 'type', [('you ›', 'human'), (' Refactor the payment module, not urgent.', None)]),
    (2.5, 'show', [('# size L, normal urgency: put it in the queue', 'sub')]),
    (3.2, 'type', [('$', 'prompt'), (f' {CMD} queue add refactor-payments --brief-file brief.md --size L --normal', None)]),
    (5.8, 'show', [('queued', 'queued'), ('   refactor-payments  (size L, normal)', None)]),
    (6.6, 'type', [('$', 'prompt'), (f' {CMD} queue list', None)]),
    (8.0, 'show', [('waiting', 'waiting'), ('  refactor-payments  claude: short window 85 % — waits for reset at 14:00', None)]),
    (9.4, 'show', [('… 14:00 — the window resets', 'waiting')]),
    (10.2, 'type', [('$', 'prompt'), (f' {CMD} tick', None)]),
    (11.4, 'show', [('running', 'running'), ('  refactor-payments  claude: window is free, starting now', None)]),
    (12.4, 'type', [('$', 'prompt'), (f' {CMD} queue show refactor-payments', None)]),
    (14.0, 'show', [('done', 'done'), ('     refactor-payments', None)]),
    (14.4, 'show', [('report: 0 errors, tests passed', 'sub')]),
    (15.0, 'prompt', [('$', 'prompt')]),
]
CLOCK_AT = 9.4       # the clock in the title bar jumps from 11:20 to 14:00
CPS = 38.0           # typing speed, characters per second


def pct(sec):
    return round(sec / LOOP * 100, 3)


def keyframes(name, stops):
    """stops: list of (second, css, steps or None); a leading 0 % stop is added by the caller."""
    body = ''.join(f'{pct(s)}%{{{css}{";animation-timing-function:steps(%d,end)" % n if n else ""}}}' for s, css, n in stops)
    body += f'100%{{{stops[-1][1]}}}'  # hold the last state to the end of the loop (else it eases back to the base style)
    return f'@keyframes {name}{{{body}}}'


def length(segs):
    return sum(len(s) for s, _ in segs)


def render(t):
    css = [f'text{{font-size:{FS}px;white-space:pre}}']
    body, n_lines = [], len(SCENE)
    colour = lambda key: t[key] if key else t['text']
    fade_end, wrap = LOOP * 0.97, LOOP * 0.995
    for i, (start, kind, segs) in enumerate(SCENE):
        y = Y0 + i * STEP
        nxt = SCENE[i + 1][0] if i + 1 < n_lines else fade_end
        n = length(segs)
        g = [f'<g class="l{i}">']
        col = 0
        for s, key in segs:
            lead, core = len(s) - len(s.lstrip()), s.strip()
            if core:
                g.append(f'<text x="{round(X0 + (col + lead) * CW, 1)}" y="{y}" fill="{colour(key)}" textLength="{round(len(core) * CW, 1)}" '
                         f'lengthAdjust="spacing"{" font-weight=\"700\"" if key in ("queued", "waiting", "running", "done") else ""}>{escape(core)}</text>')
            col += len(s)
        if kind == 'type':
            dur = n / CPS
            g.append(f'<rect class="c{i}" x="{X0 - 2}" y="{y - 15}" width="{round(n * CW + 4, 1)}" height="21" fill="{t["win"]}"/>')
            css.append(f'.c{i}{{transform-box:fill-box;transform-origin:100% 50%;transform:scaleX(0);animation:c{i} {LOOP}s linear infinite}}')
            css.append(keyframes(f'c{i}', [(0, 'transform:scaleX(1)', None), (start, 'transform:scaleX(1)', n),
                                           (start + dur, 'transform:scaleX(0)', None), (wrap, 'transform:scaleX(0)', None),
                                           (wrap + 0.01, 'transform:scaleX(1)', None)]))
            # the cursor runs along the typing front, then sits blinking at the end of the line until the next one starts
            g.append(f'<g class="k{i}"><rect class="b" x="{X0 - 2}" y="{y - 14}" width="8" height="18" fill="{t["prompt"]}"/></g>')
            css.append(f'.k{i}{{opacity:0;animation:k{i} {LOOP}s linear infinite}}')
            css.append(keyframes(f'k{i}', [(0, 'opacity:0;transform:translateX(0)', None), (start - 0.01, 'opacity:0;transform:translateX(0)', None),
                                           (start, 'opacity:1;transform:translateX(0)', n),
                                           (start + dur, 'opacity:1;transform:translateX(%.1fpx)' % (n * CW), None),
                                           (nxt - 0.01, 'opacity:1;transform:translateX(%.1fpx)' % (n * CW), None),
                                           (nxt, 'opacity:0;transform:translateX(%.1fpx)' % (n * CW), None)]))
        elif kind == 'prompt':
            cx = X0 + n * CW + CW
            g.append(f'<rect class="b k{i}" x="{round(cx, 1)}" y="{y - 14}" width="8" height="18" fill="{t["prompt"]}"/>')
        else:
            css.append(f'.l{i}{{animation:s{i} {LOOP}s linear infinite}}')
            css.append(keyframes(f's{i}', [(0, 'opacity:0', None), (start - 0.01, 'opacity:0', None), (start, 'opacity:1', None),
                                           (wrap, 'opacity:1', None), (wrap + 0.01, 'opacity:0', None)]))
        if kind == 'prompt':
            css.append(f'.l{i}{{animation:s{i} {LOOP}s linear infinite}}')
            css.append(keyframes(f's{i}', [(0, 'opacity:0', None), (start - 0.01, 'opacity:0', None), (start, 'opacity:1', None),
                                           (wrap, 'opacity:1', None), (wrap + 0.01, 'opacity:0', None)]))
        g.append('</g>')
        body.append(''.join(g))
    css.append('.b{animation:blink 1s steps(1,end) infinite}')
    css.append('@keyframes blink{0%{opacity:1}50%{opacity:0}}')
    # the whole scene fades out a moment before it starts over
    css.append(f'.scene{{animation:fade {LOOP}s linear infinite}}')
    css.append(keyframes('fade', [(0, 'opacity:1', None), (fade_end, 'opacity:1', None), (LOOP * 0.99, 'opacity:0', None)]))
    # clock in the title bar
    css.append(f'.t1{{animation:t1 {LOOP}s linear infinite}}.t2{{opacity:1;animation:t2 {LOOP}s linear infinite}}')
    css.append(keyframes('t1', [(0, 'opacity:1', None), (CLOCK_AT - 0.01, 'opacity:1', None), (CLOCK_AT, 'opacity:0', None)]))
    css.append(keyframes('t2', [(0, 'opacity:0', None), (CLOCK_AT - 0.01, 'opacity:0', None), (CLOCK_AT, 'opacity:1', None)]))
    # blinking cursors are only for moving pictures
    reduced = '@media (prefers-reduced-motion:reduce){*{animation:none !important}.b{opacity:0}.scene{opacity:1}.t1{opacity:0}}'
    # base state = the final picture (typed-line covers and cursors hidden, every line visible)
    style = '\n'.join(css + [reduced])

    wx, wy, ww, wh = 10, 10, W - 20, H - 24
    dots = ''.join(f'<circle cx="{34 + i * 20}" cy="35" r="6" fill="{c}"/>' for i, c in enumerate(t['dots']))
    clock_y = 40
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" role="img" aria-label="Terminal demo: a task is queued, waits for the window reset, runs and finishes">
<defs>
  <clipPath id="win"><rect x="{wx}" y="{wy}" width="{ww}" height="{wh}" rx="14"/></clipPath>
  <filter id="sh" x="-10%" y="-10%" width="120%" height="125%"><feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#1e1b4b" flood-opacity="{t['shadow']}"/></filter>
</defs>
<style>
{style}
</style>
<rect x="{wx}" y="{wy}" width="{ww}" height="{wh}" rx="14" fill="{t['win']}" stroke="{t['edge']}" filter="url(#sh)"/>
<g clip-path="url(#win)"><rect x="{wx}" y="{wy}" width="{ww}" height="40" fill="{t['bar']}"/><rect x="{wx}" y="{wy + 40}" width="{ww}" height="1" fill="{t['edge']}"/></g>
{dots}
<text x="{W // 2}" y="{clock_y}" text-anchor="middle" fill="{t['sub']}" font-size="12.5" font-family="{FONT}">agent — dispatcher demo</text>
<text class="t1" x="{W - 34}" y="{clock_y}" text-anchor="end" fill="{t['sub']}" font-size="12.5">clock 11:20</text>
<text class="t2" x="{W - 34}" y="{clock_y}" text-anchor="end" fill="{t['waiting']}" font-size="12.5" font-weight="700" opacity="0">clock 14:00</text>
<g class="scene">
{chr(10).join(body)}
</g>
</svg>
'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, t in THEMES.items():
        (OUT / f'demo-{name}.svg').write_text(render(t), encoding='utf-8')
    print('written: demo-light.svg, demo-dark.svg')


if __name__ == '__main__':
    main()
