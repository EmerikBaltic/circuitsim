"""Script to create 3 LED symbol candidate variants and render the comparison preview sheet."""

import os
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

VARIANT_A_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 40" width="80" height="40">
  <!-- Variant A: Circular dome case with prominent cathode flat cut -->
  <!-- Anode lead stub -->
  <line x1="0" y1="20" x2="26" y2="20" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Diode Triangle (Anode -> Cathode) -->
  <polygon points="26,11 26,29 44,20" stroke="#000000" stroke-width="2" fill="none" stroke-linejoin="round"/>
  <!-- Cathode Bar -->
  <line x1="44" y1="9" x2="44" y2="31" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Cathode lead stub -->
  <line x1="44" y1="20" x2="80" y2="20" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Case outline: circle centered at (36, 20), R=17, with vertical flat on cathode side at x=50 -->
  <path d="M 50,10.4 A 17,17 0 1 0 50,29.6" stroke="#000000" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line id="cathode_flat" x1="50" y1="10.4" x2="50" y2="29.6" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Light emission arrows -->
  <line x1="41" y1="10" x2="50" y2="3" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <polyline points="45,3 50,3 50,8" stroke="#000000" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="47" y1="12" x2="56" y2="5" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <polyline points="51,5 56,5 56,10" stroke="#000000" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

VARIANT_B_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 40" width="80" height="40">
  <!-- Variant B: Lens/dome case with vertical cathode flat at x=52 and upper-right arrows -->
  <!-- Anode lead stub -->
  <line x1="0" y1="20" x2="27" y2="20" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Diode Triangle (Anode -> Cathode) -->
  <polygon points="27,12 27,28 43,20" stroke="#000000" stroke-width="2" fill="none" stroke-linejoin="round"/>
  <!-- Cathode Bar -->
  <line x1="43" y1="10" x2="43" y2="30" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Cathode lead stub -->
  <line x1="43" y1="20" x2="80" y2="20" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Case outline: circle centered at (37, 20), R=16, flat on cathode side at x=51.5 -->
  <path d="M 51.5,13.3 A 16,16 0 1 0 51.5,26.7" stroke="#000000" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line id="cathode_flat" x1="51.5" y1="13.3" x2="51.5" y2="26.7" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Light emission arrows -->
  <line x1="39" y1="9" x2="48" y2="2" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <polyline points="44,2 48,2 48,6" stroke="#000000" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="46" y1="10" x2="55" y2="3" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <polyline points="51,3 55,3 55,7" stroke="#000000" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

VARIANT_C_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 40" width="80" height="40">
  <!-- Variant C: Extended package outline with flat rim cut at x=53 -->
  <!-- Anode lead stub -->
  <line x1="0" y1="20" x2="25" y2="20" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Diode Triangle (Anode -> Cathode) -->
  <polygon points="25,10 25,30 45,20" stroke="#000000" stroke-width="2" fill="none" stroke-linejoin="round"/>
  <!-- Cathode Bar -->
  <line x1="45" y1="8" x2="45" y2="32" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Cathode lead stub -->
  <line x1="45" y1="20" x2="80" y2="20" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Case outline: circle centered at (37, 20), R=18, flat at x=53 (dy=10) -->
  <path d="M 53,11.8 A 18,18 0 1 0 53,28.2" stroke="#000000" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line id="cathode_flat" x1="53" y1="11.8" x2="53" y2="28.2" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <!-- Light emission arrows -->
  <line x1="43" y1="8" x2="53" y2="1" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <polyline points="48,1 53,1 53,6" stroke="#000000" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="49" y1="10" x2="59" y2="3" stroke="#000000" stroke-width="2" stroke-linecap="round"/>
  <polyline points="54,3 59,3 59,8" stroke="#000000" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

LED_JSON = """{
  "id": "led",
  "display_name": "LED",
  "category": "Semiconductors",
  "style": "iec",
  "grid_size": [4, 2],
  "terminals": [
    {"name": "anode", "grid_pos": [-2, 0]},
    {"name": "cathode", "grid_pos": [2, 0]}
  ],
  "label_offset": [0, -1.2],
  "value_offset": [0, 1.2],
  "default_svg": "led.svg",
  "states": {}
}
"""

