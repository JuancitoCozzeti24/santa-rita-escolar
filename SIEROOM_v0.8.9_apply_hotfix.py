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
if version not in {"0.8.7", "0.8.8", "0.8.9"}:
    raise SystemExit(
        f"ERROR: versión inesperada {version!r}; no aplicaré el hotfix a ciegas."
    )

for p in (SIEWEB, SERVER, VERSION):
    backup = p.with_suffix(p.suffix + ".bak-v0.8.9-criteria-abbrev")
    if not backup.exists():
        shutil.copy2(p, backup)

s = SIEWEB.read_text(encoding="utf-8")

if "def upsert_criteria(" not in s:
    raise SystemExit(
        "ERROR: no encuentro el método nativo upsert_criteria de SIEweb. No aplicaré un parche inseguro."
    )

# Conserva la implementación v0.8.4 como fallback para creación normal.
if "def _upsert_criteria_verified_legacy(" not in s:
    s, n = re.subn(
        r"(?m)^    def upsert_criteria_verified\(",
        "    def _upsert_criteria_verified_legacy(",
        s,
        count=1,
    )
    if n != 1:
        raise SystemExit(
            "ERROR: no pude localizar upsert_criteria_verified en sieweb.py. No se modificó el archivo."
        )

hotfix = r'''
    @staticmethod
    def _criteria_hotfix_value(obj, *keys, default=None):
        if not isinstance(obj, dict):
            return default
        lower = {str(k).lower(): v for k, v in obj.items()}
        for key in keys:
            if key in obj:
                return obj[key]
            lk = str(key).lower()
            if lk in lower:
                return lower[lk]
        return default

    @classmethod
    def _criteria_hotfix_editor_nodes(cls, payload):
        """Aplana únicamente nodos reales del editor de criterios de SIEweb."""
        out = []

        def walk(value):
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return
            cid = cls._criteria_hotfix_value(value, "ID_CONTENIDO", "id")
            ccid = cls._criteria_hotfix_value(value, "ID_CLASE_CONTENIDO", "idClaseContenido")
            if cid not in (None, "") and ccid not in (None, ""):
                out.append(value)
            children = cls._criteria_hotfix_value(value, "children", default=[])
            if isinstance(children, list):
                walk(children)

        root = payload
        if isinstance(payload, dict):
            root = cls._criteria_hotfix_value(payload, "json", default=payload)
            if isinstance(root, dict):
                root = cls._criteria_hotfix_value(root, "resCriterios", default=root)
        walk(root)
        return out

    @classmethod
    def _criteria_hotfix_find_by_id(cls, payload, criterion_id):
        target = str(criterion_id)
        matches = []
        for node in cls._criteria_hotfix_editor_nodes(payload):
            cid = cls._criteria_hotfix_value(node, "ID_CONTENIDO", "id")
            if str(cid) == target:
                matches.append(node)
        if len(matches) != 1:
            return None, len(matches)
        return matches[0], 1

    @classmethod
    def _criteria_hotfix_norm_text(cls, value):
        return " ".join(str(value or "").strip().split())

    def _criteria_hotfix_native_replica(self, *, class_id, class_period_id, root_content_id, id_ambito):
        """Obtiene datosReplica del preflight si existe; para edición nunca replica a ciegas."""
        replica = {"replicar": False}
        preflight = getattr(self, "criteria_write_preflight", None)
        if not callable(preflight):
            return replica
        try:
            info = preflight(
                class_id=int(class_id),
                class_period_id=int(class_period_id),
                root_content_id=int(root_content_id),
                id_ambito=int(id_ambito),
            )
        except TypeError:
            # Algunas revisiones aceptan argumentos posicionales distintos. La edición
            # continúa sin replicación; el registro existente lleva sus IDs nativos.
            return replica
        except Exception:
            return replica
        if isinstance(info, dict):
            native = info.get("native_replica_context")
            if isinstance(native, dict):
                replica = dict(native)
                replica["replicar"] = False
        return replica

    def _criteria_hotfix_update_abbreviations_verified(
        self,
        *,
        class_id,
        class_period_id,
        root_content_id,
        id_ambito,
        changes,
    ):
        """Edita SOLO abreviaturas de desempeños existentes y verifica que no cree columnas nuevas."""
        before = self.get_criteria(
            class_id=int(class_id),
            class_period_id=int(class_period_id),
            root_content_id=int(root_content_id),
            id_ambito=int(id_ambito),
        )
        before_nodes = self._criteria_hotfix_editor_nodes(before)
        before_ids = [str(self._criteria_hotfix_value(n, "ID_CONTENIDO", "id")) for n in before_nodes]
        records = []
        operations = []

        for change in changes:
            cid = int(change["id"])
            node, count = self._criteria_hotfix_find_by_id(before, cid)
            if node is None:
                raise SieWebError(
                    f"PROTECCIÓN DE CRITERIOS: ID_CONTENIDO={cid} no existe de forma única (coincidencias={count}). No se envió nada."
                )

            program = self._criteria_hotfix_norm_text(
                self._criteria_hotfix_value(node, "DESCPROGRAMA", "programa")
            ).lower()
            level = self._criteria_hotfix_value(node, "NIVEL", "nivelEva")
            if program and program != "desempeño":
                raise SieWebError(
                    f"PROTECCIÓN DE CRITERIOS: ID_CONTENIDO={cid} no es un Desempeño. No se envió nada."
                )
            if level not in (None, "", 3, "3"):
                raise SieWebError(
                    f"PROTECCIÓN DE CRITERIOS: ID_CONTENIDO={cid} no está en nivel de desempeño. No se envió nada."
                )

            parent = int(self._criteria_hotfix_value(node, "ID_CONTENIDO_REF", "idpadre", default=0) or 0)
            expected_parent = change.get("parent_id")
            if expected_parent not in (None, "") and parent != int(expected_parent):
                raise SieWebError(
                    f"PROTECCIÓN DE CRITERIOS: el padre de {cid} cambió ({parent} != {expected_parent}). No se envió nada."
                )

            current_description = self._criteria_hotfix_norm_text(
                self._criteria_hotfix_value(node, "DESCRIPCION", "descripcion")
            )
            expected_description = self._criteria_hotfix_norm_text(change.get("description"))
            if expected_description and current_description != expected_description:
                raise SieWebError(
                    f"PROTECCIÓN DE CRITERIOS: la descripción de {cid} no coincide exactamente. No se envió nada."
                )

            desired_abbreviation = str(change.get("abbreviation") or "").strip()
            if not desired_abbreviation:
                raise SieWebError(
                    f"PROTECCIÓN DE CRITERIOS: abreviatura vacía para {cid}. No se envió nada."
                )
            if len(desired_abbreviation) > 80:
                raise SieWebError(
                    f"PROTECCIÓN DE CRITERIOS: abreviatura demasiado larga para {cid}. No se envió nada."
                )
            if desired_abbreviation.startswith("__"):
                raise SieWebError(
                    "PROTECCIÓN DE CRITERIOS: se bloquean abreviaturas/marcadores internos que empiezan por '__'."
                )

            current_abbreviation = str(
                self._criteria_hotfix_value(node, "ABREVIATURA", "abreviatura", default="") or ""
            ).strip()
            if current_abbreviation == desired_abbreviation:
                operations.append({
                    "action": "already-correct",
                    "idContenido": cid,
                    "abbreviation": desired_abbreviation,
                })
                continue

            record = dict(node)
            record.pop("children", None)
            record["ID_CLASE"] = int(class_id)
            record["ID_CLASE_PERIODO"] = int(class_period_id)
            record["ID_CONTENIDO"] = cid
            record["ID_CONTENIDO_REF"] = parent
            record["DESCRIPCION"] = current_description
            record["ORIGI"] = current_description
            record["ABREV_ORIGI"] = current_abbreviation
            record["ABREVIATURA"] = desired_abbreviation
            record["EDITOREG"] = 1
            record["flExiste"] = True
            records.append(record)
            operations.append({
                "action": "update-existing-abbreviation",
                "idContenido": cid,
                "from": current_abbreviation,
                "to": desired_abbreviation,
            })

        if not records:
            return {
                "saved": True,
                "already_present": True,
                "updated_existing": False,
                "operations": operations,
                "sent_record_count": 0,
                "protection": "abbreviation-only; no criteria created",
            }

        replica = self._criteria_hotfix_native_replica(
            class_id=class_id,
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            id_ambito=id_ambito,
        )
        write = self.upsert_criteria(
            class_id=int(class_id),
            records=records,
            replica=replica,
        )

        after = self.get_criteria(
            class_id=int(class_id),
            class_period_id=int(class_period_id),
            root_content_id=int(root_content_id),
            id_ambito=int(id_ambito),
        )
        after_nodes = self._criteria_hotfix_editor_nodes(after)
        after_ids = [str(self._criteria_hotfix_value(n, "ID_CONTENIDO", "id")) for n in after_nodes]
        if len(after_ids) != len(before_ids) or sorted(after_ids) != sorted(before_ids):
            raise SieWebError(
                "ALERTA DE INTEGRIDAD: la edición de abreviatura cambió la cantidad o los IDs de criterios. Revisa SIEweb; se bloquean nuevas operaciones."
            )

        verification = []
        for change in changes:
            cid = int(change["id"])
            desired = str(change.get("abbreviation") or "").strip()
            node, count = self._criteria_hotfix_find_by_id(after, cid)
            if node is None:
                raise SieWebError(
                    f"VERIFICACIÓN FALLIDA: el criterio {cid} dejó de ser único después del guardado (coincidencias={count})."
                )
            observed = str(
                self._criteria_hotfix_value(node, "ABREVIATURA", "abreviatura", default="") or ""
            ).strip()
            observed_description = self._criteria_hotfix_norm_text(
                self._criteria_hotfix_value(node, "DESCRIPCION", "descripcion")
            )
            expected_description = self._criteria_hotfix_norm_text(change.get("description"))
            if observed != desired:
                raise SieWebError(
                    f"VERIFICACIÓN FALLIDA: abreviatura de {cid}: {observed!r} != {desired!r}."
                )
            if expected_description and observed_description != expected_description:
                raise SieWebError(
                    f"VERIFICACIÓN FALLIDA: la descripción de {cid} fue modificada."
                )
            verification.append({
                "id": cid,
                "abbreviation": observed,
                "description_unchanged": True,
            })

        return {
            "saved": True,
            "updated_existing": True,
            "write": write,
            "operations": operations,
            "verification": verification,
            "sent_record_count": len(records),
            "protection": "abbreviation-only; same criterion IDs; no grade writes; no replication",
        }

    def upsert_criteria_verified(self, *args, **kwargs):
        """HF v0.8.9: edita abreviaturas de criterios existentes sin tratarlos como 'already-present'."""
        records = kwargs.get("records")
        expected = kwargs.get("expected")
        required = ("class_id", "class_period_id", "root_content_id", "id_ambito")

        if not isinstance(records, list) or not isinstance(expected, list) or not records or len(records) != len(expected):
            return self._upsert_criteria_verified_legacy(*args, **kwargs)
        if not all(k in kwargs and kwargs.get(k) not in (None, "") for k in required):
            return self._upsert_criteria_verified_legacy(*args, **kwargs)

        # Bloquea el patrón de marcador que provocó la columna accidental del incidente.
        for item in expected:
            desc = self._criteria_hotfix_norm_text(
                self._criteria_hotfix_value(item, "description", "DESCRIPCION")
            )
            if desc.startswith("__"):
                raise SieWebError(
                    "PROTECCIÓN DE CRITERIOS v0.8.9: no se permiten descripciones internas '__...__' como mecanismo para forzar una actualización."
                )

        before = self.get_criteria(
            class_id=int(kwargs["class_id"]),
            class_period_id=int(kwargs["class_period_id"]),
            root_content_id=int(kwargs["root_content_id"]),
            id_ambito=int(kwargs["id_ambito"]),
        )
        changes = []
        all_existing = True

        for record, exp in zip(records, expected):
            cid = self._criteria_hotfix_value(exp, "id", "ID_CONTENIDO")
            if cid in (None, ""):
                cid = self._criteria_hotfix_value(record, "id", "ID_CONTENIDO")
            if cid in (None, ""):
                all_existing = False
                break
            node, count = self._criteria_hotfix_find_by_id(before, cid)
            if node is None or count != 1:
                all_existing = False
                break

            current_description = self._criteria_hotfix_norm_text(
                self._criteria_hotfix_value(node, "DESCRIPCION", "descripcion")
            )
            desired_description = self._criteria_hotfix_norm_text(
                self._criteria_hotfix_value(exp, "description", "DESCRIPCION", default=current_description)
            )
            parent = int(self._criteria_hotfix_value(node, "ID_CONTENIDO_REF", "idpadre", default=0) or 0)
            desired_parent = self._criteria_hotfix_value(exp, "parent_id", "ID_CONTENIDO_REF", default=parent)
            desired_abbreviation = self._criteria_hotfix_value(exp, "abbreviation", "ABREVIATURA")
            if desired_abbreviation in (None, ""):
                desired_abbreviation = self._criteria_hotfix_value(record, "abbreviation", "ABREVIATURA")

            # Este hotfix es deliberadamente conservador: solo intercepta edición de abreviatura.
            if desired_description != current_description or int(desired_parent) != parent or desired_abbreviation in (None, ""):
                all_existing = False
                break

            changes.append({
                "id": int(cid),
                "parent_id": parent,
                "description": current_description,
                "abbreviation": str(desired_abbreviation).strip(),
            })

        if all_existing and changes:
            return self._criteria_hotfix_update_abbreviations_verified(
                class_id=kwargs["class_id"],
                class_period_id=kwargs["class_period_id"],
                root_content_id=kwargs["root_content_id"],
                id_ambito=kwargs["id_ambito"],
                changes=changes,
            )

        return self._upsert_criteria_verified_legacy(*args, **kwargs)

'''

