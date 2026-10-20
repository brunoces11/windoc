#!/usr/bin/env python3
"""
Compilador de Fonte de Ícones Sob Demanda para WinDoc (BRUNOMA TYPEFACE).
Varre a pasta 'svgs/', importa os vetores SVG para glifos TrueType (PUA: U+E000 em diante),
gera BRUNOMA_TYPEFACE.ttf, atualiza o cache do sistema e exporta glyphs.json.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import fontforge
except ImportError:
    print("[ERRO] fontforge não encontrado. Instale com: sudo pacman -S fontforge", file=sys.stderr)
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent
SVGS_DIR = BASE_DIR / "svgs"
OUTPUT_TTF = BASE_DIR / "BRUNOMA_TYPEFACE.ttf"
MAPPING_JSON = BASE_DIR / "glyphs.json"
USER_FONTS_DIR = Path.home() / ".local/share/fonts"


def build():
    svg_files = sorted(SVGS_DIR.glob("*.svg"))
    if not svg_files:
        print(f"[AVISO] Nenhum arquivo .svg encontrado em {SVGS_DIR}")
        return

    font = fontforge.font()
    font.fontname = "BRUNOMA-TYPEFACE"
    font.familyname = "BRUNOMA TYPEFACE"
    font.fullname = "BRUNOMA TYPEFACE Regular"
    font.version = "1.0"
    font.em = 1000

    # Espaço padrão
    sp = font.createChar(0x20, "space")
    sp.width = 500

    start_codepoint = 0xE000
    mapping = {}

    print(f"[+] Compilando {len(svg_files)} ícone(s) SVG em {OUTPUT_TTF.name}...")

    for i, svg_path in enumerate(svg_files):
        codepoint = start_codepoint + i
        glyph_name = svg_path.stem
        glyph = font.createChar(codepoint, glyph_name)
        try:
            glyph.importOutlines(str(svg_path))
            glyph.width = 1000
            char_hex = f"U+{codepoint:04X}"
            mapping[glyph_name] = {
                "name": glyph_name,
                "codepoint": char_hex,
                "unicode_escape": f"\\u{codepoint:04x}",
                "file": svg_path.name,
            }
            print(f"  - {glyph_name:20} -> {char_hex} ({svg_path.name})")
        except Exception as e:
            print(f"  [!] Falha ao importar {svg_path.name}: {e}", file=sys.stderr)

    font.generate(str(OUTPUT_TTF))
    font.close()

    # Salva o mapa de caracteres
    with open(MAPPING_JSON, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    print(f"[OK] Mapa exportado para {MAPPING_JSON.name}")

    # Atualiza o cache de fontes do usuário
    USER_FONTS_DIR.mkdir(parents=True, exist_ok=True)
    symlink_target = USER_FONTS_DIR / "BRUNOMA_TYPEFACE.ttf"
    if symlink_target.exists() or symlink_target.is_symlink():
        symlink_target.unlink()
    symlink_target.symlink_to(OUTPUT_TTF)

    subprocess.run(["fc-cache", "-f", str(USER_FONTS_DIR)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("[OK] Fonte instalada em ~/.local/share/fonts/ e cache recarregado!")
    print("\nPara usar no Python ou no agy-title-daemon:")
    for name, data in mapping.items():
        print(f"  {name:15}: chr(0x{data['codepoint'][2:]})  -> \"{data['unicode_escape']}\"")


if __name__ == "__main__":
    build()
