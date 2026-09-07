from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path.cwd()
SIEWEB = ROOT / "sieweb.py"
SERVER = ROOT / "server_core.py"
VERSION = ROOT / "VERSION.txt"

for p in (SIEWEB, SERVER, VERSION):
    if not p.exists():
        raise SystemExit(
            f"ERROR: no encuentro {p.name}. Ejecuta este archivo desde la raíz del repositorio santa-rita-escolar."
        )

version = VERSION.read_text(encoding="utf-8").strip()
allowed = {"0.8.7", "0.8.8", "0.8.9", "0.8.10", "0.8.11", "0.8.12"}
if version not in allowed:
    raise SystemExit(
        f"ERROR: versión inesperada {version!r}; no aplicaré el hotfix a ciegas. Versiones admitidas: {sorted(allowed)}"
    )

for p in (SIEWEB, SERVER, VERSION):
    backup = p.with_suffix(p.suffix + ".bak-v0.8.12-nivel-logro")
    if not backup.exists():
        shutil.copy2(p, backup)


def find_matching_paren(text: str, open_pos: int) -> int:
    """Devuelve la posición del ')' que cierra el '(' en open_pos, ignorando strings y comentarios simples."""
    if open_pos < 0 or open_pos >= len(text) or text[open_pos] != "(":
        raise ValueError("open_pos no apunta a '('")
    depth = 0
    i = open_pos
    quote = None
    triple = False
    escaped = False
    while i < len(text):
        ch = text[i]
        nxt3 = text[i:i+3]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif triple and nxt3 == quote * 3:
                i += 2
                quote = None
                triple = False
            elif not triple and ch == quote:
                quote = None
            i += 1
            continue
        if nxt3 in ("'''", '\"\"\"'):
            quote = nxt3[0]
            triple = True
            i += 3
            continue
        if ch in ("'", '"'):
            quote = ch
            triple = False
            i += 1
            continue
        if ch == "#":
            nl = text.find("\n", i)
            if nl == -1:
                return -1
            i = nl + 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


# -----------------------------------------------------------------------------
# 1) Compatibilidad v0.8.7: objNG debe usar arrNivelGrado nativo, no arrNGS.
#    Reutiliza la corrección segura introducida en v0.8.8 si aún no existe.
# -----------------------------------------------------------------------------
s = SIEWEB.read_text(encoding="utf-8")

if "def resolve_grade_write_scope(" not in s:
    helper = r'''
    @classmethod
    def _normalize_native_nivel_grado(cls, value: Any, *, source: str) -> list[dict[str, str]]:
        """Normaliza únicamente el contrato nativo arrNivelGrado de SIEweb."""
        raw = value
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                raw = None
            else:
                try:
                    raw = json.loads(text)
                except ValueError as exc:
                    raise SieWebError(
                        f"{source} debe ser JSON válido con arrNivelGrado; no se envió nada."
                    ) from exc
        if isinstance(raw, dict):
            nested = cls._dict_get_ci(raw, "arrNivelGrado")
            raw = nested if nested is not None else [raw]
        if not isinstance(raw, list) or not raw:
            raise SieWebError(
                f"{source} no contiene arrNivelGrado nativo; no se enviará objNG."
            )
        out: list[dict[str, str]] = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise SieWebError(
                    f"{source}[{index}] no es un objeto de nivel/grado; no se envió nada."
                )
            n = cls._dict_get_ci(item, "n")
            g = cls._dict_get_ci(item, "g")
            if n in (None, "") or g in (None, ""):
                raise SieWebError(
                    f"{source}[{index}] debe contener n y g; no se envió nada."
                )
            out.append({"n": str(n).strip(), "g": str(g).strip()})
        return out

    @classmethod
    def _normalize_ngs_selector(cls, value: Any) -> list[str]:
        """Normaliza arrNGS solo como selector de sección; nunca como objNG."""
        raw = value
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return []
            if text[:1] in {"[", "{", '"'}:
                try:
                    raw = json.loads(text)
                except ValueError:
                    raw = text
        if isinstance(raw, dict):
            nested = cls._dict_get_ci(raw, "arrNGS")
            raw = nested if nested is not None else []
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        return [
            str(item).strip().upper()
            for item in raw
            if isinstance(item, str) and str(item).strip()
        ]

    def resolve_grade_write_scope(self, summary: dict[str, Any], supplied: Any = None) -> list[dict[str, str]]:
        """Usa infoClasePeriodo.arrNivelGrado como fuente autoritativa para objNG."""
        class_info = summary.get("class") or {}
        native = self._normalize_native_nivel_grado(
            class_info.get("arrNivelGrado"), source="infoClasePeriodo.arrNivelGrado"
        )
        native_ngs = self._normalize_ngs_selector(class_info.get("arrNGS"))
        if supplied in (None, "", [], {}):
            return native
        decoded = supplied
        if isinstance(decoded, str):
            text = decoded.strip()
            try:
                decoded = json.loads(text)
            except ValueError:
                decoded = text
        supplied_ngs = self._normalize_ngs_selector(decoded)
        if supplied_ngs:
            if native_ngs and supplied_ngs != native_ngs:
                raise SieWebError(
                    "PROTECCIÓN DE CONTEXTO SIEWEB: arrNGS solicitado no coincide con la sección del registro. No se envió nada."
                )
            return native
        candidate = self._normalize_native_nivel_grado(decoded, source="section_ng/objNG solicitado")
        if candidate != native:
            raise SieWebError(
                "PROTECCIÓN DE CONTEXTO SIEWEB: objNG solicitado no coincide con infoClasePeriodo.arrNivelGrado. No se envió nada."
            )
        return native

'''
    marker = "    def update_grades("
    if marker not in s:
        raise SystemExit("ERROR: no encuentro update_grades en sieweb.py; no modificaré nada.")
    s = s.replace(marker, helper + marker, 1)

