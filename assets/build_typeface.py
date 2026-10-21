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

import fontTools.ttLib as ttLib
from fontTools.colorLib.builder import buildCOLR, buildCPAL

BASE_DIR = Path(__file__).resolve().parent
SVGS_DIR = BASE_DIR / "svgs"
OUTPUT_TTF = BASE_DIR / "BRUNOMA_TYPEFACE.ttf"
MAPPING_JSON = BASE_DIR / "glyphs.json"
TXT_MAPPING = SVGS_DIR / "mapeamento-icones.txt"
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
            glyph.correctDirection()
            glyph.round()
            glyph.autoHint()
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

    # Injeção de tabelas OpenType COLR / CPAL para ícones coloridos por padrão
    try:
        tt = ttLib.TTFont(str(OUTPUT_TTF))
        palette = [
            (217 / 255.0, 119 / 255.0, 87 / 255.0, 1.0),   # 0: Claude Laranja (#D97757)
            (37 / 255.0, 226 / 255.0, 141 / 255.0, 1.0),   # 1: OpenAI Verde Claro (#25E28D)
            (49 / 255.0, 134 / 255.0, 255 / 255.0, 1.0),   # 2: Antigravity Azul Google (#3186FF)
        ]
        color_glyphs = {}
        if "CLAUDE_LARANJA" in tt["glyf"]:
            color_glyphs["CLAUDE_LARANJA"] = [("CLAUDE_LARANJA", 0)]
        if "openai_black_vazado" in tt["glyf"]:
            color_glyphs["openai_black_vazado"] = [("openai_black_vazado", 1)]
        if "AGY_CLI" in tt["glyf"]:
            color_glyphs["AGY_CLI"] = [("AGY_CLI", 2)]

        tt["CPAL"] = buildCPAL([palette])
        tt["COLR"] = buildCOLR(color_glyphs, version=0)
        tt.save(str(OUTPUT_TTF))
        tt.close()
        print("[OK] Tabelas OpenType COLR/CPAL injetadas com sucesso (Cores dos glifos ativadas)!")
    except Exception as e:
        print(f"[!] Falha ao injetar COLR/CPAL: {e}", file=sys.stderr)

    # Salva o mapa de caracteres em JSON
    with open(MAPPING_JSON, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    print(f"[OK] Mapa exportado para {MAPPING_JSON.name}")

    # Salva o arquivo de transcrição textual de mapeamento na raiz da pasta svgs
    with open(TXT_MAPPING, "w", encoding="utf-8") as f:
        f.write("MAPEAMENTO DE ÍCONES COMPILADOS - BRUNOMA TYPEFACE\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"{'ÍCONE / NOME':<24} | {'UNICODE':<8} | {'ESCAPE':<8} | {'ARQUIVO SVG'}\n")
        f.write("-" * 70 + "\n")
        for name, data in mapping.items():
            f.write(f"{name:<24} | {data['codepoint']:<8} | {data['unicode_escape']:<8} | {data['file']}\n")
        f.write("\n" + "=" * 70 + "\n")
        f.write("COMO USAR:\n")
        f.write("1. Python / Scripts:\n")
        f.write("   icone = chr(0xE000)  # ou \"\\ue000\"\n")
        f.write("2. Hyprland / Kitty / Sistema:\n")
        f.write("   O Fontconfig faz fallback automático para 'BRUNOMA TYPEFACE' ao encontrar o código.\n")
    print(f"[OK] Mapeamento textual exportado para svgs/{TXT_MAPPING.name}")

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
