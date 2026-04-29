from gestorcompras.services.actua_payload import missing_required_fields, normalize_payload


def test_normalize_payload_sets_task_and_oc_aliases():
    payload = {"oc": "12345", "proveedor": "ACME"}
    out = normalize_payload("98765", payload)
    assert out["task_number"] == "98765"
    assert out["numero_tarea"] == "98765"
    assert out["orden_compra"] == "12345"
    assert out["oc"] == "12345"
    assert out["numero_orden"] == "12345"


def test_missing_required_fields_by_origin():
    payload = normalize_payload("111", {"proveedor": "X"})
    missing = missing_required_fields("correos_masivos", payload)
    assert "orden_compra" in missing
    assert "task_number" not in missing

