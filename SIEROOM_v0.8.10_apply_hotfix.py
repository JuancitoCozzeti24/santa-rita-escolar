from pathlib import Path
import copy
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
if version not in {"0.8.7", "0.8.8", "0.8.9", "0.8.10"}:
    raise SystemExit(
        f"ERROR: versión inesperada {version!r}; no aplicaré el hotfix a ciegas."
    )

for p in (SIEWEB, SERVER, VERSION):
    backup = p.with_suffix(p.suffix + ".bak-v0.8.10-criteria-native-tree")
    if not backup.exists():
        shutil.copy2(p, backup)

s = SIEWEB.read_text(encoding="utf-8")

# HF10 usa deepcopy dentro de sieweb.py; garantiza el import en el archivo destino.
if not re.search(r"(?m)^import copy(?:\s|$)", s):
    if s.startswith("from __future__ import"):
        lines = s.splitlines(True)
        insert_at = 0
        while insert_at < len(lines) and (lines[insert_at].startswith("from __future__ import") or not lines[insert_at].strip()):
            insert_at += 1
        lines.insert(insert_at, "import copy\n")
        s = "".join(lines)
    else:
        s = "import copy\n" + s

if "def upsert_criteria(" not in s:
    raise SystemExit(
        "ERROR: no encuentro el método nativo upsert_criteria de SIEweb. No aplicaré un parche inseguro."
    )

# Si v0.8.9 ya fue aplicado, elimina únicamente su bloque de hotfix para reemplazarlo.
old_start = s.find("    @staticmethod\n    def _criteria_hotfix_value")
if old_start != -1:
    marker_candidates = [
        "    def save_grades_verified(",
        "    def update_grades(",
    ]
    old_end = -1
    for marker in marker_candidates:
        pos = s.find(marker, old_start)
        if pos != -1 and (old_end == -1 or pos < old_end):
            old_end = pos
    if old_end == -1:
        raise SystemExit(
            "ERROR: encontré el hotfix v0.8.9 pero no pude determinar dónde termina. No modificaré el archivo."
        )
    s = s[:old_start] + s[old_end:]

