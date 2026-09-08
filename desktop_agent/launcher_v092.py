from __future__ import annotations

from datetime import datetime

import main as legacy
import launcher_v091 as prev
from editor_contract_probe import probe_editor_contract

APP_VERSION = "0.9.2"


def _print_contract(result, evidence_path) -> None:
    print("\n--- CONTRATO DEL EDITOR DE NOTA (SOLO LECTURA) ---")
    print(f"Estudiante: orden {result.student_order} | {result.student_code} | {result.student_name}")
    print(f"Columna: {result.column_index + 1} | {result.column_label[:160]}")
    print(f"Selección del estudiante confirmada: {'sí' if result.row_selection_confirmed else 'no'}")
    print(f"Editor detectado: {'sí' if result.editor_detected else 'no'}")
    a=result.active_element or {}
    attrs=a.get('attrs') or {}
    print("\nElemento activo del editor:")
    print(f"  tag={a.get('tag') or '-'} | role={attrs.get('role') or '-'} | type={attrs.get('type') or '-'}")
    print(f"  name={attrs.get('name') or '-'} | id={attrs.get('id') or '-'} | class={str(attrs.get('class') or '')[:180]}")
    print(f"  maxlength={attrs.get('maxlength') or '-'} | pattern={attrs.get('pattern') or '-'} | inputmode={attrs.get('inputmode') or '-'}")
    print(f"  placeholder={attrs.get('placeholder') or '-'} | aria-label={attrs.get('aria-label') or '-'}")
    print(f"  value actual (no secreto): {str(a.get('value') or '')[:80] or '(vacío)'}")

    if result.ancestors:
        print("\nAncestros inmediatos del editor (muestra):")
        for item in result.ancestors[:6]:
            at=item.get('attrs') or {}
            print(f"  depth={item.get('depth')} | tag={item.get('tag') or '-'} | class={str(at.get('class') or '')[:160]} | role={at.get('role') or '-'}")

    if result.nearby_controls:
        print("\nControles visibles cercanos (sin activarlos):")
        for item in result.nearby_controls[:12]:
            at=item.get('attrs') or {}
            label=item.get('text') or at.get('aria-label') or at.get('placeholder') or ''
            print(f"  {item.get('tag') or '-'} | role={at.get('role') or '-'} | type={at.get('type') or '-'} | texto={str(label)[:120]}")

    if result.event_listeners:
        print("\nListeners del input/editor (CDP):")
        for item in result.event_listeners[:18]:
            if item.get('error'):
                print(f"  error CDP: {item.get('error')}")
                continue
            src=item.get('source_url') or f"scriptId={item.get('script_id','')}"
            desc=str(item.get('handler_description') or '').replace('\n',' ')
            print(f"  {item.get('type')} | ancestro={item.get('depth')} | línea={item.get('line_number')} | {src[:130]}")
            if desc:
                print(f"     handler: {desc[:220]}")

    print(f"\nSolicitudes POST/PUT/PATCH/DELETE al abrir: {len(result.network_requests)}")
    for req in result.network_requests[:10]:
        print(f"  {req.get('method')} | {str(req.get('url',''))[:220]}")
    print(f"Escape enviado: {'sí' if result.escape_sent else 'no'}")
    print(f"Editor cerrado tras Escape: {'sí' if result.editor_closed_after_escape else 'no'}")
    print(f"Texto de celda sin cambios: {'sí' if result.grade_text_unchanged else 'NO'}")
    if result.error:
        print(f"Detalle: {result.error}")
    print(f"Evidencia JSON: {evidence_path}")
    if result.ok and result.editor_detected and result.grade_text_unchanged:
        print("OK: contrato del editor leído sin escribir ni guardar ninguna calificación.")
    else:
        print("AVISO: no realizar pruebas de escritura todavía.")


def maybe_run_contract_probe(probe) -> None:
    page=getattr(probe,'_page',None)
    cell_map=getattr(probe,'_cell_map',None)
    if page is None or cell_map is None or not getattr(cell_map,'students',None):
        return
    print("\n--- SIGUIENTE PRUEBA OPCIONAL ---")
    print("E = abrir UNA celda, inspeccionar el input/editor y cerrarlo con Escape. NO escribe nada.")
    print("ENTER = omitir.")
    choice=legacy.prompt("Elige E o ENTER: ").lower()
    if choice not in {'e','editor'}:
        return
    max_order=max([int(str(s.get('order') or 0)) for s in cell_map.students] or [1])
    raw_order=legacy.prompt(f"Número de orden del estudiante [1-{max_order}] (ENTER=1): ") or '1'
    raw_col=legacy.prompt(f"Columna [1-{cell_map.column_count}] (ENTER=1): ") or '1'
    try:
        order=int(raw_order); column=int(raw_col)
    except ValueError:
        print("Entrada inválida. No se realizó ningún clic."); return
    if order<1 or order>max_order or column<1 or column>cell_map.column_count:
        print("Orden/columna fuera de rango. No se realizó ningún clic."); return
    evidence_dir=legacy.app_data_root()/"evidence"
    evidence_dir.mkdir(parents=True,exist_ok=True)
    result=probe_editor_contract(page,cell_map,order,column,evidence_dir)
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    path=legacy.save_json(evidence_dir,f"{stamp}_sieweb_editor_contract.json",result.as_dict())
    _print_contract(result,path)


legacy.APP_VERSION=APP_VERSION
legacy.map_grade_cells=prev.map_grade_cells_normalized
legacy.probe_grade_cells=prev.probe_grade_cells_with_framework


def print_grade_cell_probe_v092(probe) -> None:
    prev.original_print(probe)
    prev.print_event_report(getattr(probe,'event_listener_report',None))
    prev.print_vue_report(getattr(probe,'vue_event_report',None))
    maybe_run_contract_probe(probe)

legacy.print_grade_cell_probe=print_grade_cell_probe_v092

if __name__ == '__main__':
    legacy.main()
