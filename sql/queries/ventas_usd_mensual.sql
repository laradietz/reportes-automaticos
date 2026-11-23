-- Ventas mensuales en USD y tipo de cambio promedio ponderado por operación.
WITH tc AS (
    SELECT d.anio_mes, v.importe_neto,
           (SELECT c.venta FROM dim_cotizacion c
             WHERE c.fecha <= v.fecha ORDER BY c.fecha DESC LIMIT 1) AS tipo_cambio
    FROM fact_ventas v JOIN dim_fecha d ON d.fecha = v.fecha
)
SELECT anio_mes,
       ROUND(SUM(importe_neto / tipo_cambio), 2) AS ventas_usd,
       ROUND(AVG(tipo_cambio), 2)                AS tipo_cambio_promedio
FROM tc
WHERE tipo_cambio IS NOT NULL
GROUP BY anio_mes
ORDER BY anio_mes;