# Conserva la implementación oficial/anterior como fallback para creación de criterios.
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
    # ---------- HF v0.8.10: edición nativa segura de abreviaturas ----------
    @staticmethod
    def _criteria_hf10_value(obj, *keys, default=None):
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
    def _criteria_hf10_norm_text(cls, value):
        return " ".join(str(value or "").strip().split())

    @classmethod
    def _criteria_hf10_real_nodes(cls, tree):
        out = []

        def walk(value):
            if isinstance(value, list):
                for item in value:
                    walk(item)
                return
            if not isinstance(value, dict):
                return
            cid = cls._criteria_hf10_value(value, "ID_CONTENIDO", "id")
            ccid = cls._criteria_hf10_value(value, "ID_CLASE_CONTENIDO", "idClaseContenido")
            if cid not in (None, "") and ccid not in (None, ""):
                out.append(value)
            children = cls._criteria_hf10_value(value, "children", default=[])
            if isinstance(children, list):
                walk(children)

        walk(tree)
        return out

    @classmethod
    def _criteria_hf10_find_node(cls, tree, criterion_id):
        target = str(criterion_id)
        matches = []
        for node in cls._criteria_hf10_real_nodes(tree):
            cid = cls._criteria_hf10_value(node, "ID_CONTENIDO", "id")
            if str(cid) == target:
                matches.append(node)
        if len(matches) != 1:
            return None, len(matches)
        return matches[0], 1

    @classmethod
    def _criteria_hf10_extract_tree(cls, payload):
        data = payload
        if isinstance(data, dict) and isinstance(data.get("json"), dict):
            data = data["json"]
        if not isinstance(data, dict):
            raise SieWebError(
                "PROTECCIÓN HF10: dataInicialPesosCriterios no devolvió un objeto JSON utilizable."
            )
        tree = data.get("resCriterios")
        if not isinstance(tree, list) or not tree:
            raise SieWebError(
                "PROTECCIÓN HF10: no encontré resCriterios del modal nativo. No se envió nada."
            )
        return tree

    @classmethod
    def _criteria_hf10_signature(cls, tree):
        rows = []
        for node in cls._criteria_hf10_real_nodes(tree):
            cid = int(cls._criteria_hf10_value(node, "ID_CONTENIDO", "id"))
            ccid = int(cls._criteria_hf10_value(node, "ID_CLASE_CONTENIDO", "idClaseContenido"))
            parent = int(cls._criteria_hf10_value(node, "ID_CONTENIDO_REF", "idpadre", default=0) or 0)
            desc = cls._criteria_hf10_norm_text(
                cls._criteria_hf10_value(node, "DESCRIPCION", "descripcion")
            )
            rows.append((cid, ccid, parent, desc))
        return sorted(rows)

    def _criteria_hf10_replica_from_payload(self, payload, *, class_id=None, class_period_id=None, root_content_id=None, id_ambito=None):
        """Obtiene datosReplica nativo; para una edición local siempre fuerza replicar=False."""
        preflight = getattr(self, "criteria_write_preflight", None)
        if callable(preflight) and all(v not in (None, "") for v in (class_id, class_period_id, root_content_id, id_ambito)):
            try:
                info = preflight(
                    class_id=int(class_id),
                    class_period_id=int(class_period_id),
                    root_content_id=int(root_content_id),
                    id_ambito=int(id_ambito),
                )
                if isinstance(info, dict):
                    native = info.get("native_replica_context")
                    if isinstance(native, dict):
                        replica = dict(native)
                        replica["replicar"] = False
                        return replica
            except Exception:
                # La edición puede continuar con el contexto derivado del mismo
                # payload nativo si esta revisión no expone el preflight como método.
                pass

        data = payload.get("json") if isinstance(payload, dict) and isinstance(payload.get("json"), dict) else payload
        if not isinstance(data, dict):
            data = {}

        # El modal oficial usa nivelReplicaAnual para el límite. Para una edición
        # local siempre se fuerza replicar=False.
        limite = 1
        nra = data.get("nivelReplicaAnual")
        if isinstance(nra, list) and nra and isinstance(nra[0], dict):
            try:
                limite = int(nra[0].get("LIMITE", 1) or 1)
            except Exception:
                limite = 1

        # idCurso / grupocod se obtienen de un nodo real del propio editor.
        nodes = cls._criteria_hf10_real_nodes(data.get("resCriterios") or [])
        id_curso = None
        grupocod = None
        if nodes:
            id_curso = cls._criteria_hf10_value(nodes[0], "ID_CURSO")
            grupocod = cls._criteria_hf10_value(nodes[0], "GRUPOCOD")

        # SIEweb tolera campos adicionales; estos son los mismos que expone el
        # preflight v0.8.4. Si alguno no está disponible se omite, nunca se inventa.
        replica = {"replicar": False, "limiteReplica": limite}
        if id_curso not in (None, ""):
            replica["idCurso"] = id_curso
        if grupocod not in (None, ""):
            replica["grupocod"] = grupocod
        return replica

    def _criteria_hf10_update_abbreviations_verified(
        self,
        *,
        class_id,
        class_period_id,
        root_content_id,
        id_ambito,
        changes,
    ):
        """
        Edita abreviaturas usando el contrato real del modal: envía el árbol
        COMPLETO resCriterios con el mismo ID_CONTENIDO/ID_CLASE_CONTENIDO.
        No envía una hoja suelta, porque HyoClaseContenido/insertar interpreta
        esos registros como altas nuevas o puede ignorar la modificación.
        """
        before_payload = self.get_criteria(
            class_id=int(class_id),
            class_period_id=int(class_period_id),
            root_content_id=int(root_content_id),
            id_ambito=int(id_ambito),
        )
        before_tree = self._criteria_hf10_extract_tree(before_payload)
        before_signature = self._criteria_hf10_signature(before_tree)
        working_tree = copy.deepcopy(before_tree)
        operations = []
        touched = []

        for change in changes:
            cid = int(change["id"])
            before_node, before_count = self._criteria_hf10_find_node(before_tree, cid)
            work_node, work_count = self._criteria_hf10_find_node(working_tree, cid)
            if before_node is None or work_node is None or before_count != 1 or work_count != 1:
                raise SieWebError(
                    f"PROTECCIÓN HF10: criterio {cid} no es único en el árbol nativo. No se envió nada."
                )

            program_id = self._criteria_hf10_value(before_node, "ID_PROGRAMA")
            program_name = self._criteria_hf10_norm_text(
                self._criteria_hf10_value(before_node, "DESCPROGRAMA", "programa")
            ).lower()
            if program_id not in (None, "", 5, "5") and program_name != "desempeño":
                raise SieWebError(
                    f"PROTECCIÓN HF10: criterio {cid} no es un desempeño. No se envió nada."
                )

            parent = int(self._criteria_hf10_value(before_node, "ID_CONTENIDO_REF", "idpadre", default=0) or 0)
            expected_parent = change.get("parent_id")
            if expected_parent not in (None, "") and parent != int(expected_parent):
                raise SieWebError(
                    f"PROTECCIÓN HF10: el padre de {cid} cambió ({parent} != {expected_parent}). No se envió nada."
                )

            current_description = self._criteria_hf10_norm_text(
                self._criteria_hf10_value(before_node, "DESCRIPCION", "descripcion")
            )
            expected_description = self._criteria_hf10_norm_text(change.get("description"))
            if expected_description and current_description != expected_description:
                raise SieWebError(
                    f"PROTECCIÓN HF10: la descripción de {cid} no coincide exactamente. No se envió nada."
                )

            desired = str(change.get("abbreviation") or "").strip()
            if not desired:
                raise SieWebError(f"PROTECCIÓN HF10: abreviatura vacía para {cid}.")
            if len(desired) > 80:
                raise SieWebError(f"PROTECCIÓN HF10: abreviatura demasiado larga para {cid}.")
            if desired.startswith("__"):
                raise SieWebError(
                    "PROTECCIÓN HF10: se bloquean marcadores internos '__...__'."
                )

            current = str(
                self._criteria_hf10_value(before_node, "ABREVIATURA", "abreviatura", default="") or ""
            ).strip()
            if current == desired:
                operations.append({
                    "action": "already-correct",
                    "idContenido": cid,
                    "abbreviation": desired,
                })
                continue

            # Cambia SOLO lo que el usuario pidió. Los campos *_ORIGI conservan
            # el valor que SIEweb leyó originalmente; sirven para que el modal
            # detecte que el registro EXISTENTE fue editado.
            work_node["ABREVIATURA"] = desired
            if "ABREV_ORIGI" not in work_node or work_node.get("ABREV_ORIGI") in (None, ""):
                work_node["ABREV_ORIGI"] = current
            work_node["EDITOREG"] = 1
            work_node["flExiste"] = True

            # Nunca reescribir descripción ni ORIGI al cambiar una abreviatura.
            work_node["DESCRIPCION"] = self._criteria_hf10_value(before_node, "DESCRIPCION")
            if "ORIGI" in before_node:
                work_node["ORIGI"] = before_node.get("ORIGI")

            touched.append(cid)
            operations.append({
                "action": "update-existing-abbreviation",
                "idContenido": cid,
                "from": current,
                "to": desired,
            })

        if not touched:
            return {
                "saved": True,
                "already_present": True,
                "updated_existing": False,
                "operations": operations,
                "protection": "HF10 full native tree; no new criteria; no grade writes",
            }

        # Protección previa al POST: el árbol a enviar debe contener exactamente
        # los mismos IDs, class-content IDs, padres y descripciones.
        working_signature = self._criteria_hf10_signature(working_tree)
        if working_signature != before_signature:
            raise SieWebError(
                "ALERTA HF10: además de la abreviatura cambió la estructura o una descripción. No se envió nada."
            )

        replica = self._criteria_hf10_replica_from_payload(
            before_payload,
            class_id=class_id,
            class_period_id=class_period_id,
            root_content_id=root_content_id,
            id_ambito=id_ambito,
        )
        write = self.upsert_criteria(
            class_id=int(class_id),
            records=working_tree,
            replica=replica,
        )

        after_payload = self.get_criteria(
            class_id=int(class_id),
            class_period_id=int(class_period_id),
            root_content_id=int(root_content_id),
            id_ambito=int(id_ambito),
        )
        after_tree = self._criteria_hf10_extract_tree(after_payload)
        after_signature = self._criteria_hf10_signature(after_tree)
        if after_signature != before_signature:
            raise SieWebError(
                "ALERTA DE INTEGRIDAD HF10: después del guardado cambió un ID, padre o descripción. Se bloquean nuevas operaciones."
            )

        verification = []
        for change in changes:
            cid = int(change["id"])
            node, count = self._criteria_hf10_find_node(after_tree, cid)
            if node is None or count != 1:
                raise SieWebError(
                    f"VERIFICACIÓN HF10 FALLIDA: criterio {cid} dejó de ser único."
                )
            observed = str(
                self._criteria_hf10_value(node, "ABREVIATURA", "abreviatura", default="") or ""
            ).strip()
            desired = str(change.get("abbreviation") or "").strip()
            if observed != desired:
                raise SieWebError(
                    f"VERIFICACIÓN HF10 FALLIDA: abreviatura de {cid}: {observed!r} != {desired!r}."
                )
            verification.append({
                "id": cid,
                "abbreviation": observed,
                "same_id": True,
                "description_unchanged": True,
            })

        return {
            "saved": True,
            "updated_existing": True,
            "write": write,
            "operations": operations,
            "verification": verification,
            "sent_full_native_tree": True,
            "touched_ids": touched,
            "protection": "HF10: full resCriterios tree; same IDs/parents/descriptions; no grade writes; no replication",
        }

    def upsert_criteria_verified(self, *args, **kwargs):
        """
        HF v0.8.10: intercepta SOLO una edición de abreviatura sobre criterios
        existentes. Las altas nuevas y otros cambios siguen usando el flujo legado.
        """
        records = kwargs.get("records")
        expected = kwargs.get("expected")
        required = ("class_id", "class_period_id", "root_content_id", "id_ambito")

        if (
            not isinstance(records, list)
            or not isinstance(expected, list)
            or not records
            or len(records) != len(expected)
            or not all(k in kwargs and kwargs.get(k) not in (None, "") for k in required)
        ):
            return self._upsert_criteria_verified_legacy(*args, **kwargs)

        before_payload = self.get_criteria(
            class_id=int(kwargs["class_id"]),
            class_period_id=int(kwargs["class_period_id"]),
            root_content_id=int(kwargs["root_content_id"]),
            id_ambito=int(kwargs["id_ambito"]),
        )
        before_tree = self._criteria_hf10_extract_tree(before_payload)
        changes = []

        for record, exp in zip(records, expected):
            cid = self._criteria_hf10_value(exp, "id", "ID_CONTENIDO")
            if cid in (None, ""):
                cid = self._criteria_hf10_value(record, "id", "ID_CONTENIDO")
            if cid in (None, ""):
                return self._upsert_criteria_verified_legacy(*args, **kwargs)

            node, count = self._criteria_hf10_find_node(before_tree, cid)
            if node is None or count != 1:
                return self._upsert_criteria_verified_legacy(*args, **kwargs)

            current_description = self._criteria_hf10_norm_text(
                self._criteria_hf10_value(node, "DESCRIPCION", "descripcion")
            )
            desired_description = self._criteria_hf10_norm_text(
                self._criteria_hf10_value(exp, "description", "DESCRIPCION", default=current_description)
            )
            parent = int(self._criteria_hf10_value(node, "ID_CONTENIDO_REF", "idpadre", default=0) or 0)
            desired_parent = self._criteria_hf10_value(exp, "parent_id", "ID_CONTENIDO_REF", default=parent)
            desired_abbreviation = self._criteria_hf10_value(exp, "abbreviation", "ABREVIATURA")
            if desired_abbreviation in (None, ""):
                desired_abbreviation = self._criteria_hf10_value(record, "abbreviation", "ABREVIATURA")

            # Si intentan cambiar descripción/padre o crear un registro, no lo
            # intercepta HF10: queda en manos del flujo verificado legado.
            if (
                desired_description != current_description
                or int(desired_parent) != parent
                or desired_abbreviation in (None, "")
            ):
                return self._upsert_criteria_verified_legacy(*args, **kwargs)

            if desired_description.startswith("__"):
                raise SieWebError(
                    "PROTECCIÓN HF10: no se permiten descripciones internas '__...__' para forzar una actualización."
                )

            changes.append({
                "id": int(cid),
                "parent_id": parent,
                "description": current_description,
                "abbreviation": str(desired_abbreviation).strip(),
            })

        return self._criteria_hf10_update_abbreviations_verified(
            class_id=kwargs["class_id"],
            class_period_id=kwargs["class_period_id"],
            root_content_id=kwargs["root_content_id"],
            id_ambito=kwargs["id_ambito"],
            changes=changes,
        )