def main():
    cand_dir = Path("src/circuitsim/resources/symbols/iec/candidates")
    cand_dir.mkdir(parents=True, exist_ok=True)
    
    (cand_dir / "led_variant_a.svg").write_text(VARIANT_A_SVG, encoding="utf-8")
    (cand_dir / "led_variant_b.svg").write_text(VARIANT_B_SVG, encoding="utf-8")
    (cand_dir / "led_variant_c.svg").write_text(VARIANT_C_SVG, encoding="utf-8")
    
    # Install Variant A as the default active symbol
    iec_dir = Path("src/circuitsim/resources/symbols/iec")
    (iec_dir / "led.svg").write_text(VARIANT_A_SVG, encoding="utf-8")
    (iec_dir / "led.json").write_text(LED_JSON, encoding="utf-8")
    print("Installed Variant A to src/circuitsim/resources/symbols/iec/led.svg and led.json")

    # Render preview sheet to docs/design/led_variants.png in both themes
    docs_dir = Path("docs/design")
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    app = QApplication.instance() or QApplication([])

    # Preview sheet layout:
    # 3 columns (Variant A, Variant B, Variant C)
    # 2 rows (Dark Theme, Light Theme)
    # Each cell: 240 x 140 px (symbol scaled 2x to 160 x 80 px)
    width = 820
    height = 380
    sheet = QImage(width, height, QImage.Format.Format_ARGB32)
    sheet.fill(QColor("#161B22"))  # Overall sheet dark neutral background

    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    variants = [
        ("Variant A (Default)", VARIANT_A_SVG),
        ("Variant B (Compact Lens)", VARIANT_B_SVG),
        ("Variant C (Large Package)", VARIANT_C_SVG),
    ]

    themes = [
        ("Dark Theme", "#0D1117", "#E6EDF3", 50),
        ("Light Theme", "#FFFFFF", "#1F2328", 200),
    ]

    title_font = QFont("Segoe UI", 12, QFont.Weight.Bold)
    sub_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
    info_font = QFont("Segoe UI", 8)

    # Title
    p.setFont(title_font)
    p.setPen(QColor("#F0F6FC"))
    p.drawText(QRectF(0, 10, width, 30), Qt.AlignmentFlag.AlignCenter, "LED Schematic Symbol Candidates (IEC 60617 with Cathode Flat)")

    for r_idx, (t_name, bg_col, stroke_col, y_offset) in enumerate(themes):
        # Row label
        p.setFont(sub_font)
        p.setPen(QColor("#8B949E"))
        p.drawText(25, y_offset + 55, t_name)

        for c_idx, (v_name, svg_text) in enumerate(variants):
            x_box = 130 + c_idx * 220
            y_box = y_offset
            box_w = 200
            box_h = 120

            # Cell background card
            p.setPen(QPen(QColor("#30363D"), 1.0))
            p.setBrush(QColor(bg_col))
            p.drawRoundedRect(QRectF(x_box, y_box, box_w, box_h), 6.0, 6.0)

            # Draw light grid lines inside card
            grid_pen = QPen(QColor("#21262D" if "Dark" in t_name else "#E1E4E8"), 1.0)
            p.setPen(grid_pen)
            cx = x_box + box_w / 2.0
            cy = y_box + box_h / 2.0 + 8.0
            for gx in range(-80, 81, 20):
                p.drawLine(QPointF(cx + gx, cy - 35), QPointF(cx + gx, cy + 35))
            for gy in range(-30, 31, 20):
                p.drawLine(QPointF(cx - 90, cy + gy), QPointF(cx + 90, cy + gy))

            # Header inside cell
            p.setFont(info_font)
            p.setPen(QColor("#8B949E" if "Dark" in t_name else "#57606A"))
            p.drawText(QRectF(x_box, y_box + 4, box_w, 18), Qt.AlignmentFlag.AlignCenter, v_name)

            # Recolour SVG stroke for theme
            recoloured_svg = svg_text.replace('#000000', stroke_col)
            svg_data = recoloured_svg.encode('utf-8')

            renderer = QSvgRenderer(svg_data)
            # Render symbol at 2x scale (160 x 80 px)
            sym_rect = QRectF(cx - 80, cy - 40, 160, 80)
            renderer.render(p, sym_rect)

            # Terminal dots (A and K)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#58A6FF"))
            p.drawEllipse(QPointF(cx - 80, cy), 3.5, 3.5)
            p.drawEllipse(QPointF(cx + 80, cy), 3.5, 3.5)

            # Terminal tags
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.setPen(QColor("#58A6FF"))
            p.drawText(QPointF(cx - 72, cy - 6), "A")
            p.drawText(QPointF(cx + 62, cy - 6), "K")

    p.end()
    out_path = docs_dir / "led_variants.png"
    sheet.save(str(out_path))
    print(f"Saved preview sheet to {out_path.resolve()}")

if __name__ == "__main__":
    main()
