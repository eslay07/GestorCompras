# Seguridad

## Reporte responsable

Reporta una vulnerabilidad mediante un aviso privado de seguridad en la pestaña **Security** del repositorio. No incluyas secretos, datos personales ni información de producción en incidencias públicas.

## Reglas para contribuciones

- No subas archivos de entorno, credenciales, claves, certificados o tokens.
- No añadas bases de datos, logs, descargas ni configuraciones locales.
- Usa solamente fixtures sintéticos y correos `example.com`.
- Mantén los adaptadores de demostración sin conexiones externas.
- Ejecuta `scripts\privacy_check.py` y las pruebas antes de proponer cambios.

Si un secreto llegara a incorporarse, revócalo en su sistema de origen antes de limpiar el historial. No publiques su valor en reportes o conversaciones.
