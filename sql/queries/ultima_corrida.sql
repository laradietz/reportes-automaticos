-- Métricas de la última corrida exitosa del ETL.
SELECT run_id, inicio, fin, filas_leidas, filas_cargadas, filas_rechazadas, estado
FROM etl_runs
WHERE estado = 'OK'
ORDER BY inicio DESC
LIMIT 1;
