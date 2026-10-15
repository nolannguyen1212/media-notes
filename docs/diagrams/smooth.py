import base64
import html
import re
import sys

NUM = re.compile(r"-?\d+(?:\.\d+)?")


def bbox(shape):
    rect = re.search(r'<rect x="([-\d.]+)" y="([-\d.]+)" width="([-\d.]+)" height="([-\d.]+)"', shape)
    if rect:
        x, y, w, h = map(float, rect.groups())
        return x, y, x + w, y + h
    xs, ys = [], []
    for d in re.findall(r' d="([^"]+)"', shape):
        for cmd, args in re.findall(r"([MLCHVZ])([^MLCHVZ]*)", d):
            nums = list(map(float, NUM.findall(args)))
            if cmd == "H":
                xs += nums
            elif cmd == "V":
                ys += nums
            else:
                xs += nums[0::2]
                ys += nums[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def read_boxes(svg):
    boxes = {}
    for m in re.finditer(r'<g class="([A-Za-z0-9+/=]+)(?: [^"]*)?"><g class="shape" >(.*?)</g>', svg):
        name = html.unescape(base64.b64decode(m.group(1)).decode())
        boxes[name] = bbox(m.group(2))
    return boxes


def parse_edge(label):
    m = re.match(r"(?:(.*)\.)?\((.+?) (<->|->) (.+?)\)\[\d+\]$", label)
    if not m:
        return None
    prefix = m.group(1) + "." if m.group(1) else ""
    return prefix + m.group(2), prefix + m.group(4)


def sides(a, b, down):
    if down:
        if b[1] >= a[3] - 1:
            return "bottom", "top"
        if b[3] <= a[1] + 1:
            return "top", "bottom"
    else:
        if b[0] >= a[2] - 1:
            return "right", "left"
        if b[2] <= a[0] + 1:
            return "left", "right"
    if down:
        return ("right", "left") if (a[0] + a[2]) < (b[0] + b[2]) else ("left", "right")
    return ("bottom", "top") if (a[1] + a[3]) < (b[1] + b[3]) else ("top", "bottom")


NORMAL = {"top": (0, -1), "bottom": (0, 1), "left": (-1, 0), "right": (1, 0)}


def center(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def ports(edges, boxes):
    slots = {}
    for i, (src, dst, s_side, d_side) in enumerate(edges):
        slots.setdefault((src, s_side), []).append((i, 0, center(boxes[dst])))
        slots.setdefault((dst, d_side), []).append((i, 1, center(boxes[src])))
    result = {}
    for (name, side), items in slots.items():
        b = boxes[name]
        horizontal = side in ("top", "bottom")
        items.sort(key=lambda it: it[2][0] if horizontal else it[2][1])
        length = (b[2] - b[0]) if horizontal else (b[3] - b[1])
        gap = min(70, length * 0.7 / max(len(items), 1))
        cx, cy = center(b)
        for k, (i, end, _) in enumerate(items):
            off = (k - (len(items) - 1) / 2) * gap
            if side == "top":
                p = (cx + off, b[1])
            elif side == "bottom":
                p = (cx + off, b[3])
            elif side == "left":
                p = (b[0], cy + off)
            else:
                p = (b[2], cy + off)
            result[(i, end)] = p
    return result


def related(name, other):
    return name == other or other.startswith(name + ".") or name.startswith(other + ".")


def arc(p0, p3, bow):
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    px, py = -dy / length * bow, dx / length * bow
    c1 = (p0[0] + dx / 3 + px, p0[1] + dy / 3 + py)
    c2 = (p0[0] + dx * 2 / 3 + px, p0[1] + dy * 2 / 3 + py)
    return c1, c2


def hits(p0, c1, c2, p3, obstacles):
    for k in range(1, 40):
        t = k / 40
        u = 1 - t
        x = u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p3[0]
        y = u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p3[1]
        for b in obstacles:
            if b[0] - 10 < x < b[2] + 10 and b[1] - 10 < y < b[3] + 10:
                return True
    return False


def route(p0, p3, base, obstacles):
    for extra in (0, 60, -60, 120, -120, 180, -180, 260, -260):
        c1, c2 = arc(p0, p3, base + extra)
        if not hits(p0, c1, c2, p3, obstacles):
            return c1, c2
    return arc(p0, p3, base)


def edge_groups(svg, boxes):
    groups = []
    for m in re.finditer(r'<g class="([A-Za-z0-9+/=]+)">(.*?)</g>', svg, re.S):
        label = html.unescape(base64.b64decode(m.group(1)).decode())
        pair = parse_edge(label)
        if pair and pair[0] in boxes and pair[1] in boxes and "connection" in m.group(2):
            groups.append((m, pair))
    return groups


def smooth(path, down, bend):
    svg = open(path).read()
    boxes = read_boxes(svg)
    groups = edge_groups(svg, boxes)
    edges = []
    for _, (src, dst) in groups:
        s_side, d_side = sides(boxes[src], boxes[dst], down)
        edges.append((src, dst, s_side, d_side))
    pts = ports(edges, boxes)
    pairs = {}
    for i, (src, dst, _, _) in enumerate(edges):
        pairs.setdefault(tuple(sorted((src, dst))), []).append(i)
    pair_bow = {}
    for members in pairs.values():
        mids = {i: ((pts[(i, 0)][0] + pts[(i, 1)][0]) / 2, (pts[(i, 0)][1] + pts[(i, 1)][1]) / 2) for i in members}
        cx = sum(m[0] for m in mids.values()) / len(members)
        cy = sum(m[1] for m in mids.values()) / len(members)
        for i in members:
            if len(members) == 1:
                dx, dy = pts[(i, 1)][0] - pts[(i, 0)][0], pts[(i, 1)][1] - pts[(i, 0)][1]
                sign = (1 if dx * dy > 0 else -1) * (-1 if down else 1)
                pair_bow[i] = 0 if abs(dx) < 20 or abs(dy) < 20 else sign * bend * (dx * dx + dy * dy) ** 0.5
                continue
            dx, dy = pts[(i, 1)][0] - pts[(i, 0)][0], pts[(i, 1)][1] - pts[(i, 0)][1]
            side = -dy * (mids[i][0] - cx) + dx * (mids[i][1] - cy)
            pair_bow[i] = 55 if side >= 0 else -55

    holes = []
    out = svg
    for i, (m, _) in enumerate(groups):
        body = m.group(2)
        src, dst, s_side, d_side = edges[i]
        n0, n3 = NORMAL[s_side], NORMAL[d_side]
        start_pad = 3 if "marker-start" in body else 0
        p0 = (pts[(i, 0)][0] + n0[0] * start_pad, pts[(i, 0)][1] + n0[1] * start_pad)
        p3 = (pts[(i, 1)][0] + n3[0] * 3, pts[(i, 1)][1] + n3[1] * 3)
        obstacles = [b for name, b in boxes.items() if not related(name, src) and not related(name, dst)]
        c1, c2 = route(p0, p3, pair_bow[i], obstacles)
        d = "M %.2f %.2f C %.2f %.2f %.2f %.2f %.2f %.2f" % (*p0, *c1, *c2, *p3)
        new = re.sub(r'(<path d=")[^"]+(" stroke="[^"]+" fill="none" class="connection)', r"\g<1>" + d + r"\g<2>", body, count=1)

        text = re.search(r'<text x="([-\d.]+)" y="([-\d.]+)"', new)
        if text:
            tx, ty = float(text.group(1)), float(text.group(2))
            mx = (p0[0] + 3 * c1[0] + 3 * c2[0] + p3[0]) / 8
            my = (p0[1] + 3 * c1[1] + 3 * c2[1] + p3[1]) / 8
            lines = new.count("<tspan")
            dx, dy = mx - tx, my - ty + 5 - max(lines - 1, 0) * 9
            new = re.sub(r'(<(?:text|tspan) x=")([-\d.]+)"', lambda t: '%s%.2f"' % (t.group(1), float(t.group(2)) + dx), new)
            new = new.replace('<text x="%.2f" y="%s"' % (tx + dx, text.group(2)), '<text x="%.2f" y="%.2f"' % (tx + dx, ty + dy), 1)
            words = re.findall(r">([^<>]+)</(?:tspan|text)>", new)
            width = max(len(w) for w in words) * 8 + 10
            height = max(lines, 1) * 19 + 6
            holes.append('<rect x="%.2f" y="%.2f" width="%d" height="%d" fill="black"></rect>' % (mx - width / 2, my - height / 2, width, height))
        out = out.replace(body, new, 1)
    out = re.sub(r'<rect x="[^"]+" y="[^"]+" width="[^"]+" height="[^"]+" fill="black"></rect>\n?', "", out)
    out = out.replace("</mask>", "\n".join(holes) + "\n</mask>", 1)
    open(path, "w").write(out)


if __name__ == "__main__":
    bend = float(sys.argv[sys.argv.index("--bend") + 1]) if "--bend" in sys.argv else 0
    smooth(sys.argv[1], sys.argv[2] == "down", bend)
