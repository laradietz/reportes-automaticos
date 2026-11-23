-- KPIs de cabecera + comparación del último mes contra el anterior.
WITH mensual AS (
    SELECT d.anio_mes, SUM(v.importe_neto) AS ventas
    FROM fact_ventas v JOIN dim_fecha d ON d.fecha = v.fecha
    GROUP BY d.anio_mes
),
ultimo AS (
    SELECT anio_mes, ventas,
           LAG(ventas) OVER (ORDER BY anio_mes) AS ventas_prev
    FROM mensual
    ORDER BY anio_mes DESC
    LIMIT 1
)
SELECT
    ROUND(SUM(v.importe_neto), 2)                         AS ventas_netas,
    COUNT(*)                                              AS ordenes,
    ROUND(SUM(v.importe_neto) * 1.0 / COUNT(*), 2)        AS ticket_promedio,
    COUNT(DISTINCT v.id_cliente)                          AS clientes_activos,
    SUM(v.cantidad)                                       AS unidades,
    ROUND(100.0 * (1 - SUM(v.importe_neto) / SUM(v.importe_bruto)), 2) AS descuento_efectivo_pct,
    (SELECT anio_mes FROM ultimo)                         AS ultimo_mes,
    (SELECT ROUND(ventas, 2) FROM ultimo)                 AS ventas_ultimo_mes,
    (SELECT ROUND((ventas * 1.0 / ventas_prev - 1) * 100, 1) FROM ultimo) AS variacion_mom_pct
FROM fact_ventas v;
