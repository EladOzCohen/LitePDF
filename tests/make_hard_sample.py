"""PDFs that stress text selection: Word-like Hebrew (visual order, each word its own object, scrambled stream)."""
import random
import sys
import pymupdf

out = sys.argv[1]
random.seed(7)
doc = pymupdf.open()
font = pymupdf.Font(fontfile="C:/Windows/fonts/arial.ttf")
page = doc.new_page(width=595, height=842)
tw = pymupdf.TextWriter(page.rect)

# --- page 1 area A: English paragraph, every word drawn separately in SHUFFLED stream order
words = ("The quick brown fox jumps over the lazy dog and keeps running through the green field "
         "until the evening comes and everybody goes home to rest").split()
x, y, items = 60, 100, []
for w in words:
    wd = font.text_length(w, fontsize=13)
    if x + wd > 535:
        x, y = 60, y + 20
    items.append((x, y, w))
    x += wd + font.text_length(" ", fontsize=13)
random.shuffle(items)
for (x, y, w) in items:
    page.insert_text((x, y), w, fontsize=13, fontname="arial", fontfile="C:/Windows/fonts/arial.ttf")

# --- area B: Hebrew paragraph laid out RIGHT to LEFT, words stored in VISUAL order (left->right), one object per word
heb = "זהו משפט ארוך בעברית שנכתב במסמך ויש בו הרבה מילים כדי לבדוק סימון על פני כמה שורות שלמות בלי בעיות".split()
x, y, lines, cur = 535, 300, [], []
for w in heb:
    wd = font.text_length(w, fontsize=13)
    if x - wd < 60:
        lines.append(cur); cur = []; x = 535
    cur.append((x - wd, w)); x -= wd + font.text_length(" ", fontsize=13)
lines.append(cur)
for i, ln in enumerate(lines):
    for (xx, w) in sorted(ln):                     # visual order: left to right
        page.insert_text((xx, 300 + i * 20), w[::-1], fontsize=13, fontname="arial", fontfile="C:/Windows/fonts/arial.ttf")
doc.save(out)
print("saved", out)