# Asegura que update_grades normalice objNG.
if '"objNG": obj_ng' not in s:
    old_payload = '''        payload = {
            "ano": year,
            "cursocod": course_code,
            "idClasePeriodo": class_period_id,
            "objNG": section_ng,
            "periodo": period,
            "registros": records,
        }'''
    new_payload = '''        obj_ng = self._normalize_native_nivel_grado(section_ng, source="objNG")
        payload = {
            "ano": year,
            "cursocod": course_code,
            "idClasePeriodo": class_period_id,
            "objNG": obj_ng,
            "periodo": period,
            "registros": records,
        }'''
    if old_payload not in s:
        raise SystemExit("ERROR: no pude localizar el payload de update_grades para normalizar objNG.")
    s = s.replace(old_payload, new_payload, 1)

# Asegura arrNivelGrado en el resumen de clase.
if '"arrNivelGrado": self._dict_get_ci(info,"arrNivelGrado"),' not in s:
    old_line = '                "arrNGS": self._dict_get_ci(info,"arrNGS","NGS"),'
    if old_line not in s:
        raise SystemExit("ERROR: no encuentro arrNGS en summarize_gradebook; no modificaré nada.")
    s = s.replace(
        old_line,
        '                "arrNivelGrado": self._dict_get_ci(info,"arrNivelGrado"),\n' + old_line,
        1,
    )

# -----------------------------------------------------------------------------
# 2) Refuerza save_grades_verified: si se abre Nivel de logro, SOLO admite
#    registros nivelEva=1, cabecera exacta y notas A/B/C.
# -----------------------------------------------------------------------------
start = s.find("    def save_grades_verified(")
end = s.find("    def save_grades_multi_verified(", start + 1)
if start == -1 or end == -1 or end <= start:
    raise SystemExit("ERROR: no pude delimitar save_grades_verified en sieweb.py.")
block = s[start:end]

if "HF12_NIVEL_LOGRO_VALIDATION" not in block:
    call_token = "records = self.build_grade_records("
    call_pos = block.find(call_token)
    if call_pos == -1:
        raise SystemExit("ERROR: no encuentro build_grade_records dentro de save_grades_verified.")
    open_pos = block.find("(", call_pos)
    close_pos = find_matching_paren(block, open_pos)
    if close_pos == -1:
        raise SystemExit("ERROR: no pude encontrar el cierre de build_grade_records.")
    line_end = block.find("\n", close_pos)
    if line_end == -1:
        line_end = close_pos + 1
    validation = r'''
        # HF12_NIVEL_LOGRO_VALIDATION
        # protect_achievement_level=False NO desactiva la seguridad global:
        # abre exclusivamente Nivel de logro (nivelEva=1) y solo A/B/C.
        if not protect_achievement_level:
            if not records:
                raise SieWebError(
                    "PROTECCIÓN NIVEL DE LOGRO HF12: no se generaron registros; no se envió nada."
                )
            for _rec in records:
                _lvl = self._dict_get_ci(_rec, "nivelEva", "NIVEL", "nivel")
                _hid = self._dict_get_ci(_rec, "idCabecera", "ID_CABECERA", "header_id")
                _grade = self._dict_get_ci(_rec, "notaNue", "NOTANUE", "nota", "grade")
                _grade = str(_grade or "").strip().upper()
                if str(_lvl) != "1":
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: el destino no es nivelEva=1 (nivel={_lvl!r}); no se envió nada."
                    )
                if str(_hid) != str(header_id):
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: cabecera inesperada {_hid!r} != {header_id!r}; no se envió nada."
                    )
                if _grade not in {"A", "B", "C"}:
                    raise SieWebError(
                        f"PROTECCIÓN NIVEL DE LOGRO HF12: nota {_grade!r} no válida; solo A/B/C. No se envió nada."
                    )
'''
    block = block[:line_end+1] + validation + block[line_end+1:]

