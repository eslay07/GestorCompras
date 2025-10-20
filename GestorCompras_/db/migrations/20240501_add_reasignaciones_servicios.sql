CREATE TABLE IF NOT EXISTS reasignaciones_servicios (
  id INTEGER PRIMARY KEY,
  message_id TEXT UNIQUE,
  fecha DATETIME,
  asunto TEXT,
  task_number TEXT,
  proveedor TEXT,
  mecanico TEXT,
  telefono TEXT,
  inf_vehiculo TEXT,
  correo_usuario TEXT,
  raw_hash TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rs_fecha ON reasignaciones_servicios(fecha);
CREATE INDEX IF NOT EXISTS idx_rs_message ON reasignaciones_servicios(message_id);
CREATE INDEX IF NOT EXISTS idx_rs_task ON reasignaciones_servicios(task_number);
