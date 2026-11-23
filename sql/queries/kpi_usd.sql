-- Ventas netas convertidas a USD con el último tipo de cambio disponible a la fecha de cada venta.
WITH tc AS (
    SELECT v.importe_neto,
           (SELECT c.venta FROM dim_cotizacion c
             WHERE c.fecha <= v.fecha ORDER BY c.fecha DESC LIMIT 1) AS tipo_cambio
    FROM fact_ventas v
)
SELECT ROUND(SUM(importe_neto / tipo_cambio), 2) AS ventas_usd,
       ROUND(AVG(tipo_cambio), 2)                AS tipo_cambio_promedio
FROM tc
WHERE tipo_cambio IS NOT NULL;