# Asegura objNG nativo dentro de save_grades_verified.
if "native_obj_ng = self.resolve_grade_write_scope(before, section_ng)" not in block:
    guard = re.search(
        r"if protect_achievement_level:\n\s+self\.assert_performance_target\(before, header_id=header_id, performance_level=performance_level\)\n",
        block,
    )
    if not guard:
        raise SystemExit("ERROR: no encuentro la guarda protect_achievement_level esperada.")
    insert_at = guard.end()
    block = block[:insert_at] + "        native_obj_ng = self.resolve_grade_write_scope(before, section_ng)\n" + block[insert_at:]

# Cambia solo el primer section_ng de la llamada de escritura dentro de este método.
if "section_ng=native_obj_ng" not in block:
    needle = "            section_ng=section_ng,\n"
    if needle not in block:
        raise SystemExit("ERROR: no encuentro section_ng=section_ng en save_grades_verified.")
    block = block.replace(needle, "            section_ng=native_obj_ng,\n", 1)

s = s[:start] + block + s[end:]
SIEWEB.write_text(s, encoding="utf-8")

# -----------------------------------------------------------------------------
# 3) server_core: allow_achievement_level=true habilita SOLO el flujo anterior.
#    El action sigue siendo save_grades_verified; no se abre update_grades.
# -----------------------------------------------------------------------------
server = SERVER.read_text(encoding="utf-8")

# Localiza la llamada real al cliente dentro del manejador de save_grades_verified.
occurrences = [m.start() for m in re.finditer(r"\.save_grades_verified\(", server)]
if len(occurrences) != 1:
    raise SystemExit(
        f"ERROR: esperaba una única llamada .save_grades_verified( en server_core.py y encontré {len(occurrences)}. No modificaré a ciegas."
    )
call_pos = occurrences[0]
open_pos = server.find("(", call_pos)
close_pos = find_matching_paren(server, open_pos)
if close_pos == -1:
    raise SystemExit("ERROR: no pude delimitar la llamada save_grades_verified en server_core.py.")
call_block = server[call_pos:close_pos+1]

kw = 'protect_achievement_level=not bool(p.get("allow_achievement_level", False))'
if kw not in call_block:
    # Reemplaza un valor fijo si existe; de lo contrario inserta el keyword al final.
    fixed_pat = re.compile(r"protect_achievement_level\s*=\s*(?:True|False)")
    if fixed_pat.search(call_block):
        call_block2 = fixed_pat.sub(kw, call_block, count=1)
    else:
        # Conserva la coma y el estilo del bloque.
        indent_match = re.search(r"\n([ \t]+)[A-Za-z_]\w*\s*=", call_block)
        indent = indent_match.group(1) if indent_match else "                "
        before_close = call_block[:-1]
        if before_close.rstrip().endswith(","):
            insertion = f'\n{indent}{kw},\n'
        else:
            insertion = f',\n{indent}{kw},\n'
        call_block2 = before_close + insertion + ")"
    server = server[:call_pos] + call_block2 + server[close_pos+1:]

# Actualiza la ayuda visible si encuentra la descripción conocida.
if "allow_achievement_level=true" not in server:
    marker = "Para notas nuevas prefiere save_grades_verified."
    addon = (
        " Para Nivel de logro (nivelEva=1), save_grades_verified admite "
        "payload_json allow_achievement_level=true; valida cabecera, nivelEva=1 y notas A/B/C antes de escribir."
    )
    if marker in server:
        server = server.replace(marker, marker + addon, 1)

SERVER.write_text(server, encoding="utf-8")
VERSION.write_text("0.8.12\n", encoding="utf-8")

# -----------------------------------------------------------------------------
# 4) Validaciones de compilación y presencia del hotfix.
# -----------------------------------------------------------------------------
s2 = SIEWEB.read_text(encoding="utf-8")
server2 = SERVER.read_text(encoding="utf-8")

assert "HF12_NIVEL_LOGRO_VALIDATION" in s2
assert 'if not protect_achievement_level:' in s2
assert '"A", "B", "C"' in s2
assert 'protect_achievement_level=not bool(p.get("allow_achievement_level", False))' in server2
assert '"objNG": obj_ng' in s2
assert '"arrNivelGrado": self._dict_get_ci(info,"arrNivelGrado"),' in s2

subprocess.run([sys.executable, "-m", "py_compile", str(SIEWEB), str(SERVER)], check=True)

print("OK: SIEROOM 0.8.12 aplicado.")
print("- save_grades_verified sigue protegido por defecto.")
print("- allow_achievement_level=true abre EXCLUSIVAMENTE nivelEva=1.")
print("- Solo permite A/B/C, valida idCabecera y usa objNG nativo arrNivelGrado.")
print("- update_grades de bajo nivel sigue bloqueado desde el MCP.")
print("- Reinicia/redeploya el servicio para que ChatGPT vea la nueva versión.")
