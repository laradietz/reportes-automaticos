-- Registros rechazados en la ÚLTIMA corrida exitosa, agrupados por motivo.
SELECT tabla, motivo, COUNT(*) AS registros
FROM etl_rechazos
WHERE run_id = (SELECT run_id FROM etl_runs WHERE estado = 'OK' ORDER BY inicio DESC LIMIT 1)
GROUP BY tabla, motivo
ORDER BY registros DESC;