if "_criteria_hotfix_update_abbreviations_verified" not in s:
    marker_candidates = [
        "    def save_grades_verified(",
        "    def update_grades(",
    ]
    marker = next((m for m in marker_candidates if m in s), None)
    if marker is None:
        raise SystemExit(
            "ERROR: no encuentro un punto seguro para insertar el hotfix de criterios en sieweb.py."
        )
    s = s.replace(marker, hotfix + marker, 1)

SIEWEB.write_text(s, encoding="utf-8")

server = SERVER.read_text(encoding="utf-8")
# Solo actualiza la ayuda visible del MCP; el action existente no cambia.
if "v0.8.9" not in server:
    server = server.replace(
        "Para notas nuevas prefiere save_grades_verified.",
        "Para notas nuevas prefiere save_grades_verified. v0.8.9 permite cambiar la abreviatura de desempeños existentes mediante upsert_criteria_verified sin crear una columna nueva; la descripción y las notas permanecen intactas.",
        1,
    )
SERVER.write_text(server, encoding="utf-8")
VERSION.write_text("0.8.9\n", encoding="utf-8")

s2 = SIEWEB.read_text(encoding="utf-8")
assert "def _upsert_criteria_verified_legacy(" in s2
assert "def upsert_criteria_verified(self, *args, **kwargs):" in s2
assert "_criteria_hotfix_update_abbreviations_verified" in s2
assert "PROTECCIÓN DE CRITERIOS v0.8.9" in s2

subprocess.run([sys.executable, "-m", "py_compile", str(SIEWEB), str(SERVER)], check=True)

print("OK: SIEROOM 0.8.9 hotfix aplicado.")
print("- upsert_criteria_verified ahora detecta abreviaturas distintas en criterios existentes.")
print("- La edición conserva ID_CONTENIDO, ID_CLASE_CONTENIDO, padre y descripción.")
print("- Se verifica que la cantidad/IDs de criterios no cambien: si aparece un duplicado, se bloquea.")
print("- Se bloquean marcadores '__...__' usados para forzar actualizaciones.")
print("- No modifica notas ni Nivel de Logro y no replica ediciones a otras secciones automáticamente.")
