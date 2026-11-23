-- Evolución mensual con variación contra el mes anterior y acumulado (funciones de ventana).
WITH m AS (
    SELECT d.anio_mes,
           COUNT(*)                         AS ordenes,
           ROUND(SUM(v.importe_neto), 2)    AS ventas_netas
    FROM fact_ventas v JOIN dim_fecha d ON d.fecha = v.fecha
    GROUP BY d.anio_mes
)
SELECT anio_mes,
       ordenes,
       ventas_netas,
       LAG(ventas_netas) OVER (ORDER BY anio_mes) AS ventas_mes_anterior,
       ROUND((ventas_netas * 1.0 / LAG(ventas_netas) OVER (ORDER BY anio_mes) - 1) * 100, 1) AS variacion_pct,
       ROUND(SUM(ventas_netas) OVER (ORDER BY anio_mes), 2) AS acumulado
FROM m
ORDER BY anio_mes;
