from collections import Counter

from PIL import Image

src = Image.open(r"C:\Users\think\AppData\Local\Temp\windows-computer-use-073c7dece95d4492875688a313f9bfae.png").convert("RGB")
w, h = src.size

# 找有彩度的颜色（蓝色系/强调色）
sat = Counter()
for y in range(0, h, 4):
    for x in range(0, w, 4):
        r, g, b = src.getpixel((x, y))
        mx, mn = max(r, g, b), min(r, g, b)
        if mx - mn > 24 and mx > 90:
            sat[(r // 8 * 8, g // 8 * 8, b // 8 * 8)] += 1

print("colored buckets:")
for color, count in sat.most_common(12):
    print(f"  #{color[0]:02x}{color[1]:02x}{color[2]:02x}  {count}")

# 用户气泡区域：预览 (450..530, 450..480) -> 源坐标
def sample_box(name, x0, y0, x1, y1):
    sx, sy = w / 1440.0, h / 860.0
    box = src.crop((int(x0 * sx), int(y0 * sy), int(x1 * sx), int(y1 * sy)))
    colors = Counter(box.getdata())
    top = colors.most_common(3)
    print(f"{name}: " + "  ".join(f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}({n})" for c, n in top))

sample_box("user_bubble", 448, 452, 530, 478)
sample_box("send_area", 845, 812, 880, 840)
sample_box("card_area", 320, 230, 890, 420)
sample_box("sidebar_bottom", 10, 820, 220, 850)