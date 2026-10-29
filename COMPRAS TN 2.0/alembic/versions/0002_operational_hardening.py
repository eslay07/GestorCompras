"""Protecciones de concurrencia y normalización de reportes heredados."""

from alembic import op

revision = "0002_operational_hardening"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Versiones anteriores podían insertar la misma tarea pendiente desde dos
    # trabajos simultáneos. Se conserva el registro más antiguo y se impide la
    # carrera sin prohibir que una tarea ya consumida vuelva a encolarse.
    op.execute(
        """
        DELETE FROM task_inbox
        WHERE status = 'pending'
          AND id NOT IN (
              SELECT MIN(id)
              FROM task_inbox
              WHERE status = 'pending'
              GROUP BY origin, task_number
          )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_task_inbox_pending
        ON task_inbox (origin, task_number)
        WHERE status = 'pending'
        """
    )

    # ACTUA_REPORT_EMAIL era un interruptor 0/1 en el programa anterior, no
    # una dirección. Lo separamos para no intentar enviar correo a "1".
    op.execute(
        """
        INSERT INTO settings (namespace, key, value_json, updated_at)
        SELECT namespace,
               'actua_send_report',
               CASE
                   WHEN lower(trim(value_json, ' \"')) IN ('1', 'true', 'yes', 'si', 'sí')
                       THEN 'true'
                   ELSE 'false'
               END,
               updated_at
        FROM settings
        WHERE namespace = 'automation'
          AND key = 'actua_report_email'
          AND lower(trim(value_json, ' \"')) IN
              ('0', '1', 'true', 'false', 'yes', 'no', 'si', 'sí')
        ON CONFLICT(namespace, key) DO UPDATE SET
            value_json = excluded.value_json,
            updated_at = excluded.updated_at
        """
    )
    op.execute(
        """
        UPDATE settings
        SET value_json = '""'
        WHERE namespace = 'automation'
          AND key = 'actua_report_email'
          AND lower(trim(value_json, ' \"')) IN
              ('0', '1', 'true', 'false', 'yes', 'no', 'si', 'sí')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_task_inbox_pending")