'''

if "_criteria_hf10_update_abbreviations_verified" not in s:
    marker_candidates = [
        "    def save_grades_verified(",
        "    def update_grades(",
    ]
    marker = next((m for m in marker_candidates if m in s), None)
    if marker is None:
        raise SystemExit(
            "ERROR: no encuentro un punto seguro para insertar HF10 en sieweb.py."
        )
    s = s.replace(marker, hotfix + marker, 1)

SIEWEB.write_text(s, encoding="utf-8")

server = SERVER.read_text(encoding="utf-8")
# Actualiza solo la descripción visible del action ya existente; no cambia el contrato MCP.
server = server.replace(
    "v0.8.9 permite cambiar la abreviatura de desempeños existentes mediante upsert_criteria_verified sin crear una columna nueva; la descripción y las notas permanecen intactas.",
    "v0.8.10 permite cambiar la abreviatura de desempeños existentes mediante upsert_criteria_verified enviando el árbol nativo completo resCriterios; conserva IDs, padres, descripciones y notas, y bloquea duplicados.",
)
if "v0.8.10 permite cambiar la abreviatura" not in server:
    server = server.replace(
        "Para notas nuevas prefiere save_grades_verified.",
        "Para notas nuevas prefiere save_grades_verified. v0.8.10 permite cambiar la abreviatura de desempeños existentes mediante upsert_criteria_verified enviando el árbol nativo completo resCriterios; conserva IDs, padres, descripciones y notas, y bloquea duplicados.",
        1,
    )
SERVER.write_text(server, encoding="utf-8")
VERSION.write_text("0.8.10\n", encoding="utf-8")

s2 = SIEWEB.read_text(encoding="utf-8")
assert "def _upsert_criteria_verified_legacy(" in s2
assert "def upsert_criteria_verified(self, *args, **kwargs):" in s2
assert "_criteria_hf10_update_abbreviations_verified" in s2
assert "sent_full_native_tree" in s2
assert "work_node[\"EDITOREG\"] = 1" in s2

subprocess.run([sys.executable, "-m", "py_compile", str(SIEWEB), str(SERVER)], check=True)

print("OK: SIEROOM 0.8.10 hotfix aplicado.")
print("- La edición de abreviatura envía el árbol nativo COMPLETO resCriterios, no una hoja aislada.")
print("- Conserva ID_CONTENIDO, ID_CLASE_CONTENIDO, padre y DESCRIPCION de todos los criterios.")
print("- Solo marca EDITOREG=1 y cambia ABREVIATURA en el desempeño objetivo.")
print("- Verifica que no aparezcan/eliminarse IDs ni cambiar descripciones después del POST.")
print("- No modifica notas, Nivel de Logro ni activa réplica al editar una abreviatura.")